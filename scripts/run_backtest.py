#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from senator_copytrader.backtest import (  # noqa: E402
    load_or_download_prices,
    load_purchase_candidates,
    run_backtest,
    summarize_results,
    write_results,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Senate disclosure-date 90-day backtest."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=PROJECT_ROOT / "work" / "senate-stock-watcher-data" / "data",
    )
    parser.add_argument(
        "--price-cache",
        type=Path,
        default=PROJECT_ROOT / "work" / "backtest_prices.json",
    )
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "backtest_results.csv"
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    extraction = load_purchase_candidates(args.data_dir)
    eligible = [candidate for candidate in extraction.candidates if not candidate.initial_exclusion]
    if not eligible:
        parser.error("no eligible stock-purchase candidates found")
    start = min(candidate.disclosure_date for candidate in eligible) - timedelta(days=7)
    end = max(candidate.disclosure_date for candidate in eligible) + timedelta(days=110)
    prices = load_or_download_prices(
        (candidate.ticker for candidate in eligible),
        start,
        end,
        args.price_cache,
        workers=args.workers,
    )
    rows = run_backtest(extraction, prices)
    write_results(args.output, rows)
    print(json.dumps(summarize_results(extraction, rows), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
