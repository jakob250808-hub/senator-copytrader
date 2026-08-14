import csv
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from senator_copytrader.backtest import PricePoint, PriceSeries
from senator_copytrader.factor_backtest import (
    FactorConfig,
    MembershipInterval,
    QualitySnapshot,
    load_membership_intervals,
    run_factor_backtest,
)


def price_series(symbol, closes, instrument_type="EQUITY"):
    return PriceSeries(
        symbol,
        instrument_type,
        {
            day: PricePoint(value, value, 100_000_000.0)
            for day, value in closes.items()
        },
    )


class FactorBacktestTests(unittest.TestCase):
    def setUp(self):
        self.days = [date(2020, 1, 1) + timedelta(days=index) for index in range(310)]

    def prices(self, aaa_recent=20.0, bbb_recent=15.0, spy_last=101.0):
        spy = {day: 100.0 for day in self.days}
        spy[self.days[299]] = spy_last
        aaa = {day: 10.0 for day in self.days}
        bbb = {day: 10.0 for day in self.days}
        for index in range(278, len(self.days)):
            aaa[self.days[index]] = aaa_recent
            bbb[self.days[index]] = bbb_recent
        return {
            "SPY": price_series("SPY", spy, "ETF"),
            "AAA": price_series("AAA", aaa),
            "BBB": price_series("BBB", bbb),
        }

    def config(self, **overrides):
        values = {
            "holdings": 1,
            "momentum_long_days": 252,
            "momentum_skip_days": 21,
            "trend_sma_days": 20,
            "liquidity_lookback_days": 10,
            "minimum_average_dollar_volume_usd": 0.0,
            "cost_per_side": 0.0,
        }
        values.update(overrides)
        return FactorConfig(**values)

    def test_membership_loader_preserves_multiple_intervals_and_open_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "membership.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["ticker", "start_date", "end_date"])
                writer.writerow(["AAA", "2020-01-01", "2020-01-31"])
                writer.writerow(["AAA", "2020-03-01", ""])
            result = load_membership_intervals(path)

        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].active_on(date(2020, 1, 31)))
        self.assertFalse(result[0].active_on(date(2020, 2, 1)))
        self.assertTrue(result[1].active_on(date(2030, 1, 1)))

    def test_uses_12_to_1_momentum_known_before_execution(self):
        membership = [
            MembershipInterval("AAA", self.days[0]),
            MembershipInterval("BBB", self.days[0]),
        ]
        prices = self.prices()
        # A huge execution-day move in BBB must not affect the prior-close signal.
        execution_day = self.days[300]
        bbb = dict(prices["BBB"].prices)
        bbb[execution_day] = PricePoint(1_000.0, 1_000.0, 100_000_000.0)
        prices["BBB"] = PriceSeries("BBB", "EQUITY", bbb)

        _, rows = run_factor_backtest(
            membership,
            prices,
            execution_day,
            self.days[-1],
            config=self.config(),
        )

        self.assertEqual(rows[0]["selected"], "AAA")
        self.assertEqual(rows[0]["signal_date"], self.days[299].isoformat())

    def test_market_regime_moves_portfolio_to_cash(self):
        membership = [MembershipInterval("AAA", self.days[0])]
        prices = self.prices(spy_last=50.0)

        summary, rows = run_factor_backtest(
            membership,
            prices,
            self.days[300],
            self.days[-1],
            config=self.config(),
        )

        self.assertEqual(rows[0]["market_regime"], "off")
        self.assertEqual(rows[0]["selected_count"], 0)
        self.assertEqual(summary["ending_value_usd"], 100_000.0)

    def test_quality_ignores_snapshot_published_after_signal(self):
        membership = [
            MembershipInterval("AAA", self.days[0]),
            MembershipInterval("BBB", self.days[0]),
        ]
        prices = self.prices(aaa_recent=20.0, bbb_recent=20.0)
        signal_day = self.days[299]
        quality = {
            "AAA": (
                QualitySnapshot("AAA", signal_day - timedelta(days=10), 0.20, 0.40, 0.10),
            ),
            "BBB": (
                QualitySnapshot("BBB", signal_day - timedelta(days=10), 0.05, 0.10, 0.80),
                QualitySnapshot("BBB", signal_day + timedelta(days=1), 0.90, 0.90, 0.00),
            ),
        }

        _, rows = run_factor_backtest(
            membership,
            prices,
            self.days[300],
            self.days[-1],
            quality_snapshots=quality,
            config=self.config(quality_weight=1.0),
        )

        self.assertEqual(rows[0]["selected"], "AAA")

    def test_costs_are_charged_on_monthly_rebalance(self):
        membership = [MembershipInterval("AAA", self.days[0])]
        prices = self.prices()

        summary, _ = run_factor_backtest(
            membership,
            prices,
            self.days[300],
            self.days[-1],
            config=self.config(cost_per_side=0.01),
        )

        self.assertGreater(summary["transaction_costs_usd"], 0.0)
        self.assertLess(summary["ending_value_usd"], 100_000.0)

    def test_non_equity_member_is_not_selected(self):
        membership = [MembershipInterval("AAA", self.days[0])]
        prices = self.prices()
        prices["AAA"] = PriceSeries("AAA", "ETF", prices["AAA"].prices)

        summary, rows = run_factor_backtest(
            membership,
            prices,
            self.days[300],
            self.days[-1],
            config=self.config(),
        )

        self.assertEqual(rows[0]["selected_count"], 0)
        self.assertEqual(rows[0]["exclusions"]["not_equity"], 1)
        self.assertEqual(summary["ending_value_usd"], 100_000.0)

    def test_index_removal_forces_exit_before_next_month(self):
        membership = [MembershipInterval("AAA", self.days[0], self.days[302])]
        prices = self.prices()

        summary, _ = run_factor_backtest(
            membership,
            prices,
            self.days[300],
            self.days[-1],
            config=self.config(),
        )

        self.assertEqual(summary["forced_membership_exit_count"], 1)
        self.assertEqual(summary["ending_positions"], {})


if __name__ == "__main__":
    unittest.main()
