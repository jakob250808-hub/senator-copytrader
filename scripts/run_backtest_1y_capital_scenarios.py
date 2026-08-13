#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from senator_copytrader.backtest import load_or_download_prices  # noqa: E402
from senator_copytrader.config import load_config  # noqa: E402
from senator_copytrader.portfolio_backtest import (  # noqa: E402
    load_kadoa_signals,
    run_portfolio_backtest,
    summarize_order_sensitivity,
    write_portfolio_results,
)


SCENARIOS = (
    ("current_3k_7k_20k_5k", "Ausgangsstand 3k/7k, 20k/5k", 3_000, 7_000, 20_000, 5_000),
    ("required_3k_7k_40k_10k", "3k/7k, 40k/10k", 3_000, 7_000, 40_000, 10_000),
    ("required_3k_7k_60k_15k", "3k/7k, 60k/15k", 3_000, 7_000, 60_000, 15_000),
    ("required_3k_7k_80k_20k", "3k/7k, 80k/20k", 3_000, 7_000, 80_000, 20_000),
    ("required_3k_7k_100k_30k", "3k/7k, 100k/30k", 3_000, 7_000, 100_000, 30_000),
    ("aligned_2k_6k_60k_16k", "2k/6k, 60k/16k", 2_000, 6_000, 60_000, 16_000),
    ("aligned_2_5k_7_5k_60k_15k", "2,5k/7,5k, 60k/15k", 2_500, 7_500, 60_000, 15_000),
    ("aligned_3k_6k_40k_12k", "3k/6k, 40k/12k", 3_000, 6_000, 40_000, 12_000),
    ("aligned_3k_6k_60k_15k", "3k/6k, 60k/15k", 3_000, 6_000, 60_000, 15_000),
    ("aligned_3k_6k_80k_24k", "3k/6k, 80k/24k", 3_000, 6_000, 80_000, 24_000),
    ("aligned_3k_6k_99k_30k", "3k/6k, 99k/30k", 3_000, 6_000, 99_000, 30_000),
)
SELECTED_SCENARIO = "aligned_2k_6k_60k_16k"
COST_SENSITIVITY = (0.0, 0.001, 0.0025, 0.005)


