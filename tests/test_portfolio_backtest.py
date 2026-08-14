import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from senator_copytrader.backtest import PricePoint, PriceSeries
from senator_copytrader.portfolio_backtest import (
    PortfolioSignal,
    load_kadoa_signals,
    run_portfolio_backtest,
    summarize_order_sensitivity,
)


def signal(event_id, ticker, filing_day, action="buy", senator="John Boozman"):
    return PortfolioSignal(
        event_id=event_id,
        senator=senator,
        filing_date=filing_day,
        transaction_date=filing_day,
        action=action,
        ticker=ticker,
        asset_type="Stock",
        owner="Self",
        amount_range="$1,001 - $15,000",
    )


class PortfolioBacktestTests(unittest.TestCase):
    def test_kadoa_loader_uses_filing_date_and_resolves_feed_alias(self):
        payload = {
            "filer": {"full_name": "Thomas H Tuberville"},
            "trades": [
                {
                    "id": "inside",
                    "filing_date": "2026-01-10",
                    "transaction_date": "2025-12-01",
                    "transaction_type": "Purchase",
                    "ticker": "XLU",
                    "asset_type": "Stock",
                    "owner": "Self",
                    "amount_range_label": "$1,001 - $15,000",
                },
                {
                    "id": "outside",
                    "filing_date": "2025-01-10",
                    "transaction_date": "2025-01-01",
                    "transaction_type": "Purchase",
                    "ticker": "AAPL",
                    "asset_type": "Stock",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            filer_dir = Path(directory)
            (filer_dir / "senate_tuberville.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            result = load_kadoa_signals(
                filer_dir,
                ["Tommy Tuberville"],
                date(2025, 8, 13),
                date(2026, 8, 13),
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].senator, "Tommy Tuberville")
        self.assertEqual(result[0].filing_date, date(2026, 1, 10))

    def test_kadoa_loader_resolves_initial_based_mitch_mcconnell_name(self):
        payload = {
            "filer": {"full_name": "A. Mitchell McConnell"},
            "trades": [
                {
                    "id": "wfc",
                    "filing_date": "2026-03-19",
                    "transaction_date": "2026-03-01",
                    "transaction_type": "Purchase",
                    "ticker": "WFC",
                    "asset_type": "Stock",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            filer_dir = Path(directory)
            (filer_dir / "senate_mcconnell.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            result = load_kadoa_signals(
                filer_dir,
                ["Mitch McConnell"],
                date(2025, 8, 13),
                date(2026, 8, 13),
            )

        self.assertEqual(result[0].senator, "Mitch McConnell")

    def test_daily_limit_executes_five_of_six_same_day_buys(self):
        filing_day = date(2026, 1, 5)
        execution_day = date(2026, 1, 6)
        tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
        signals = [signal(str(index), ticker, filing_day) for index, ticker in enumerate(tickers)]
        prices = {
            "SPY": PriceSeries(
                "SPY",
                "ETF",
                {
                    execution_day: PricePoint(100, 100),
                    date(2026, 1, 7): PricePoint(100, 100),
                },
            )
        }
        prices.update(
            {
                ticker: PriceSeries(
                    ticker,
                    "EQUITY",
                    {
                        execution_day: PricePoint(10, 10),
                        date(2026, 1, 7): PricePoint(10, 10),
                    },
                )
                for ticker in tickers
            }
        )

        summary, rows = run_portfolio_backtest(
            signals,
            prices,
            execution_day,
            date(2026, 1, 7),
        )

        self.assertEqual(summary["status_counts"]["executed"], 5)
        self.assertEqual(summary["reason_counts"]["daily_notional_limit"], 1)
        self.assertEqual(summary["total_buy_notional_usd"], 5_000.0)
        self.assertEqual([row["status"] for row in rows].count("skipped"), 1)

    def test_sale_closes_position_without_shorting(self):
        first_day = date(2026, 1, 6)
        second_day = date(2026, 1, 7)
        third_day = date(2026, 1, 8)
        signals = [
            signal("buy", "ABC", date(2026, 1, 5)),
            signal("sell", "ABC", first_day, action="sell"),
            signal("extra-sell", "ABC", second_day, action="sell"),
        ]
        prices = {
            "SPY": PriceSeries(
                "SPY",
                "ETF",
                {
                    first_day: PricePoint(100, 100),
                    second_day: PricePoint(100, 100),
                    third_day: PricePoint(100, 100),
                },
            ),
            "ABC": PriceSeries(
                "ABC",
                "EQUITY",
                {
                    first_day: PricePoint(10, 10),
                    second_day: PricePoint(12, 12),
                    third_day: PricePoint(12, 12),
                },
            ),
        }

        summary, rows = run_portfolio_backtest(
            signals, prices, first_day, third_day
        )

        self.assertEqual(rows[0]["status"], "executed")
        self.assertEqual(rows[1]["status"], "executed")
        self.assertEqual(rows[2]["reason"], "no_position")
        self.assertEqual(summary["ending_positions"], {})
        self.assertGreater(summary["ending_value_usd"], 100_000.0)

    def test_position_limit_rejects_fourth_equal_buy(self):
        days = [date(2026, 1, day) for day in range(5, 11)]
        signals = [
            signal(str(index), "ABC", days[index]) for index in range(4)
        ]
        prices = {
            "SPY": PriceSeries(
                "SPY", "ETF", {day: PricePoint(100, 100) for day in days}
            ),
            "ABC": PriceSeries(
                "ABC", "EQUITY", {day: PricePoint(10, 10) for day in days}
            ),
        }

        summary, _ = run_portfolio_backtest(
            signals, prices, days[0], days[-1]
        )

        self.assertEqual(summary["total_buy_notional_usd"], 3_000.0)
        self.assertEqual(summary["reason_counts"]["position_limit"], 1)

    def test_order_sensitivity_reports_cap_dependent_range(self):
        filing_day = date(2026, 1, 5)
        execution_day = date(2026, 1, 6)
        end_day = date(2026, 1, 7)
        signals = [signal("a", "AAA", filing_day), signal("b", "BBB", filing_day)]
        prices = {
            "SPY": PriceSeries(
                "SPY",
                "ETF",
                {
                    execution_day: PricePoint(100, 100),
                    end_day: PricePoint(100, 100),
                },
            ),
            "AAA": PriceSeries(
                "AAA",
                "EQUITY",
                {
                    execution_day: PricePoint(10, 10),
                    end_day: PricePoint(10, 20),
                },
            ),
            "BBB": PriceSeries(
                "BBB",
                "EQUITY",
                {
                    execution_day: PricePoint(10, 10),
                    end_day: PricePoint(10, 5),
                },
            ),
        }

        result = summarize_order_sensitivity(
            signals,
            prices,
            execution_day,
            end_day,
            runs=20,
            max_daily_notional_usd=1_000.0,
        )

        self.assertEqual(result["runs"], 20)
        self.assertLess(result["min_return_pct"], result["max_return_pct"])
        self.assertIn("median_average_invested_usd", result)
        self.assertIn("median_limit_skip_count", result)

    def test_summary_reports_months_limit_skips_and_buy_concentration(self):
        january = date(2026, 1, 30)
        february = date(2026, 2, 2)
        signals = [
            signal("a", "AAA", date(2026, 1, 29), senator="John Boozman"),
            signal("b", "BBB", date(2026, 1, 29), senator="John Boozman"),
        ]
        prices = {
            "SPY": PriceSeries(
                "SPY",
                "ETF",
                {
                    january: PricePoint(100, 100),
                    february: PricePoint(100, 100),
                },
            ),
            "AAA": PriceSeries(
                "AAA",
                "EQUITY",
                {
                    january: PricePoint(10, 10),
                    february: PricePoint(10, 11),
                },
            ),
            "BBB": PriceSeries(
                "BBB",
                "EQUITY",
                {
                    january: PricePoint(10, 10),
                    february: PricePoint(10, 10),
                },
            ),
        }

        summary, _ = run_portfolio_backtest(
            signals,
            prices,
            january,
            february,
            max_daily_notional_usd=1_000.0,
        )

        self.assertEqual(summary["executed_buy_count"], 1)
        self.assertEqual(summary["executed_buys_by_senator"], {"John Boozman": 1})
        self.assertEqual(summary["executed_buys_by_ticker"], {"AAA": 1})
        self.assertEqual(summary["largest_senator_buy_share"], 1.0)
        self.assertEqual(summary["largest_ticker_buy_share"], 1.0)
        self.assertEqual(summary["limit_skip_counts"]["daily_notional_limit"], 1)
        self.assertEqual(
            [item["month"] for item in summary["monthly_returns"]],
            ["2026-01", "2026-02"],
        )
        self.assertEqual(summary["monthly_return_summary"]["month_count"], 2)
        self.assertGreater(summary["monthly_returns"][1]["return_pct"], 0.0)

    def test_stop_loss_runs_before_signals_and_recycles_portfolio_budget(self):
        first_day = date(2026, 1, 6)
        second_day = date(2026, 1, 7)
        signals = [
            signal("buy-abc", "ABC", date(2026, 1, 5)),
            signal("buy-def", "DEF", first_day),
        ]
        prices = {
            "SPY": PriceSeries(
                "SPY",
                "ETF",
                {
                    first_day: PricePoint(100, 100),
                    second_day: PricePoint(100, 100),
                },
            ),
            "ABC": PriceSeries(
                "ABC",
                "EQUITY",
                {
                    first_day: PricePoint(100, 100),
                    second_day: PricePoint(90, 90),
                },
            ),
            "DEF": PriceSeries(
                "DEF",
                "EQUITY",
                {second_day: PricePoint(50, 50)},
            ),
        }

        summary, rows = run_portfolio_backtest(
            signals,
            prices,
            first_day,
            second_day,
            max_portfolio_usd=1_000.0,
            stop_loss_pct=8.0,
        )

        self.assertEqual(summary["strategy_exit_counts"], {"stop_loss": 1})
        self.assertEqual(rows[0]["status"], "executed")
        self.assertEqual(rows[1]["status"], "executed")
        self.assertEqual(rows[2]["action"], "risk_exit")
        self.assertEqual(rows[2]["execution_date"], second_day.isoformat())
        self.assertEqual(set(summary["ending_positions"]), {"DEF"})


if __name__ == "__main__":
    unittest.main()


class LimitCheckLookAheadTests(unittest.TestCase):
    """The portfolio-limit check must not use a close that has not printed.

    Before the fix, holdings other than the signal ticker were valued at the
    *current day's close* while the trade itself executed at the open.  On a
    day where an existing holding jumps intraday, that made the bot skip a buy
    for a reason it could not have known at the time it placed the order.
    """

    def _prices(self):
        days = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
        spy = PriceSeries(
            "SPY",
            "ETF",
            {day: PricePoint(100.0, 100.0, 1e9) for day in days},
        )
        # HELD is bought on day one at 10.0.  On day two it opens unchanged but
        # closes 50% higher.
        held = PriceSeries(
            "HELD",
            "EQUITY",
            {
                days[0]: PricePoint(10.0, 10.0, 1e8),
                days[1]: PricePoint(10.0, 15.0, 1e8),
                days[2]: PricePoint(15.0, 15.0, 1e8),
            },
        )
        new = PriceSeries(
            "NEW",
            "EQUITY",
            {day: PricePoint(20.0, 20.0, 1e8) for day in days},
        )
        return days, {"SPY": spy, "HELD": held, "NEW": new}

    def test_buy_is_judged_on_open_prices(self):
        days, prices = self._prices()
        signals = (
            signal("held", "HELD", days[0] - timedelta(days=1)),
            signal("new", "NEW", days[0]),
        )
        summary, rows = run_portfolio_backtest(
            signals,
            prices,
            days[0],
            days[-1],
            starting_cash_usd=100_000.0,
            buy_notional_usd=1_000.0,
            max_position_usd=1_000.0,
            max_portfolio_usd=2_000.0,
            max_daily_notional_usd=10_000.0,
            cost_per_side=0.0,
        )
        by_id = {row["event_id"]: row for row in rows}
        self.assertEqual(by_id["held"]["status"], "executed")
        # HELD is worth 1,000 USD at the open of day two, so the 2,000 USD
        # portfolio limit still has room for the 1,000 USD NEW buy.  Valuing
        # HELD at day two's close (1,500 USD) would wrongly skip it.
        self.assertEqual(by_id["new"]["status"], "executed")
        self.assertEqual(by_id["new"]["reason"], "position_opened_or_increased")
        self.assertEqual(summary["limit_skip_counts"]["portfolio_limit"], 0)
