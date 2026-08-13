import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from senator_copytrader.backtest import (
    Candidate,
    Extraction,
    PricePoint,
    PriceSeries,
    load_purchase_candidates,
    run_backtest,
)


class BacktestTests(unittest.TestCase):
    def test_daily_file_received_date_is_signal_date_and_duplicates_are_removed(self):
        filing = {
            "first_name": "Sheldon",
            "last_name": "Whitehouse",
            "ptr_link": "https://example.test/filing/1",
            "date_recieved": "01/04/2021",
            "transactions": [
                {
                    "transaction_date": "12/01/2020",
                    "ticker": '<a href="https://finance.yahoo.com/q?s=AAPL">AAPL</a>',
                    "asset_type": "Stock",
                    "type": "Purchase",
                    "amount": "$1,001 - $15,000",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "one.json").write_text(json.dumps([filing]), encoding="utf-8")
            (path / "duplicate.json").write_text(json.dumps([filing]), encoding="utf-8")
            result = load_purchase_candidates(path)

        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].disclosure_date, date(2021, 1, 4))
        self.assertEqual(result.candidates[0].ticker, "AAPL")
        self.assertEqual(result.filings_by_senator["Sheldon Whitehouse"], 1)

    def test_entry_uses_next_spy_trading_day_not_securitys_next_available_day(self):
        candidate = Candidate(
            "id", "Sheldon Whitehouse", date(2021, 1, 8), date(2020, 12, 1),
            "ABC", "Stock", "$1,001 - $15,000"
        )
        extraction = Extraction([candidate], {}, {})
        spy_days = {
            date(2021, 1, 8): PricePoint(100, 100),
            date(2021, 1, 11): PricePoint(100, 100),
            date(2021, 4, 12): PricePoint(110, 110),
        }
        prices = {
            "SPY": PriceSeries("SPY", "ETF", spy_days),
            "ABC": PriceSeries(
                "ABC", "EQUITY", {date(2021, 1, 12): PricePoint(10, 10), date(2021, 4, 12): PricePoint(11, 11)}
            ),
        }

        row = run_backtest(extraction, prices)[0]

        self.assertEqual(row["status"], "excluded")
        self.assertEqual(row["exclusion_reason"], "no_security_price_on_entry_day")

    def test_90_calendar_day_return_uses_adjusted_prices_and_costs(self):
        candidate = Candidate(
            "id", "Sheldon Whitehouse", date(2021, 1, 8), date(2020, 12, 1),
            "ABC", "Stock", "$1,001 - $15,000"
        )
        extraction = Extraction([candidate], {}, {})
        entry_day = date(2021, 1, 11)
        exit_day = date(2021, 4, 12)
        prices = {
            "SPY": PriceSeries(
                "SPY", "ETF", {entry_day: PricePoint(100, 100), exit_day: PricePoint(110, 110)}
            ),
            "ABC": PriceSeries(
                "ABC", "EQUITY", {entry_day: PricePoint(20, 20), exit_day: PricePoint(24, 24)}
            ),
        }

        row = run_backtest(extraction, prices)[0]

        self.assertEqual(row["status"], "scored")
        self.assertEqual(row["entry_date"], "2021-01-11")
        self.assertEqual(row["exit_date"], "2021-04-12")
        self.assertAlmostEqual(float(row["strategy_return_pct"]), 19.7601, places=4)
        self.assertAlmostEqual(float(row["spy_return_pct"]), 9.7801, places=4)
        self.assertAlmostEqual(float(row["excess_return_pct_points"]), 9.98, places=4)

    def test_provider_asset_type_rejects_mutual_funds(self):
        day = date(2021, 1, 11)
        candidate = Candidate(
            "id", "Susan M Collins", date(2021, 1, 8), date(2020, 12, 1),
            "FUNDX", "Stock", "$1,001 - $15,000"
        )
        extraction = Extraction([candidate], {}, {})
        prices = {
            "SPY": PriceSeries("SPY", "ETF", {day: PricePoint(100, 100)}),
            "FUNDX": PriceSeries("FUNDX", "MUTUALFUND", {day: PricePoint(10, 10)}),
        }

        row = run_backtest(extraction, prices)[0]

        self.assertEqual(row["status"], "excluded")
        self.assertEqual(row["exclusion_reason"], "provider_instrument_type_MUTUALFUND")


if __name__ == "__main__":
    unittest.main()
