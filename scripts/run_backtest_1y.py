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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a one-year, money-limit-aware watchlist backtest."
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
        "--output", type=Path, default=PROJECT_ROOT / "backtest_1y_results.csv"
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=PROJECT_ROOT / "backtest_1y_summary.json",
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
    strategy = config.strategy
    summary, rows = run_portfolio_backtest(
        signals,
        prices,
        args.start,
        args.end,
        starting_cash_usd=args.starting_cash,
        buy_notional_usd=strategy.buy_notional_usd,
        max_position_usd=strategy.max_position_usd,
        max_portfolio_usd=strategy.max_portfolio_usd,
        max_daily_notional_usd=strategy.max_daily_notional_usd,
        stop_loss_pct=strategy.stop_loss_pct,
        take_profit_pct=strategy.take_profit_pct,
        max_holding_days=strategy.max_holding_days,
    )
    summary["order_sensitivity"] = summarize_order_sensitivity(
        signals,
        prices,
        args.start,
        args.end,
        runs=args.order_sensitivity_runs,
        starting_cash_usd=args.starting_cash,
        buy_notional_usd=strategy.buy_notional_usd,
        max_position_usd=strategy.max_position_usd,
        max_portfolio_usd=strategy.max_portfolio_usd,
        max_daily_notional_usd=strategy.max_daily_notional_usd,
        stop_loss_pct=strategy.stop_loss_pct,
        take_profit_pct=strategy.take_profit_pct,
        max_holding_days=strategy.max_holding_days,
    )
    write_portfolio_results(args.output, rows)
    rendered_summary = json.dumps(summary, indent=2, sort_keys=True)
    args.summary_output.write_text(rendered_summary + "\n", encoding="utf-8")
    print(rendered_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
