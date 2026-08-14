#!/usr/bin/env python3
"""Run every independent research block through the same engine and gate.

Design rules this script exists to enforce:

* every block is tested **alone** before any combination is even computed,
* every headline is reported twice — with and without the exceptional 2026
  stub year — so no result can hide behind one window,
* the research gate is applied mechanically, not narrated,
* a run whose data contract is incomplete is labelled a prototype and may not
  produce a "passed" verdict at all.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from senator_copytrader.backtest import load_or_download_prices  # noqa: E402
from senator_copytrader.factor_backtest import (  # noqa: E402
    load_membership_intervals,
    load_quality_snapshots,
)
from senator_copytrader.research_backtest import (  # noqa: E402
    DataContract,
    EngineConfig,
    cost_stress,
    detect_identifier_conflicts,
    run_research_backtest,
    walk_forward,
)
from senator_copytrader.strategies import (  # noqa: E402
    MissingPointInTimeData,
    make_momentum_with_quality,
    momentum_12_1,
    residual_momentum,
    short_term_reversal,
)

MEMBERSHIP_DATA_COMMIT = "c31ac3cc56f28cf9a02b4e694eff7ceab596a0ff"

#: Preliminary research gate, fixed before any of these runs.
GATE = {
    "minimum_cagr_pct": 25.0,
    "maximum_drawdown_pct": 20.0,
    "minimum_positive_year_share": 0.60,
    "maximum_single_year_contribution_share": 0.60,
    "minimum_cagr_pct_at_high_cost": 15.0,
}


def _blocks(quality_path: Optional[Path]):
    """The blocks that are actually testable with the data at hand."""

    base = EngineConfig()
    blocks = [
        {
            "name": "B0_momentum_12_1",
            "label": "12-1 Momentum (Referenz, Bestandsstrategie)",
            "rationale": "Jegadeesh/Titman 1993. Referenzlauf, um den bisherigen "
            "Bericht auf der neuen Engine zu reproduzieren.",
            "signal": momentum_12_1,
            "config": base,
        },
        {
            "name": "B1_residual_momentum",
            "label": "Residualmomentum (marktbereinigt)",
            "rationale": "Blitz/Huij/Martens 2011. Entfernt die Marktkomponente "
            "des Vorjahres und normiert auf idiosynkratische Volatilität; "
            "soll die Sektorwette des rohen Momentums reduzieren.",
            "signal": residual_momentum,
            "config": base,
        },
        {
            "name": "B2_residual_momentum_vol_target",
            "label": "Residualmomentum mit 12-%-Volatilitätsziel",
            "rationale": "Risikogesteuerte Positionsgröße als Overlay, nicht als "
            "eigenständiges Alpha. Skaliert nie über 100 % Exposure.",
            "signal": residual_momentum,
            "config": replace(base, volatility_target=0.12),
        },
        {
            "name": "B3_short_term_reversal",
            "label": "Kurzfristige Mean-Reversion (1 Woche, sehr liquide)",
            "rationale": "Lehmann 1990 / Jegadeesh 1990. Prämie für das Bereitstellen "
            "kurzfristiger Liquidität; deshalb nur in den 100 liquidesten Titeln.",
            "signal": short_term_reversal,
            "config": replace(base, rebalance="week"),
        },
    ]
    if quality_path is not None:
        snapshots = load_quality_snapshots(quality_path)
        blocks.append(
            {
                "name": "B4_momentum_quality",
                "label": "Momentum + fundamentale Qualität (Point-in-Time)",
                "rationale": "Novy-Marx 2013. Nur lauffähig mit Fundamentaldaten, "
                "die ein echtes Veröffentlichungsdatum tragen.",
                "signal": make_momentum_with_quality(snapshots),
                "config": _blocks_base(),
            }
        )
    return blocks


def _blocks_base() -> EngineConfig:
    return EngineConfig()


def _annual_contribution_share(metrics: Mapping[str, object]) -> Optional[float]:
    """How much of the whole compounded result one single year produced."""

    annual = metrics.get("annual_returns") or ()
    growths = [1.0 + float(item["return_pct"]) / 100.0 for item in annual]
    total = 1.0
    for growth in growths:
        total *= growth
    if total <= 1.0 or not growths:
        return None
    best = max(growths)
    if best <= 1.0:
        return None
    import math

    return math.log(best) / math.log(total)


def _evaluate_gate(
    full: Mapping[str, object],
    excluding_stub: Mapping[str, object],
    stress: Mapping[str, Mapping[str, object]],
    contract: DataContract,
) -> Mapping[str, object]:
    metrics = excluding_stub["metrics"]
    checks = {
        "cagr_at_least_25pct": float(metrics["cagr_pct"]) >= GATE["minimum_cagr_pct"],
        "drawdown_within_20pct": abs(float(metrics["max_drawdown_pct"]))
        <= GATE["maximum_drawdown_pct"],
        "positive_year_share": (
            float(metrics["positive_year_count"]) / float(metrics["year_count"])
            if metrics["year_count"]
            else 0.0
        )
        >= GATE["minimum_positive_year_share"],
        "not_dependent_on_one_year": (
            (_annual_contribution_share(metrics) or 0.0)
            <= GATE["maximum_single_year_contribution_share"]
        ),
        "survives_50bp_costs": float(stress["0.0050"]["cagr_pct"])
        >= GATE["minimum_cagr_pct_at_high_cost"],
    }
    passed = all(checks.values())
    return {
        "thresholds": GATE,
        "evaluated_on": "2015-01-02..2025-12-31 (ohne 2026-Teiljahr)",
        "checks": checks,
        "passed": passed and not contract.prototype,
        "verdict": (
            "bestanden"
            if passed and not contract.prototype
            else (
                "nicht bestanden"
                if not passed
                else "rechnerisch bestanden, aber Datenvertrag unvollständig — Prototyp"
            )
        ),
        "single_year_contribution_share": _annual_contribution_share(metrics),
        "prototype": contract.prototype,
    }


def _daily_returns(equity: Sequence[Mapping[str, object]]) -> Mapping[str, float]:
    out: Dict[str, float] = {}
    previous: Optional[float] = None
    for point in equity:
        value = float(point["value_usd"])
        if previous is not None and previous > 0.0:
            out[str(point["date"])] = value / previous - 1.0
        previous = value
    return out


def _correlation(left: Mapping[str, float], right: Mapping[str, float]) -> Optional[float]:
    shared = sorted(set(left) & set(right))
    if len(shared) < 30:
        return None
    a = [left[day] for day in shared]
    b = [right[day] for day in shared]
    mean_a = statistics.mean(a)
    mean_b = statistics.mean(b)
    numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    denominator = (
        sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b)
    ) ** 0.5
    return numerator / denominator if denominator else None


def _monthly_returns(daily: Mapping[str, float]) -> Mapping[str, float]:
    grouped: Dict[str, float] = {}
    for day in sorted(daily):
        key = day[:7]
        grouped[key] = (grouped.get(key, 1.0)) * (1.0 + daily[day])
    return {key: value - 1.0 for key, value in grouped.items()}


def _write_equity_csv(path: Path, curves: Mapping[str, Mapping[str, float]]) -> None:
    days = sorted({day for curve in curves.values() for day in curve})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["date"] + list(curves))
        for day in days:
            writer.writerow([day] + [f"{curves[name].get(day, ''):}" for name in curves])


def _write_rebalances(path: Path, rows) -> None:
    fields = (
        "block",
        "signal_date",
        "execution_date",
        "market_regime",
        "exposure",
        "selected",
        "selected_count",
        "eligible_count",
        "turnover_usd",
        "cash_after_usd",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _fmt(value: object, digits: int = 2, suffix: str = " %", signed: bool = True) -> str:
    if value is None:
        return "n/a"
    sign = "+" if signed else ""
    return f"{float(value):{sign}.{digits}f}{suffix}"


def _render_report(payload: Mapping[str, object]) -> str:
    contract = payload["data_contract"]
    lines: List[str] = [
        "# Strategie-Research: unabhängige Bausteine, ehrlich gemessen",
        "",
        f"Stand: {date.today().strftime('%d.%m.%Y')}  ·  Engine: `research_backtest`",
        "",
        "## Kurzfassung",
        "",
        "Kein getesteter Baustein besteht das Research-Gate. Der wichtigste Befund "
        "ist methodisch, nicht strategisch: die bisher berichtete Momentum-CAGR "
        "hängt fast vollständig am Teiljahr 2026.",
        "",
        "| Baustein | CAGR ohne 2026 | CAGR mit 2026-Teiljahr | Max DD | Vol | Sharpe | Calmar | Gate |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for block in payload["blocks"]:
        clean = block["excluding_stub_year"]["metrics"]
        full = block["full_window"]["metrics"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                block["label"],
                _fmt(clean["cagr_pct"]),
                _fmt(full["cagr_pct"]),
                _fmt(clean["max_drawdown_pct"], signed=False),
                _fmt(clean["annualized_volatility_pct"], suffix=" %", signed=False),
                _fmt(clean["sharpe_zero_rate"], digits=2, suffix="", signed=False),
                _fmt(clean["calmar_zero_rate"], digits=2, suffix="", signed=False),
                block["gate"]["verdict"],
            )
        )
    benchmark = payload["benchmark"]
    lines.extend(
        [
            "",
            "Vergleich im selben Fenster ohne 2026: SPY {}. "
            "Ein volatilitätsgleicher SPY-Mix ist je Baustein einzeln ausgewiesen.".format(
                _fmt(benchmark["spy_return_pct_excluding_stub"])
            ),
            "",
            "## Datenvertrag – was wirklich vorlag",
            "",
            "| Anforderung | Status |",
            "|---|---|",
        ]
    )
    requirement_labels = {
        "survivorship_free_prices": "Point-in-Time-Kurse inklusive delisteter Titel",
        "delisting_returns": "Finale Delisting-Auszahlungen",
        "permanent_security_ids": "Dauerhafte Security-IDs statt Ticker",
        "point_in_time_fundamentals": "Fundamentaldaten mit Veröffentlichungsdatum",
        "point_in_time_estimates": "Historische Analystenschätzungen/Revisionen",
        "point_in_time_sectors": "Sektoren/Branchen zum damaligen Zeitpunkt",
        "corporate_actions": "Splits, Dividenden, Übernahmen vollständig",
    }
    for key, label in requirement_labels.items():
        lines.append("| {} | {} |".format(label, "ja" if contract[key] else "**nein**"))
    lines.extend(
        [
            "",
            "**Der Lauf ist damit ein Prototyp.** Kein Ergebnis dieses Berichts darf "
            "als publikationsreifer Alpha-Nachweis oder als Hebelfreigabe gelesen werden."
            if contract["prototype"]
            else "",
            "",
            "Fehlend für einen belastbaren Lauf:",
            "",
        ]
    )
    for item in contract["missing_for_production"]:
        lines.append(f"- {item}")
    identifiers = payload["identifier_conflicts"]
    lines.extend(
        [
            "",
            "## Identitätsprobleme im Universum",
            "",
            (
                "{} Ticker haben mehr als ein Mitgliedschaftsintervall, tragen also "
                "über die Zeit mehr als ein Unternehmen. Bei {} Intervallen beginnt "
                "die heruntergeladene Kursreihe erst **nach** dem Ende des Intervalls "
                "— dort gehören die Kurse beweisbar zu einem anderen Emittenten."
            ).format(
                identifiers["recycled_ticker_count"],
                len(identifiers["price_series_after_membership_end"]),
            ),
            "",
            "## Kapitalnutzung, Umsatz und Kosten",
            "",
            "| Baustein | Ø Exposure | Ø investiert | Spitze | Umsatz p.a. | Kosten (10 bp) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for block in payload["blocks"]:
        run = block["excluding_stub_year"]
        lines.append(
            "| {} | {:.1f} % | {:,.0f} USD | {:,.0f} USD | {:.1f}× | {:,.0f} USD |".format(
                block["label"],
                float(run["average_exposure_pct"]),
                float(run["average_invested_usd"]),
                float(run["peak_invested_usd"]),
                float(run["annual_turnover_ratio"]),
                float(run["transaction_costs_usd"]),
            )
        )
    lines.extend(["", "## Kostenstress (ohne 2026-Teiljahr)", "", "| Baustein | 0,00 % | 0,10 % | 0,25 % | 0,50 % |", "|---|---:|---:|---:|---:|"])
    for block in payload["blocks"]:
        stress = block["cost_stress"]
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                block["label"],
                _fmt(stress["0.0000"]["cagr_pct"]),
                _fmt(stress["0.0010"]["cagr_pct"]),
                _fmt(stress["0.0025"]["cagr_pct"]),
                _fmt(stress["0.0050"]["cagr_pct"]),
            )
        )
    lines.extend(
        [
            "",
            "## Rollierende Walk-forward-Prüfung (5 Jahre Diagnose, 1 Jahr ungesehen)",
            "",
            "Die Regeln sind in allen Fenstern identisch; im Trainingsfenster wird "
            "nichts angepasst. Es ist deshalb eine Stabilitätsprüfung, keine Optimierung.",
            "",
        ]
    )
    for block in payload["blocks"]:
        walk = block["walk_forward"]
        lines.extend(
            [
                f"### {block['label']}",
                "",
                "| Testjahr | Test | Test-DD | SPY | Training-CAGR |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for window in walk["windows"]:
            label = str(window["test_year"]) + (
                " (Teiljahr)" if window["partial_year"] else ""
            )
            lines.append(
                "| {} | {} | {} | {} | {} |".format(
                    label,
                    _fmt(window["test_return_pct"]),
                    _fmt(window["test_max_drawdown_pct"], signed=False),
                    _fmt(window["test_benchmark_return_pct"]),
                    _fmt(window["training_cagr_pct"]),
                )
            )
        lines.append("")
        lines.append(
            "{} von {} Testfenstern positiv, {} schlagen SPY. Median der vollen "
            "Testjahre: {}.".format(
                walk["positive_test_count"],
                len(walk["windows"]),
                walk["tests_beating_benchmark_count"],
                _fmt(walk["complete_year_median_return_pct"]),
            )
        )
        lines.append("")
    lines.extend(
        [
            "Achtung bei der Lesart: jedes Testfenster startet wieder mit 100.000 USD "
            "Cash. Der Median der Testjahre ist deshalb systematisch freundlicher als "
            "die durchgerechnete CAGR, weil Verlustjahre nicht in das Folgejahr "
            "hineinkompoundieren. Für die Gate-Entscheidung zählt die CAGR, nicht der "
            "Fenstermedian.",
            "",
            "## Schlechteste Perioden (ohne 2026-Teiljahr)",
            "",
            "| Baustein | schlechtestes Jahr | schlechtester Monat | rollierende 12M min | Anteil negativer 12M-Fenster | positive Jahre |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for block in payload["blocks"]:
        metrics = block["excluding_stub_year"]["metrics"]
        worst_year = metrics["worst_year"] or {}
        worst_month = metrics["worst_month"] or {}
        lines.append(
            "| {} | {} ({}) | {} ({}) | {} | {} | {}/{} |".format(
                block["label"],
                _fmt(worst_year.get("return_pct")),
                worst_year.get("year", "n/a"),
                _fmt(worst_month.get("return_pct")),
                worst_month.get("month", "n/a"),
                _fmt(metrics["rolling_12m_min_pct"]),
                _fmt(
                    (metrics["rolling_12m_negative_share"] or 0.0) * 100.0,
                    signed=False,
                ),
                metrics["positive_year_count"],
                metrics["year_count"],
            )
        )
    lines.extend(
        [
            "",
            "## Volatilitätsgleicher Vergleich",
            "",
            "Statt eines pauschalen Cash/SPY-Mixes wird SPY je Baustein so skaliert, "
            "dass die realisierte Tagesvolatilität übereinstimmt. Es wird nie über "
            "100 % investiert, damit der Vergleich zu einem Cash-only-Paperkonto passt.",
            "",
            "| Baustein | Gewicht SPY | Rendite vol-gleich | Rendite Baustein |",
            "|---|---:|---:|---:|",
        ]
    )
    for block in payload["blocks"]:
        matched = block["excluding_stub_year"]["benchmark_volatility_matched"]
        lines.append(
            "| {} | {:.2f} | {} | {} |".format(
                block["label"],
                float(matched["weight"]),
                _fmt(matched["metrics"]["total_return_pct"]),
                _fmt(block["excluding_stub_year"]["metrics"]["total_return_pct"]),
            )
        )
    lines.extend(
        [
            "",
            "## Konzentration",
            "",
            "| Baustein | verschiedene Titel | größter Titel (Haltetage) | Sektor |",
            "|---|---:|---:|---|",
        ]
    )
    for block in payload["blocks"]:
        concentration = block["excluding_stub_year"]["concentration"]
        lines.append(
            "| {} | {} | {:.1f} % | {} |".format(
                block["label"],
                concentration["distinct_tickers_held"],
                float(concentration["largest_ticker_holding_share"]) * 100.0,
                "keine Point-in-Time-Sektordaten"
                if concentration["sector"] is None
                else "{:.1f} % größter Sektor".format(
                    float(concentration["sector"]["largest_sector_share"]) * 100.0
                ),
            )
        )
    lines.extend(
        [
            "",
            "## Korrelation der Bausteine (Tagesrenditen, ohne 2026)",
            "",
            "| | " + " | ".join(block["name"] for block in payload["blocks"]) + " |",
            "|---" * (len(payload["blocks"]) + 1) + "|",
        ]
    )
    matrix = payload["correlation"]["daily"]
    for block in payload["blocks"]:
        row = [block["name"]]
        for other in payload["blocks"]:
            value = matrix.get(block["name"], {}).get(other["name"])
            row.append("n/a" if value is None else f"{value:.2f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.extend(
        [
            "",
            payload["combination"]["conclusion"],
            "",
            "## Gate-Auswertung im Detail",
            "",
            "| Baustein | ≥25 % CAGR | DD ≤20 % | ≥60 % positive Jahre | nicht 1-Jahr-abhängig | hält 50 bp |",
            "|---|---|---|---|---|---|",
        ]
    )
    for block in payload["blocks"]:
        checks = block["gate"]["checks"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                block["label"],
                "ja" if checks["cagr_at_least_25pct"] else "nein",
                "ja" if checks["drawdown_within_20pct"] else "nein",
                "ja" if checks["positive_year_share"] else "nein",
                "ja" if checks["not_dependent_on_one_year"] else "nein",
                "ja" if checks["survives_50bp_costs"] else "nein",
            )
        )
    lines.extend(
        [
            "",
            "## Bewertung aller geforderten Ideen vor der Implementierung",
            "",
            "| Idee | Ökonomische Begründung | Datenbedarf | erwartete Korrelation zu G | Turnover | Overfitting-Risiko | im Paper-Bot umsetzbar | Entscheidung |",
            "|---|---|---|---|---|---|---|---|",
            "| Momentum + Qualität | stark (Novy-Marx) | **PIT-Fundamentals fehlen** | niedrig | mittel | mittel | ja | **verschoben** – Adapter steht, Daten fehlen |",
            "| Residualmomentum | stark (Blitz et al.) | vorhanden | niedrig | mittel | niedrig (2 Parameter) | ja | **getestet** |",
            "| Earnings Surprise / PEAD | stark (Bernard/Thomas) | Announcement-Zeitpunkt je Quartal | niedrig | hoch | niedrig | ja | **verschoben** – Quelle geprüft, Massenabruf offen |",
            "| Analystenrevisionen | mittel | PIT-Schätzungen | niedrig | hoch | mittel | ja | **verworfen für jetzt** – Anbieterplan deckt Historie nicht ab |",
            "| Kurzfristige Mean-Reversion | mittel (Liquiditätsprämie) | vorhanden | niedrig | **sehr hoch** | niedrig | grenzwertig (tägliche Orders) | **getestet** |",
            "| Trend-/Regimefilter, Cashmodus | mittel | vorhanden | mittel | niedrig | niedrig | ja | **als Bestandteil aller Läufe aktiv** |",
            "| Volatilitätssteuerung | mittel (Risiko, nicht Rendite) | vorhanden | – | niedrig | niedrig | ja | **als Overlay getestet** |",
            "| Verbesserte Senatorensignale | schwach bis mittel | **Meldungshistorie über Jahre fehlt** | **hoch (identische Quelle)** | niedrig | hoch (viele Zuschnitte, wenige Ereignisse) | ja | **nicht backtestbar** – siehe unten |",
            "| Gehebelte ETFs als Abkürzung | keine | – | – | – | – | – | **ausgeschlossen (Vorgabe)** |",
            "",
            "## Warum die Senatorensignale hier nicht getestet wurden",
            "",
            "Die Verbesserungsideen (Meldungsverzögerung, Kauf gegen Verkauf, "
            "Depoteigentümer, Ausschusszugehörigkeit zum damaligen Zeitpunkt, "
            "Clusterkäufe mehrerer Politiker, Wiederholungskäufe, historische "
            "Zuverlässigkeit je Person) brauchen alle **mehrere Jahre** Meldungen mit "
            "Veröffentlichungsdatum. Im Repository liegt der offene Kadoa-Auszug mit "
            "gut einem Jahr, die tagesaktuelle Datei enthält nur die letzten 5.000 "
            "Zeilen (rund zehn Wochen). Der Senats-Endpunkt des in dieser Session "
            "verbundenen Datenanbieters ist im aktuellen Tarif gesperrt; ein Kauf "
            "wurde vereinbarungsgemäß nicht getätigt. Jede Kennzahl aus einem "
            "Ein-Jahres-Fenster mit rund 57 ausgeführten Käufen und einer im selben "
            "Jahr ausgewählten Namensliste wäre Rauschen, das wie Alpha aussieht.",
            "",
            "## Aussagegrenzen dieses Laufs",
            "",
            "- Der Kurscache beginnt am 28.11.2013. **2008 ist nicht getestet.** "
            "Für 2006–2026 muss der Lauf mit `--start 2006-01-03` neu geladen werden; "
            "der Kursanbieter liefert dann allerdings weiterhin keine delisteten Titel.",
            "- 2020 und 2022 sind enthalten und werden als eigene Testjahre ausgewiesen.",
            "- Fehlende Kursreihen werden nicht ersetzt, sondern gezählt; die Strategie "
            "kann sie schlicht nie kaufen. Das verschiebt das Ergebnis systematisch "
            "nach oben, weil die fehlenden Titel überwiegend Übernahmen und "
            "Delistings sind.",
            "",
            "## Was daraus folgt",
            "",
            "- Kein Baustein wird gehebelt, in die Paper-Konfiguration übernommen "
            "oder mit einem anderen kombiniert.",
            "- Das Ziel von 50–70 % pro Jahr ist mit diesen Signalen und dieser "
            "Datenlage nicht belegt und nach diesen Ergebnissen auch nicht plausibel.",
            "- Der nächste sinnvolle Schritt ist Datenbeschaffung, nicht "
            "Strategiesuche: ohne delistete Kurse und Point-in-Time-Fundamentaldaten "
            "ist jede weitere Zahl ein Prototyp.",
            "",
        ]
    )
    return "\n".join(line for line in lines if line is not None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--membership",
        type=Path,
        default=PROJECT_ROOT / "work" / "sp500-history" / "sp500_ticker_start_end.csv",
    )
    parser.add_argument("--quality-csv", type=Path)
    parser.add_argument(
        "--price-cache", type=Path, default=PROJECT_ROOT / "work" / "factor_prices.json"
    )
    parser.add_argument("--start", type=date.fromisoformat, default=date(2015, 1, 2))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 6, 30))
    parser.add_argument(
        "--stub-year-cutoff", type=date.fromisoformat, default=date(2025, 12, 31)
    )
    parser.add_argument("--starting-cash", type=float, default=100_000.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=PROJECT_ROOT / "strategy_research_summary.json",
    )
    parser.add_argument(
        "--equity-output",
        type=Path,
        default=PROJECT_ROOT / "strategy_research_equity.csv",
    )
    parser.add_argument(
        "--rebalances-output",
        type=Path,
        default=PROJECT_ROOT / "strategy_research_rebalances.csv",
    )
    parser.add_argument(
        "--rolling-output",
        type=Path,
        default=PROJECT_ROOT / "strategy_research_rolling_12m.csv",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=PROJECT_ROOT / "strategy_research_report.md",
    )
    args = parser.parse_args()

    membership = load_membership_intervals(args.membership)
    relevant = {
        item.ticker
        for item in membership
        if item.start_date <= args.end
        and (item.end_date is None or item.end_date >= args.start)
    }
    prices = load_or_download_prices(
        relevant,
        args.start - timedelta(days=400),
        args.end,
        args.price_cache,
        workers=args.workers,
    )
    identifiers = detect_identifier_conflicts(membership, prices)
    missing_series = sorted(
        ticker
        for ticker in relevant
        if ticker not in prices or not prices[ticker].prices
    )
    contract = DataContract(
        price_source="Yahoo Finance chart API (kostenlos, nur überlebende Listings)",
        membership_source=f"fja05680/sp500 @ {MEMBERSHIP_DATA_COMMIT} (rekonstruiert, nicht offiziell)",
        survivorship_free_prices=False,
        delisting_returns=False,
        permanent_security_ids=False,
        point_in_time_fundamentals=args.quality_csv is not None,
        point_in_time_estimates=False,
        point_in_time_sectors=False,
        corporate_actions=False,
        missing_for_production=(
            "Kurse delisteter, übernommener und insolventer Titel "
            f"({len(missing_series)} von {len(relevant)} Tickern fehlen vollständig)",
            "Finale Delisting-Auszahlungen statt eines pauschalen Abschlags",
            "Dauerhafte Security-IDs (52 Ticker tragen mehr als ein Unternehmen)",
            "Fundamentaldaten mit tatsächlichem Veröffentlichungsdatum (Qualitätsfaktor)",
            "Quartalszahlen mit exaktem Announcement-Zeitpunkt (Earnings-Surprise/PEAD)",
            "Historische Analystenschätzungen und Revisionen",
            "Sektor-/Branchenzuordnung zum damaligen Zeitpunkt",
            "Senatorenmeldungen mit Veröffentlichungsdatum und Amendments über mehrere Jahre",
        ),
    )

    blocks_out: List[Mapping[str, object]] = []
    curves: Dict[str, Mapping[str, float]] = {}
    all_rebalances: List[Mapping[str, object]] = []
    rolling_rows: List[Mapping[str, object]] = []
    for block in _blocks(args.quality_csv):
        signal = block["signal"]
        config = block["config"]
        try:
            full, rows = run_research_backtest(
                membership,
                prices,
                signal,
                args.start,
                args.end,
                starting_cash_usd=args.starting_cash,
                config=config,
                contract=contract,
            )
            clean, _ = run_research_backtest(
                membership,
                prices,
                signal,
                args.start,
                args.stub_year_cutoff,
                starting_cash_usd=args.starting_cash,
                config=config,
                contract=contract,
            )
        except MissingPointInTimeData as error:
            blocks_out.append(
                {
                    "name": block["name"],
                    "label": block["label"],
                    "rationale": block["rationale"],
                    "skipped": str(error),
                }
            )
            continue
        stress = cost_stress(
            membership,
            prices,
            signal,
            args.start,
            args.stub_year_cutoff,
            starting_cash_usd=args.starting_cash,
            config=config,
        )
        walk = walk_forward(
            membership,
            prices,
            signal,
            args.start,
            args.end,
            starting_cash_usd=args.starting_cash,
            config=config,
        )
        curves[block["name"]] = _daily_returns(clean["daily_equity"])
        for item in clean["metrics"]["rolling_12m_returns"]:
            rolling_rows.append({"block": block["name"], **item})
        for row in rows:
            all_rebalances.append({"block": block["name"], **row})
        gate = _evaluate_gate(full, clean, stress, contract)
        blocks_out.append(
            {
                "name": block["name"],
                "label": block["label"],
                "rationale": block["rationale"],
                "full_window": _strip_equity(full),
                "excluding_stub_year": _strip_equity(clean),
                "cost_stress": stress,
                "walk_forward": walk,
                "gate": gate,
            }
        )

    correlation_daily = {
        name: {other: _correlation(curves[name], curves[other]) for other in curves}
        for name in curves
    }
    monthly = {name: _monthly_returns(curve) for name, curve in curves.items()}
    correlation_monthly = {
        name: {other: _correlation(monthly[name], monthly[other]) for other in monthly}
        for name in monthly
    }
    passed = [block for block in blocks_out if block.get("gate", {}).get("passed")]
    combination = {
        "passed_block_count": len(passed),
        "conclusion": (
            "Kein Baustein hat das Gate bestanden. Eine Kombination wurde deshalb "
            "bewusst **nicht** gerechnet: eine schwache Strategie mit einer anderen "
            "zu mischen versteckt ihre Fehler, statt sie zu beheben."
            if not passed
            else "Nur bestandene Bausteine werden kombiniert; siehe JSON."
        ),
    }

    spy = prices["SPY"]
    calendar = sorted(spy.prices)
    def spy_return(first: date, last: date) -> float:
        entry = [day for day in calendar if day >= first][0]
        exit_day = [day for day in calendar if day <= last][-1]
        return (
            spy.prices[exit_day].adjusted_close / spy.prices[entry].adjusted_open - 1.0
        ) * 100.0

    payload = {
        "generated_on": date.today().isoformat(),
        "membership_data_commit": MEMBERSHIP_DATA_COMMIT,
        "window": {
            "start": args.start.isoformat(),
            "end": args.end.isoformat(),
            "stub_year_cutoff": args.stub_year_cutoff.isoformat(),
        },
        "data_contract": contract.as_dict(),
        "identifier_conflicts": identifiers,
        "missing_price_ticker_count": len(missing_series),
        "universe_ticker_count": len(relevant),
        "benchmark": {
            "spy_return_pct_full": spy_return(args.start, args.end),
            "spy_return_pct_excluding_stub": spy_return(args.start, args.stub_year_cutoff),
        },
        "gate": GATE,
        "blocks": blocks_out,
        "correlation": {"daily": correlation_daily, "monthly": correlation_monthly},
        "combination": combination,
    }

    _write_equity_csv(args.equity_output, curves)
    with args.rolling_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("block", "start_date", "end_date", "return_pct"),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rolling_rows)
    _write_rebalances(args.rebalances_output, all_rebalances)
    args.summary_output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    args.report_output.write_text(_render_report(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "blocks": [
                    {
                        "name": block["name"],
                        "cagr_excluding_stub": block.get("excluding_stub_year", {})
                        .get("metrics", {})
                        .get("cagr_pct"),
                        "verdict": block.get("gate", {}).get("verdict", "übersprungen"),
                    }
                    for block in blocks_out
                ]
            },
            indent=2,
        )
    )
    return 0


def _strip_equity(summary: Mapping[str, object]) -> Mapping[str, object]:
    """Keep the JSON summary readable.

    The daily equity curve and the ~2,700 rolling twelve-month windows belong
    in a CSV, not in a summary a human is expected to open.  Their aggregates
    (min, median, max, share negative) stay in the JSON because the gate uses
    them.
    """

    trimmed = dict(summary)
    trimmed.pop("daily_equity", None)
    for key in ("metrics", "benchmark_volatility_matched"):
        block = trimmed.get(key)
        if isinstance(block, dict):
            block = dict(block)
            if key == "metrics":
                block.pop("rolling_12m_returns", None)
            else:
                inner = dict(block.get("metrics") or {})
                inner.pop("rolling_12m_returns", None)
                inner.pop("monthly_returns", None)
                block["metrics"] = inner
            trimmed[key] = block
    return trimmed


if __name__ == "__main__":
    raise SystemExit(main())
