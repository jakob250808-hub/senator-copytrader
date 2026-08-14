#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from senator_copytrader.backtest import load_or_download_prices  # noqa: E402
from senator_copytrader.factor_backtest import (  # noqa: E402
    FactorConfig,
    load_membership_intervals,
    load_quality_snapshots,
    run_factor_backtest,
)


MEMBERSHIP_DATA_COMMIT = "c31ac3cc56f28cf9a02b4e694eff7ceab596a0ff"
REBALANCE_FIELDS = (
    "signal_date",
    "execution_date",
    "market_regime",
    "selected",
    "selected_count",
    "eligible_count",
    "exclusions",
    "turnover_usd",
    "costs_usd",
    "cash_after_usd",
)
COST_SENSITIVITY = (0.0, 0.001, 0.0025, 0.005)
WALK_FORWARD_TRAINING_YEARS = 5


def _write_rebalances(path: Path, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=REBALANCE_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            rendered = dict(row)
            rendered["exclusions"] = json.dumps(
                row["exclusions"], sort_keys=True, separators=(",", ":")
            )
            writer.writerow(rendered)


def _render_report(payload: dict) -> str:
    main = payload["main"]
    coverage = main["data_coverage"]
    annual = main["annual_returns"]
    quality_enabled = main["parameters"]["quality_weight"] > 0.0
    lines = [
        "# Momentum-/Qualitäts-Research-Backtest",
        "",
        "Stand: {}".format(date.today().strftime("%d.%m.%Y")),
        "",
        "## Ergebnis des ersten Forschungsbausteins",
        "",
        (
            "Der vorläufige, ungehebelte Lauf erzielt von {} bis {} insgesamt "
            "{:+.2f} %, entsprechend {:+.2f} % CAGR. Der maximale Drawdown liegt "
            "bei {:.2f} %. SPY erzielt im selben Fenster {:+.2f} %."
        ).format(
            main["market_start"],
            main["market_end"],
            main["return_pct"],
            main["cagr_pct"],
            main["max_drawdown_pct"],
            main["spy_return_pct"],
        ),
        "",
        (
            "Es wurden {} monatliche Rebalances ausgeführt, davon {} im "
            "Defensivmodus. Durchschnittlich waren {:.0f} USD investiert; der "
            "Umsatz betrug {:.0f} USD und die modellierten Kosten {:.0f} USD."
        ).format(
            main["rebalance_count"],
            main["regime_off_rebalance_count"],
            main["average_invested_usd"],
            main["turnover_usd"],
            main["transaction_costs_usd"],
        ),
        "",
        "Der fundamentale Qualitätsfaktor ist {}. Ohne eine Point-in-Time-Datei "
        "werden keine heutigen Fundamentaldaten rückwirkend eingesetzt.".format(
            "aktiv" if quality_enabled else "noch deaktiviert"
        ),
        "",
        (
            "**Research-Gate nicht bestanden:** Gefordert waren zunächst "
            "mindestens 25 % robuste ungehebelte CAGR bei höchstens 20 % "
            "Drawdown. Gemessen wurden {:+.2f} % CAGR und {:.2f} % Drawdown. "
            "Dieser Baustein wird daher weder gehebelt noch in die "
            "Paper-Konfiguration übernommen."
        ).format(main["cagr_pct"], main["max_drawdown_pct"]),
        "",
        "## Jahresergebnisse",
        "",
        "| Jahr | Rendite | Jahresendwert |",
        "|---|---:|---:|",
    ]
    for item in annual:
        year_label = item["year"]
        if (
            int(item["year"]) == date.fromisoformat(main["market_end"]).year
            and not main["market_end"].endswith("12-31")
        ):
            year_label += " (Teiljahr bis {})".format(main["market_end"][5:])
        lines.append(
            "| {} | {:+.2f} % | {:.2f} USD |".format(
                year_label, item["return_pct"], item["ending_value_usd"]
            )
        )
    lines.extend(
        [
            "",
            "## Rollierende 5-Jahre-/1-Jahr-Prüfung",
            "",
            "Die Regeln bleiben in allen Fenstern unverändert; das Fünfjahresfenster "
            "dient nur zur Diagnose und wählt keine nachträglich beste Variante.",
            "",
            "| Testjahr | Training-CAGR | Training-DD | Test | Test-DD | SPY-Test |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for item in payload["walk_forward"]["windows"]:
        lines.append(
            "| {} | {:+.2f} % | {:.2f} % | {:+.2f} % | {:.2f} % | {:+.2f} % |".format(
                item["test_year"],
                item["training_cagr_pct"],
                item["training_max_drawdown_pct"],
                item["test_return_pct"],
                item["test_max_drawdown_pct"],
                item["test_spy_return_pct"],
            )
        )
    walk = payload["walk_forward"]
    lines.extend(
        [
            "",
            (
                "Über die {} Testfenster sind {} positiv und {} schlagen SPY. "
                "Die unabhängig zusammengesetzte Testreihe ergibt {:+.2f} %. "
                "2026 ist nur bis 30.06. enthalten."
            ).format(
                len(walk["windows"]),
                walk["positive_test_count"],
                walk["tests_beating_spy_count"],
                walk["compounded_test_return_pct"],
            ),
        ]
    )
    lines.extend(
        [
            "",
            "## Kostenstress",
            "",
            "| Kosten je Seite | CAGR | Gesamtrendite | Drawdown |",
            "|---:|---:|---:|---:|",
        ]
    )
    for key, item in payload["cost_sensitivity"].items():
        lines.append(
            "| {:.2f} % | {:+.2f} % | {:+.2f} % | {:.2f} % |".format(
                float(key) * 100.0,
                item["cagr_pct"],
                item["return_pct"],
                item["max_drawdown_pct"],
            )
        )
    lines.extend(
        [
            "",
            "## Datenqualität und Aussagegrenze",
            "",
            (
                "Die historische S&P-500-Mitgliedschaft enthält im Testfenster "
                "{} Ticker. Für {} davon ({:.1f} %) waren beim kostenlosen "
                "Kursanbieter Daten verfügbar; {} fehlten vollständig."
            ).format(
                coverage["membership_ticker_count"],
                coverage["available_price_ticker_count"],
                coverage["available_price_share"] * 100.0,
                coverage["missing_price_ticker_count"],
            ),
            "",
            (
                "Der Mitgliedschaftsdatensatz ist ein MIT-lizenziertes, aus "
                "öffentlichen Änderungen rekonstruiertes Forschungsdataset am "
                "Commit `{}`. Er ist keine offizielle S&P-Datei. Yahoo-Daten "
                "decken insbesondere delistete oder umbenannte Titel nicht "
                "zuverlässig ab; dadurch bleibt Survivorship- und Delisting-Bias."
            ).format(payload["membership_data_commit"]),
            "",
            (
                "Dieser Lauf prüft daher Strategiecode, Look-ahead-Schutz, "
                "Kosten- und Risikomechanik. Er ist **kein Freigabesignal für "
                "50–70 % Renditeziel oder Hebel**. Das nächste Gate verlangt "
                "vollständige Point-in-Time-Preise inklusive Delistings sowie "
                "Fundamentaldaten mit tatsächlichem Veröffentlichungsdatum."
            ),
            "",
            "## Feste Regeln – nicht nachträglich optimiert",
            "",
            "- S&P-500-Mitgliedschaft am Signaltag, nicht heutige Mitglieder.",
            "- Monatlicher Einstieg am nächsten Tages-Open.",
            "- 12-zu-1-Momentum: 252 Handelstage Rückblick, letzte 21 ausgelassen.",
            "- Nur Kurse ab 5 USD und durchschnittlich mindestens 10 Mio. USD Tagesumsatz.",
            "- Höchstens 20 Titel, gleich gewichtet, maximal 10 % je Titel.",
            "- Cash bei SPY unter seinem 200-Tage-Durchschnitt.",
            "- Long-only, kein Hebel, keine Änderung der Senatoren-Paper-Config.",
            "",
        ]
    )
    return "\n".join(lines)


def _walk_forward(
    membership,
    prices,
    start: date,
    end: date,
    starting_cash: float,
    quality,
    config: FactorConfig,
) -> dict:
    windows = []
    compounded = 1.0
    first_test_year = start.year + WALK_FORWARD_TRAINING_YEARS
    for test_year in range(first_test_year, end.year + 1):
        test_start = max(start, date(test_year, 1, 1))
        test_end = min(end, date(test_year, 12, 31))
        if test_start > test_end:
            continue
        training_start = max(start, date(test_year - WALK_FORWARD_TRAINING_YEARS, 1, 1))
        training_end = date(test_year - 1, 12, 31)
        training, _ = run_factor_backtest(
            membership,
            prices,
            training_start,
            training_end,
            starting_cash_usd=starting_cash,
            quality_snapshots=quality,
            config=config,
        )
        test, _ = run_factor_backtest(
            membership,
            prices,
            test_start,
            test_end,
            starting_cash_usd=starting_cash,
            quality_snapshots=quality,
            config=config,
        )
        compounded *= 1.0 + test["return_pct"] / 100.0
        windows.append(
            {
                "test_year": test_year,
                "training_start": training["market_start"],
                "training_end": training["market_end"],
                "training_cagr_pct": training["cagr_pct"],
                "training_max_drawdown_pct": training["max_drawdown_pct"],
                "test_start": test["market_start"],
                "test_end": test["market_end"],
                "test_return_pct": test["return_pct"],
                "test_max_drawdown_pct": test["max_drawdown_pct"],
                "test_spy_return_pct": test["spy_return_pct"],
            }
        )
    return {
        "training_years": WALK_FORWARD_TRAINING_YEARS,
        "windows": windows,
        "compounded_test_return_pct": (compounded - 1.0) * 100.0,
        "positive_test_count": sum(item["test_return_pct"] > 0.0 for item in windows),
        "tests_beating_spy_count": sum(
            item["test_return_pct"] > item["test_spy_return_pct"] for item in windows
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the point-in-time membership momentum/quality research backtest."
    )
    parser.add_argument(
        "--membership",
        type=Path,
        default=PROJECT_ROOT / "work" / "sp500-history" / "sp500_ticker_start_end.csv",
    )
    parser.add_argument("--quality-csv", type=Path)
    parser.add_argument(
        "--price-cache",
        type=Path,
        default=PROJECT_ROOT / "work" / "factor_prices.json",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=PROJECT_ROOT / "factor_backtest_summary.json",
    )
    parser.add_argument(
        "--rebalances-output",
        type=Path,
        default=PROJECT_ROOT / "factor_backtest_rebalances.csv",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=PROJECT_ROOT / "factor_backtest_report.md",
    )
    parser.add_argument("--start", type=date.fromisoformat, default=date(2015, 1, 2))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 6, 30))
    parser.add_argument("--starting-cash", type=float, default=100_000.0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    membership = load_membership_intervals(args.membership)
    relevant_tickers = {
        item.ticker
        for item in membership
        if item.start_date <= args.end
        and (item.end_date is None or item.end_date >= args.start)
    }
    prices = load_or_download_prices(
        relevant_tickers,
        args.start - timedelta(days=400),
        args.end,
        args.price_cache,
        workers=args.workers,
    )
    quality = load_quality_snapshots(args.quality_csv) if args.quality_csv else {}
    config = FactorConfig(quality_weight=0.30 if quality else 0.0)
    main_summary, rows = run_factor_backtest(
        membership,
        prices,
        args.start,
        args.end,
        starting_cash_usd=args.starting_cash,
        quality_snapshots=quality,
        config=config,
    )
    sensitivity = {}
    for cost in COST_SENSITIVITY:
        summary, _ = run_factor_backtest(
            membership,
            prices,
            args.start,
            args.end,
            starting_cash_usd=args.starting_cash,
            quality_snapshots=quality,
            config=replace(config, cost_per_side=cost),
        )
        sensitivity[f"{cost:.4f}"] = {
            "return_pct": summary["return_pct"],
            "cagr_pct": summary["cagr_pct"],
            "max_drawdown_pct": summary["max_drawdown_pct"],
            "transaction_costs_usd": summary["transaction_costs_usd"],
        }
    payload = {
        "membership_data_commit": MEMBERSHIP_DATA_COMMIT,
        "quality_data": str(args.quality_csv) if args.quality_csv else None,
        "main": main_summary,
        "cost_sensitivity": sensitivity,
        "walk_forward": _walk_forward(
            membership,
            prices,
            args.start,
            args.end,
            args.starting_cash,
            quality,
            config,
        ),
    }
    _write_rebalances(args.rebalances_output, rows)
    args.summary_output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.report_output.write_text(_render_report(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
