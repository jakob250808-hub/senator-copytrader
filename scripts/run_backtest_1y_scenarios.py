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
    {
        "name": "current_limits_no_exits",
        "label": "Aktuelle Limits, Exits aus",
        "max_portfolio_usd": 20_000.0,
        "max_daily_notional_usd": 5_000.0,
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "max_holding_days": None,
    },
    {
        "name": "aggressive_c_no_exits",
        "label": "C: 40k/10k, Exits aus",
        "max_portfolio_usd": 40_000.0,
        "max_daily_notional_usd": 10_000.0,
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "max_holding_days": None,
    },
    {
        "name": "aggressive_c_sl12_hold90",
        "label": "C: SL 12 %, Haltedauer 90 Tage",
        "max_portfolio_usd": 40_000.0,
        "max_daily_notional_usd": 10_000.0,
        "stop_loss_pct": 12.0,
        "take_profit_pct": None,
        "max_holding_days": 90,
    },
    {
        "name": "aggressive_c_sl12_tp25_hold90",
        "label": "C: SL 12 %, TP 25 %, 90 Tage",
        "max_portfolio_usd": 40_000.0,
        "max_daily_notional_usd": 10_000.0,
        "stop_loss_pct": 12.0,
        "take_profit_pct": 25.0,
        "max_holding_days": 90,
    },
    {
        "name": "aggressive_c_sl15_tp30_hold120",
        "label": "C: SL 15 %, TP 30 %, 120 Tage",
        "max_portfolio_usd": 40_000.0,
        "max_daily_notional_usd": 10_000.0,
        "stop_loss_pct": 15.0,
        "take_profit_pct": 30.0,
        "max_holding_days": 120,
    },
)
PRIMARY_SCENARIO = "aggressive_c_no_exits"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare current limits with aggressive one-year scenarios."
    )
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "config.example.json"
    )
    parser.add_argument(
        "--filer-dir",
        type=Path,
        default=(
            PROJECT_ROOT
            / "work"
            / "congress-trading-monitor"
            / "public"
            / "data"
            / "filer"
        ),
    )
    parser.add_argument(
        "--price-cache",
        type=Path,
        default=PROJECT_ROOT / "work" / "backtest_1y_prices.json",
    )
    parser.add_argument(
        "--results-output",
        type=Path,
        default=PROJECT_ROOT / "backtest_1y_aggressive_results.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=PROJECT_ROOT / "backtest_1y_aggressive_summary.json",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=PROJECT_ROOT / "backtest_1y_aggressive_report.md",
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
    primary_rows = None
    for scenario in SCENARIOS:
        parameters = {
            "starting_cash_usd": args.starting_cash,
            "buy_notional_usd": config.strategy.buy_notional_usd,
            "max_position_usd": config.strategy.max_position_usd,
            "max_portfolio_usd": scenario["max_portfolio_usd"],
            "max_daily_notional_usd": scenario["max_daily_notional_usd"],
            "stop_loss_pct": scenario["stop_loss_pct"],
            "take_profit_pct": scenario["take_profit_pct"],
            "max_holding_days": scenario["max_holding_days"],
        }
        summary, rows = run_portfolio_backtest(
            signals, prices, args.start, args.end, **parameters
        )
        summary = dict(summary)
        summary["label"] = scenario["label"]
        summary["parameters"] = parameters
        summary["order_sensitivity"] = summarize_order_sensitivity(
            signals,
            prices,
            args.start,
            args.end,
            runs=args.order_sensitivity_runs,
            **parameters,
        )
        summaries[scenario["name"]] = summary
        if scenario["name"] == PRIMARY_SCENARIO:
            primary_rows = rows

    if primary_rows is None:
        raise RuntimeError("primary scenario was not run")
    write_portfolio_results(args.results_output, primary_rows)
    payload = {
        "primary_scenario": PRIMARY_SCENARIO,
        "scenario_order": [scenario["name"] for scenario in SCENARIOS],
        "scenarios": summaries,
    }
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
    primary = scenarios[PRIMARY_SCENARIO]
    lines = [
        "# Aggressiver Einjahres-Backtest – Variante C",
        "",
        "Stand: {}".format(date.today().strftime("%d.%m.%Y")),
        "",
        "Zeitraum: {} bis {}".format(start.isoformat(), end.isoformat()),
        "",
        "## Kurzurteil",
        "",
        (
            "Die verlangte Variante C investiert mit 40.000 USD Portfolio- und "
            "10.000 USD Tageslimit aggressiver, lässt Kaufgröße (1.000 USD) und "
            "Tickerlimit (3.000 USD) aber unverändert. Ohne neue Exit-Regeln endet "
            "sie bei **{:.2f} USD ({:+.2f} %)**; der maximale Drawdown beträgt "
            "**{:.2f} %**."
        ).format(
            primary["ending_value_usd"],
            primary["return_pct"],
            primary["max_drawdown_pct"],
        ),
        "",
        (
            "Durchschnittlich waren {:.2f} USD investiert, maximal {:.2f} USD. "
            "Die Live-Config wurde nicht verändert; dies ist ausschließlich eine "
            "historische Paper-Simulation."
        ).format(primary["average_invested_usd"], primary["peak_invested_usd"]),
        "",
        (
            "Der C-Hauptlauf liegt {:.2f} Prozentpunkte über seinem risikogleichen "
            "40.000-USD-SPY-Mix ({:+.2f} %), aber klar unter 100 % SPY "
            "({:+.2f} %). Über 200 Signalreihenfolgen beträgt der Median {:+.2f} % "
            "und das 5.–95. Perzentil {:+.2f} bis {:+.2f} %."
        ).format(
            primary["return_pct"] - primary["risk_matched_spy_return_pct"],
            primary["risk_matched_spy_return_pct"],
            primary["spy_100k_return_pct"],
            primary["order_sensitivity"]["median_return_pct"],
            primary["order_sensitivity"]["p05_return_pct"],
            primary["order_sensitivity"]["p95_return_pct"],
        ),
        "",
        "## Szenarienvergleich",
        "",
        (
            "| Szenario | Rendite | Liquidation | Max. Drawdown | Ø investiert | "
            "Käufe | Regel-Exits | Reihenfolge P05–P95 |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario_name in payload["scenario_order"]:
        summary = scenarios[scenario_name]
        sensitivity = summary["order_sensitivity"]
        lines.append(
            "| {} | {:+.2f} % | {:+.2f} % | {:.2f} % | {:.0f} USD | "
            "{:.0f} USD | {} | {:+.2f} bis {:+.2f} % |".format(
                summary["label"],
                summary["return_pct"],
                summary["liquidation_return_pct"],
                summary["max_drawdown_pct"],
                summary["average_invested_usd"],
                summary["total_buy_notional_usd"],
                summary["strategy_exit_count"],
                sensitivity["p05_return_pct"],
                sensitivity["p95_return_pct"],
            )
        )
    lines.extend(
        [
            "",
            "## Einordnung der Exit-Regeln",
            "",
            (
                "Die Exit-Schwellen sind Forschungsvarianten, keine nachträglich "
                "gewählten Live-Parameter. Stop-Loss, Take-Profit und maximale "
                "Haltedauer werden im Backtest am adjustierten Open jedes "
                "Handelstags vor neuen Signalen geprüft. Intraday-Auslösungen und "
                "exakte Stop-Preise lassen sich mit Tagesdaten nicht simulieren."
            ),
            "",
            (
                "Alle neuen Config-Felder bleiben standardmäßig `null`. Ein "
                "Take-Profit kann starke Gewinner abschneiden; eine maximale "
                "Haltedauer kann dagegen gebundenes Kapital freigeben. Deshalb "
                "wird keine Variante allein aufgrund dieses einen In-sample-Jahres "
                "automatisch aktiviert."
            ),
            "",
            (
                "In diesem Fenster senken alle drei getesteten Exit-Sets die "
                "Rendite deutlich. Sie reduzieren zwar teilweise den Drawdown, "
                "verkaufen aber die wenigen starken Gewinner zu früh und erzeugen "
                "viel höheren Umsatz. Das spricht für implementierte, aber vorerst "
                "deaktivierte Regeln."
            ),
            "",
            "## Unveränderte Grenzen der Aussage",
            "",
            "- Die 30er-Watchlist wurde anhand desselben Jahres ausgewählt: Universums-Look-ahead.",
            "- Verkäufe aufgrund von Senatorensignalen wirken weiterhin tickerweit, nicht senatorbezogen.",
            "- Gleichzeitige Meldungen bleiben reihenfolgeabhängig; die Tabelle zeigt deshalb P05 bis P95 aus 200 Reihenfolgen.",
            "- Kadoa ist nicht die Live-Quiver-API; Parsing und Feedreihenfolge können abweichen.",
            "- Kosten/Slippage betragen weiterhin 0,10 % je Seite; Steuern und Cashzins fehlen.",
            "",
            "Die vollständigen Entscheidungen des primären C-Laufs stehen in "
            "`backtest_1y_aggressive_results.csv`, alle Szenariokennzahlen in "
            "`backtest_1y_aggressive_summary.json`.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