def _parameters(scenario, starting_cash: float, cost_per_side: float = 0.001):
    _, _, buy, position, portfolio, daily = scenario
    return {
        "starting_cash_usd": starting_cash,
        "buy_notional_usd": float(buy),
        "max_position_usd": float(position),
        "max_portfolio_usd": float(portfolio),
        "max_daily_notional_usd": float(daily),
        "cost_per_side": cost_per_side,
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "max_holding_days": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare cash-only capital utilization scenarios."
    )
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "config.example.json"
    )
    parser.add_argument(
        "--filer-dir",
        type=Path,
        default=PROJECT_ROOT / "work" / "congress-trading-monitor" / "public" / "data" / "filer",
    )
    parser.add_argument(
        "--price-cache",
        type=Path,
        default=PROJECT_ROOT / "work" / "backtest_1y_prices.json",
    )
    parser.add_argument(
        "--results-output",
        type=Path,
        default=PROJECT_ROOT / "backtest_1y_capital_results.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=PROJECT_ROOT / "backtest_1y_capital_summary.json",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=PROJECT_ROOT / "backtest_1y_capital_report.md",
    )
    parser.add_argument("--start", type=date.fromisoformat, default=date(2025, 8, 13))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 8, 13))
    parser.add_argument("--starting-cash", type=float, default=100_000.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--order-sensitivity-runs", type=int, default=200)
    args = parser.parse_args()

    config = load_config(str(args.config))
    signals = load_kadoa_signals(
        args.filer_dir, config.source.politicians, args.start, args.end
    )
    if not signals:
        parser.error("no watchlist signals found in the requested filing-date window")
    tickers = {
        signal.ticker
        for signal in signals
        if not signal.initial_exclusion and signal.ticker
    }
    prices = load_or_download_prices(
        tickers,
        args.start - timedelta(days=7),
        args.end,
        args.price_cache,
        workers=args.workers,
    )

    summaries = {}
    selected_rows = None
    selected_scenario = None
    for scenario in SCENARIOS:
        name, label, *_ = scenario
        parameters = _parameters(scenario, args.starting_cash)
        summary, rows = run_portfolio_backtest(
            signals, prices, args.start, args.end, **parameters
        )
        summary = dict(summary)
        summary["label"] = label
        summary["parameters"] = parameters
        summary["order_sensitivity"] = summarize_order_sensitivity(
            signals,
            prices,
            args.start,
            args.end,
            runs=args.order_sensitivity_runs,
            **parameters,
        )
        summaries[name] = summary
        if name == SELECTED_SCENARIO:
            selected_rows = rows
            selected_scenario = scenario

    if selected_rows is None or selected_scenario is None:
        raise RuntimeError("selected scenario was not run")

    cost_sensitivity = {}
    for cost in COST_SENSITIVITY:
        parameters = _parameters(selected_scenario, args.starting_cash, cost)
        summary, _ = run_portfolio_backtest(
            signals, prices, args.start, args.end, **parameters
        )
        cost_sensitivity[f"{cost:.4f}"] = {
            "cost_per_side_pct": cost * 100.0,
            "return_pct": summary["return_pct"],
            "liquidation_return_pct": summary["liquidation_return_pct"],
            "ending_value_usd": summary["ending_value_usd"],
            "turnover_usd": summary["turnover_usd"],
        }

    payload = {
        "data_commit": "e51eacba83bb0188aa687fa4e5576dcafd90907f",
        "selected_scenario": SELECTED_SCENARIO,
        "scenario_order": [scenario[0] for scenario in SCENARIOS],
        "scenarios": summaries,
        "selected_cost_sensitivity": cost_sensitivity,
    }
    write_portfolio_results(args.results_output, selected_rows)
    args.summary_output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.report_output.write_text(
        _render_report(args.start, args.end, payload), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _render_report(start: date, end: date, payload: dict) -> str:
    scenarios = payload["scenarios"]
    selected = scenarios[payload["selected_scenario"]]
    sensitivity = selected["order_sensitivity"]
    baseline = scenarios["current_3k_7k_20k_5k"]
    monthly = selected["monthly_return_summary"]
    parameters = selected["parameters"]
    buys_per_day = int(
        parameters["max_daily_notional_usd"] / parameters["buy_notional_usd"]
    )
    buys_per_ticker = int(
        parameters["max_position_usd"] / parameters["buy_notional_usd"]
    )
    lines = [
        "# Cash-only-Szenarien für aggressivere Kapitalnutzung",
        "",
        "Stand: {}".format(date.today().strftime("%d.%m.%Y")),
        "",
        "Zeitraum: {} bis {}; Startkapital: 100.000 USD; keine Margin.".format(start, end),
        "",
        "## Ergebnis und Auswahl",
        "",
        (
            "Ausgewählt wird für das Paper-Trading **{:.0f} USD je Kauf, {:.0f} USD "
            "je Ticker, {:.0f} USD Portfolio- und {:.0f} USD Tageslimit**. Alle "
            "Geldbeträge sind durch den Kaufbetrag teilbar; damit passen {} Käufe "
            "exakt in das Tagesbudget und {} Käufe exakt in das Tickerlimit."
        ).format(
            parameters["buy_notional_usd"], parameters["max_position_usd"],
            parameters["max_portfolio_usd"], parameters["max_daily_notional_usd"],
            buys_per_day, buys_per_ticker,
        ),
        "",
        (
            "Der deterministische Lauf erzielt {:+.2f} %, über 200 Reihenfolgen "
            "liegt der Median bei {:+.2f} % und P05–P95 bei {:+.2f} bis {:+.2f} %. "
            "Der schlechteste Lauf liegt bei {:+.2f} %, der maximale Drawdown des "
            "Hauptlaufs bei {:.2f} %."
        ).format(
            selected["return_pct"],
            sensitivity["median_return_pct"],
            sensitivity["p05_return_pct"],
            sensitivity["p95_return_pct"],
            sensitivity["min_return_pct"],
            selected["max_drawdown_pct"],
        ),
        "",
        (
            "Durchschnittlich sind {:.0f} USD statt zuvor {:.0f} USD investiert; "
            "die Spitze steigt von {:.0f} auf {:.0f} USD. Damit ist die geforderte "
            "höhere Kapitalnutzung tatsächlich erreicht."
        ).format(
            selected["average_invested_usd"],
            baseline["average_invested_usd"],
            baseline["peak_invested_usd"],
            selected["peak_invested_usd"],
        ),
        "",
        (
            "Gegenüber der ähnlich ausgelasteten 3k/6k-Variante verbessert der "
            "kleinere Kaufbetrag den schlechtesten Reihenfolgenlauf von {:+.2f} "
            "auf {:+.2f} %, P05 von {:+.2f} auf {:+.2f} % und den schlimmsten "
            "Drawdown aus 200 Läufen von {:.2f} auf {:.2f} %. Das ist der Grund "
            "für die Auswahl; nicht der höchste einzelne Backtestwert."
        ).format(
            scenarios["aligned_3k_6k_60k_15k"]["order_sensitivity"]["min_return_pct"],
            sensitivity["min_return_pct"],
            scenarios["aligned_3k_6k_60k_15k"]["order_sensitivity"]["p05_return_pct"],
            sensitivity["p05_return_pct"],
            scenarios["aligned_3k_6k_60k_15k"]["order_sensitivity"]["worst_max_drawdown_pct"],
            sensitivity["worst_max_drawdown_pct"],
        ),
        "",
        (
            "Der risikogleiche SPY-Mix erzielt {:+.2f} %, voller SPY {:+.2f} %. "
            "Die gewählte Variante liegt im Hauptlauf {:+.2f} Prozentpunkte über "
            "dem risikogleichen Vergleich."
        ).format(
            selected["risk_matched_spy_return_pct"],
            selected["spy_100k_return_pct"],
            selected["return_pct"] - selected["risk_matched_spy_return_pct"],
        ),
        "",
        "## Szenarienmatrix – Rendite und Risiko",
        "",
        "| Szenario | Hauptlauf | Min | P05 | Median | P95 | Max | Drawdown | Risiko-SPY |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in payload["scenario_order"]:
        item = scenarios[name]
        order = item["order_sensitivity"]
        lines.append(
            "| {} | {:+.2f} % | {:+.2f} % | {:+.2f} % | {:+.2f} % | {:+.2f} % | {:+.2f} % | {:.2f} % | {:+.2f} % |".format(
                item["label"], item["return_pct"], order["min_return_pct"],
                order["p05_return_pct"], order["median_return_pct"],
                order["p95_return_pct"], order["max_return_pct"],
                item["max_drawdown_pct"], item["risk_matched_spy_return_pct"],
            )
        )
    lines.extend([
        "",
        "## Kapitalbindung, Skips und Konzentration im Hauptlauf",
        "",
        "| Szenario | Ø investiert | Spitze | Umsatz | Tageslimit | Portfolio | Ticker | Cash | Top-Senator | Top-Ticker |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for name in payload["scenario_order"]:
        item = scenarios[name]
        skips = item["limit_skip_counts"]
        lines.append(
            "| {} | {:.0f} USD | {:.0f} USD | {:.0f} USD | {} | {} | {} | {} | {:.1f} % | {:.1f} % |".format(
                item["label"], item["average_invested_usd"], item["peak_invested_usd"],
                item["turnover_usd"], skips["daily_notional_limit"],
                skips["portfolio_limit"], skips["position_limit"], skips["cash_limit"],
                item["largest_senator_buy_share"] * 100.0,
                item["largest_ticker_buy_share"] * 100.0,
            )
        )
    best = monthly["best_month"]
    worst = monthly["worst_month"]
    lines.extend([
        "",
        "## Monatsrenditen der gewählten Variante",
        "",
        "| Monat | Monatsende | Rendite | Kontowert |",
        "|---|---|---:|---:|",
    ])
    for item in selected["monthly_returns"]:
        lines.append(
            "| {} | {} | {:+.2f} % | {:.2f} USD |".format(
                item["month"], item["month_end"], item["return_pct"], item["ending_value_usd"]
            )
        )
    lines.extend([
        "",
        (
            "Bester Monat: {} mit {:+.2f} %; schlechtester Monat: {} mit {:+.2f} %. "
            "Median: {:+.2f} %. Positiv waren {} von {} Monaten, **mindestens 7 % "
            "erreichte {} Monat(e)**. Der erste und letzte Monat sind wegen der "
            "Stichtage 13.08. nur Teilmonate. Das Ziel stabiler 7 % pro Monat ist "
            "damit nicht belegt."
        ).format(
            best["month"], best["return_pct"], worst["month"], worst["return_pct"],
            monthly["median_return_pct"], monthly["positive_month_count"],
            monthly["month_count"], monthly["months_at_or_above_7_pct"],
        ),
        "",
        "## Kosten-/Slippage-Sensitivität der gewählten Variante",
        "",
        "| Kosten je Seite | Rendite | Liquidationsrendite | Endwert |",
        "|---:|---:|---:|---:|",
    ])
    for key in sorted(payload["selected_cost_sensitivity"], key=float):
        item = payload["selected_cost_sensitivity"][key]
        lines.append(
            "| {:.2f} % | {:+.2f} % | {:+.2f} % | {:.2f} USD |".format(
                item["cost_per_side_pct"], item["return_pct"],
                item["liquidation_return_pct"], item["ending_value_usd"],
            )
        )
    top_senators = list(selected["executed_buys_by_senator"].items())[:5]
    top_tickers = list(selected["executed_buys_by_ticker"].items())[:5]
    lines.extend([
        "",
        "## Konzentration der gewählten Variante",
        "",
        "Ausgeführte Käufe nach den fünf größten Senatoren: {}.".format(
            ", ".join("{} {}".format(name, count) for name, count in top_senators)
        ),
        "",
        "Ausgeführte Käufe nach den fünf größten Tickern: {}.".format(
            ", ".join("{} {}".format(name, count) for name, count in top_tickers)
        ),
        "",
        "## Grenzen",
        "",
        "- Die Watchlist wurde anhand desselben Jahres gewählt: Dieser Test ist in-sample und enthält Universums-Look-ahead.",
        "- Die Variante wurde aus derselben Szenarienmatrix gewählt. Das ist kein unabhängiger Out-of-sample-Nachweis und keine Renditezusage.",
        "- Gleichzeitige Signale bleiben reihenfolgeabhängig; deshalb stehen neben dem Hauptlauf 200 deterministische Zufallsreihenfolgen.",
        "- Kadoa ist nicht der Live-Quiver-Feed. Tickerweite Verkäufe können Positionen schließen, die ein anderer Senator eröffnet hat.",
        "- 0,10 % je Seite ist der Hauptfall; 0,25 % und 0,50 % je Seite zeigen konservativere Reibung. Steuern und Cashzins fehlen.",
        "- Kosten können an einer harten Portfolio-Grenze ändern, welches nachfolgende Signal noch angenommen wird; die Sensitivität muss deshalb nicht streng monoton verlaufen.",
        "- Stop-Loss, Take-Profit und Haltedauer bleiben deaktiviert; sie werden nicht noch einmal an diesem einen Jahr optimiert.",
        "- Das Portfolio bleibt cash-only: maximal 100.000 USD planmäßiges Portfoliolimit, keine Margin und keine Live-Orders.",
        "",
        "Die vollständigen Entscheidungen der gewählten Variante stehen in `backtest_1y_capital_results.csv`, alle Kennzahlen in `backtest_1y_capital_summary.json`.",
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
