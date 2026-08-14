"""Tests for the research backtester.

The emphasis is on the failure modes the methodology review found in the first
factor backtester: look-ahead, delisted holdings that never die, index
deletions, cost accounting and portfolio arithmetic.  Each test is written so
that reintroducing the original bug makes it fail.
"""

from __future__ import annotations

import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from senator_copytrader.backtest import PricePoint, PriceSeries  # noqa: E402
from senator_copytrader.factor_backtest import (  # noqa: E402
    MembershipInterval,
    QualitySnapshot,
)
from senator_copytrader.research_backtest import (  # noqa: E402
    DataContract,
    EngineConfig,
    MarketData,
    SecurityId,
    SignalContext,
    benchmark_paths,
    detect_identifier_conflicts,
    performance_metrics,
    run_research_backtest,
)
from senator_copytrader.strategies import (  # noqa: E402
    MissingPointInTimeData,
    make_momentum_with_quality,
    momentum_12_1,
    short_term_reversal,
)


def business_days(start: date, count: int):
    days = []
    day = start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def series(
    symbol: str,
    days,
    closes,
    *,
    opens=None,
    dollar_volume: float = 50_000_000.0,
    instrument_type: str = "EQUITY",
) -> PriceSeries:
    opens = opens if opens is not None else closes
    return PriceSeries(
        symbol=symbol,
        instrument_type=instrument_type,
        prices={
            day: PricePoint(float(open_price), float(close), dollar_volume)
            for day, open_price, close in zip(days, opens, closes)
        },
    )


class LookAheadGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.days = business_days(date(2020, 1, 1), 30)
        prices = {
            "SPY": series("SPY", self.days, [100.0 + i for i in range(30)]),
            "AAA": series("AAA", self.days, [10.0 + i for i in range(30)]),
        }
        self.market = MarketData(prices, self.days)
        self.context = SignalContext(
            signal_day=self.days[10],
            signal_index=10,
            calendar=self.days,
            prices=prices,
            eligible=("AAA",),
            benchmark=prices["SPY"],
            market=self.market,
        )

    def test_closes_refuse_future_days(self) -> None:
        with self.assertRaises(ValueError):
            self.context.closes("AAA", 0, 11)

    def test_aligned_returns_refuse_future_days(self) -> None:
        with self.assertRaises(ValueError):
            self.context.aligned_returns("AAA", 0, 11)

    def test_volume_lookup_refuses_future_days(self) -> None:
        with self.assertRaises(ValueError):
            self.context.average_dollar_volume("AAA", 0, 11)

    def test_closes_stop_at_the_signal_day(self) -> None:
        closes = self.context.closes("AAA", 8, 10)
        self.assertEqual(closes, (18.0, 19.0, 20.0))


class ExecutionTest(unittest.TestCase):
    """A signal formed on day t must trade at the open of day t+1."""

    def setUp(self) -> None:
        self.days = business_days(date(2020, 1, 1), 300)
        # AAA doubles over the first year, BBB is flat.
        self.prices = {
            "SPY": series("SPY", self.days, [100.0] * 300, opens=[100.0] * 300),
            "AAA": series(
                "AAA",
                self.days,
                [10.0 + 0.05 * i for i in range(300)],
                opens=[9.0 + 0.05 * i for i in range(300)],
            ),
        }
        self.membership = (MembershipInterval("AAA", date(2019, 1, 1), None),)

    def test_buys_at_the_next_open_not_the_signal_close(self) -> None:
        config = EngineConfig(
            holdings=1,
            max_position_weight=1.0,
            trend_sma_days=None,
            cost_per_side=0.0,
            minimum_average_dollar_volume_usd=0.0,
        )
        start = self.days[260]
        summary, rows = run_research_backtest(
            self.membership,
            self.prices,
            momentum_12_1,
            start,
            self.days[-1],
            starting_cash_usd=1_000.0,
            config=config,
        )
        self.assertTrue(rows)
        first = rows[0]
        execution_day = date.fromisoformat(str(first["execution_date"]))
        signal_day = date.fromisoformat(str(first["signal_date"]))
        self.assertLess(signal_day, execution_day)
        open_price = self.prices["AAA"].prices[execution_day].adjusted_open
        close_price = self.prices["AAA"].prices[execution_day].adjusted_close
        self.assertNotAlmostEqual(open_price, close_price)
        expected_shares = 1_000.0 / open_price
        # Ending value is shares * final close plus (zero) residual cash.
        final_close = self.prices["AAA"].prices[self.days[-1]].adjusted_close
        self.assertAlmostEqual(
            float(summary["metrics"]["ending_value_usd"]),
            expected_shares * final_close,
            places=4,
        )


class DelistingTest(unittest.TestCase):
    """A provider series that simply stops must not become an immortal asset."""

    def setUp(self) -> None:
        self.days = business_days(date(2020, 1, 1), 320)
        self.stop_index = 280
        self.prices = {
            "SPY": series("SPY", self.days, [100.0] * 320),
            "AAA": series(
                "AAA",
                self.days[: self.stop_index],
                [10.0 + 0.05 * i for i in range(self.stop_index)],
            ),
        }
        # Still a member on paper long after the data stops — exactly the case
        # a survivorship-biased provider produces for an acquired company.
        self.membership = (MembershipInterval("AAA", date(2019, 1, 1), None),)
        self.config = EngineConfig(
            holdings=1,
            max_position_weight=1.0,
            trend_sma_days=None,
            cost_per_side=0.0,
            minimum_average_dollar_volume_usd=0.0,
            max_stale_trading_days=5,
            delisting_haircut=0.30,
        )

    def test_position_is_liquidated_with_a_haircut(self) -> None:
        summary, _ = run_research_backtest(
            self.membership,
            self.prices,
            momentum_12_1,
            self.days[260],
            self.days[-1],
            starting_cash_usd=1_000.0,
            config=self.config,
        )
        self.assertEqual(summary["delisting_exit_count"], 1)
        self.assertGreater(float(summary["delisting_modelled_loss_usd"]), 0.0)
        event = summary["exit_events"][0]
        self.assertEqual(event["reason"], "delisted_or_data_stop")
        exit_day = date.fromisoformat(str(event["date"]))
        last_bar = self.days[self.stop_index - 1]
        self.assertGreater((exit_day - last_bar).days, 0)
        # After the exit the account is pure cash, so the value stops moving.
        self.assertAlmostEqual(
            float(summary["metrics"]["ending_value_usd"]),
            float(event["proceeds_usd"]),
            places=6,
        )

    def test_without_the_stale_guard_the_position_would_survive(self) -> None:
        """Documents the size of the bias the guard removes."""

        forgiving = EngineConfig(
            holdings=1,
            max_position_weight=1.0,
            trend_sma_days=None,
            cost_per_side=0.0,
            minimum_average_dollar_volume_usd=0.0,
            max_stale_trading_days=10_000,
            delisting_haircut=0.30,
        )
        with_guard, _ = run_research_backtest(
            self.membership,
            self.prices,
            momentum_12_1,
            self.days[260],
            self.days[-1],
            starting_cash_usd=1_000.0,
            config=self.config,
        )
        without_guard, _ = run_research_backtest(
            self.membership,
            self.prices,
            momentum_12_1,
            self.days[260],
            self.days[-1],
            starting_cash_usd=1_000.0,
            config=forgiving,
        )
        self.assertEqual(without_guard["delisting_exit_count"], 0)
        self.assertGreater(
            float(without_guard["metrics"]["ending_value_usd"]),
            float(with_guard["metrics"]["ending_value_usd"]),
        )
        self.assertGreater(int(without_guard["stale_valuation_day_count"]), 0)


class MembershipTest(unittest.TestCase):
    def setUp(self) -> None:
        self.days = business_days(date(2020, 1, 1), 320)
        self.prices = {
            "SPY": series("SPY", self.days, [100.0] * 320),
            "AAA": series(
                "AAA", self.days, [10.0 + 0.05 * i for i in range(320)]
            ),
            "BBB": series("BBB", self.days, [20.0] * 320),
        }
        self.config = EngineConfig(
            holdings=2,
            max_position_weight=1.0,
            trend_sma_days=None,
            cost_per_side=0.0,
            minimum_average_dollar_volume_usd=0.0,
        )

    def test_non_members_are_never_selected(self) -> None:
        membership = (MembershipInterval("BBB", date(2019, 1, 1), None),)
        _, rows = run_research_backtest(
            membership,
            self.prices,
            momentum_12_1,
            self.days[260],
            self.days[-1],
            config=self.config,
        )
        for row in rows:
            self.assertNotIn("AAA", str(row["selected"]))

    def test_index_deletion_forces_an_exit_outside_the_rebalance(self) -> None:
        deletion_day = self.days[300]
        membership = (
            MembershipInterval("AAA", date(2019, 1, 1), deletion_day),
        )
        summary, _ = run_research_backtest(
            membership,
            self.prices,
            momentum_12_1,
            self.days[260],
            self.days[-1],
            config=self.config,
        )
        self.assertEqual(summary["index_deletion_exit_count"], 1)
        event = summary["exit_events"][0]
        self.assertEqual(event["reason"], "index_deletion")
        self.assertEqual(
            date.fromisoformat(str(event["date"])), self.days[301]
        )

    def test_membership_end_date_is_inclusive(self) -> None:
        day = date(2021, 6, 1)
        interval = MembershipInterval("AAA", date(2020, 1, 1), day)
        self.assertTrue(interval.active_on(day))
        self.assertFalse(interval.active_on(day + timedelta(days=1)))


class CostTest(unittest.TestCase):
    def setUp(self) -> None:
        self.days = business_days(date(2020, 1, 1), 400)
        self.prices = {
            "SPY": series("SPY", self.days, [100.0] * 400),
            "AAA": series("AAA", self.days, [10.0 + 0.05 * i for i in range(400)]),
            "BBB": series("BBB", self.days, [30.0 - 0.01 * i for i in range(400)]),
        }
        self.membership = (
            MembershipInterval("AAA", date(2019, 1, 1), None),
            MembershipInterval("BBB", date(2019, 1, 1), None),
        )

    def _run(self, cost: float):
        config = EngineConfig(
            holdings=1,
            max_position_weight=1.0,
            trend_sma_days=None,
            cost_per_side=cost,
            minimum_average_dollar_volume_usd=0.0,
        )
        summary, _ = run_research_backtest(
            self.membership,
            self.prices,
            momentum_12_1,
            self.days[260],
            self.days[-1],
            config=config,
        )
        return summary

    def test_costs_reduce_the_result_monotonically(self) -> None:
        values = [
            float(self._run(cost)["metrics"]["ending_value_usd"])
            for cost in (0.0, 0.001, 0.0025, 0.005)
        ]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_reported_costs_match_turnover(self) -> None:
        summary = self._run(0.0025)
        self.assertAlmostEqual(
            float(summary["transaction_costs_usd"]),
            float(summary["turnover_usd"]) * 0.0025,
            places=6,
        )

    def test_zero_cost_run_reports_no_cost(self) -> None:
        self.assertAlmostEqual(float(self._run(0.0)["transaction_costs_usd"]), 0.0)


class PortfolioArithmeticTest(unittest.TestCase):
    def setUp(self) -> None:
        self.days = business_days(date(2020, 1, 1), 400)
        self.prices = {"SPY": series("SPY", self.days, [100.0] * 400)}
        self.membership = []
        for index, name in enumerate(["AAA", "BBB", "CCC", "DDD"]):
            self.prices[name] = series(
                self.days and name,
                self.days,
                [10.0 + 0.01 * (index + 1) * i for i in range(400)],
            )
            self.membership.append(MembershipInterval(name, date(2019, 1, 1), None))

    def test_equal_weight_respects_the_position_cap(self) -> None:
        config = EngineConfig(
            holdings=4,
            max_position_weight=0.10,
            trend_sma_days=None,
            cost_per_side=0.0,
            minimum_average_dollar_volume_usd=0.0,
        )
        summary, _ = run_research_backtest(
            tuple(self.membership),
            self.prices,
            momentum_12_1,
            self.days[260],
            self.days[261],
            starting_cash_usd=100_000.0,
            config=config,
        )
        # Four names capped at 10% each leaves 60% in cash.
        self.assertLess(float(summary["average_exposure_pct"]), 45.0)
        self.assertGreater(float(summary["average_exposure_pct"]), 35.0)

    def test_value_is_cash_plus_positions(self) -> None:
        config = EngineConfig(
            holdings=2,
            max_position_weight=0.5,
            trend_sma_days=None,
            cost_per_side=0.0,
            minimum_average_dollar_volume_usd=0.0,
        )
        summary, _ = run_research_backtest(
            tuple(self.membership),
            self.prices,
            momentum_12_1,
            self.days[260],
            self.days[-1],
            starting_cash_usd=100_000.0,
            config=config,
        )
        metrics = summary["metrics"]
        self.assertAlmostEqual(
            float(metrics["total_return_pct"]),
            (float(metrics["ending_value_usd"]) / 100_000.0 - 1.0) * 100.0,
            places=9,
        )
        self.assertGreater(float(summary["average_invested_usd"]), 0.0)


class BenchmarkTest(unittest.TestCase):
    def test_volatility_matched_path_never_levers_up(self) -> None:
        days = business_days(date(2020, 1, 1), 200)
        closes = [100.0 * (1.0 + 0.02 * math.sin(i / 3.0)) for i in range(200)]
        spy = series("SPY", days, closes)
        # A strategy twice as volatile as the benchmark must not push the
        # matched benchmark above full investment.
        strategy = [100_000.0 * (1.0 + 0.04 * math.sin(i / 3.0)) for i in range(200)]
        paths = benchmark_paths(days, spy, 100_000.0, 0.0, strategy)
        self.assertLessEqual(paths["volatility_matched_weight"][0], 1.0)

        calm = [100_000.0 * (1.0 + 0.005 * math.sin(i / 3.0)) for i in range(200)]
        calm_paths = benchmark_paths(days, spy, 100_000.0, 0.0, calm)
        self.assertLess(calm_paths["volatility_matched_weight"][0], 1.0)


class MetricsTest(unittest.TestCase):
    def test_worst_year_and_positive_year_count(self) -> None:
        days = business_days(date(2020, 1, 1), 780)
        values = []
        value = 100_000.0
        for index, day in enumerate(days):
            value *= 1.001 if day.year != 2021 else 0.999
            values.append(value)
        metrics = performance_metrics(days, values, 100_000.0)
        self.assertEqual(metrics["worst_year"]["year"], "2021")
        self.assertLess(float(metrics["worst_year"]["return_pct"]), 0.0)
        self.assertEqual(metrics["positive_year_count"], metrics["year_count"] - 1)
        self.assertIsNotNone(metrics["rolling_12m_median_pct"])

    def test_drawdown_is_negative_and_calmar_uses_it(self) -> None:
        days = business_days(date(2020, 1, 1), 300)
        values = [100_000.0 * (1.0 if i < 150 else 0.8) for i in range(300)]
        metrics = performance_metrics(days, values, 100_000.0)
        self.assertAlmostEqual(float(metrics["max_drawdown_pct"]), -20.0, places=6)
        self.assertLess(float(metrics["calmar_zero_rate"]), 0.0)


class IdentifierTest(unittest.TestCase):
    def test_recycled_ticker_is_reported(self) -> None:
        membership = (
            MembershipInterval("SNDK", date(2006, 4, 20), date(2016, 5, 12)),
            MembershipInterval("SNDK", date(2025, 11, 28), None),
        )
        days = business_days(date(2025, 1, 2), 100)
        prices = {"SNDK": series("SNDK", days, [30.0] * 100)}
        report = detect_identifier_conflicts(membership, prices)
        self.assertEqual(report["recycled_ticker_count"], 1)
        self.assertIn("SNDK", report["recycled_tickers"])

    def test_security_id_is_interval_scoped(self) -> None:
        old = SecurityId("SNDK", date(2006, 4, 20), date(2016, 5, 12))
        new = SecurityId("SNDK", date(2025, 11, 28), None)
        self.assertNotEqual(old.key, new.key)
        self.assertTrue(old.active_on(date(2010, 1, 4)))
        self.assertFalse(new.active_on(date(2010, 1, 4)))


class DataContractTest(unittest.TestCase):
    def test_incomplete_data_marks_the_run_as_a_prototype(self) -> None:
        contract = DataContract(
            price_source="free provider",
            membership_source="reconstructed",
        )
        self.assertTrue(contract.prototype)
        self.assertTrue(contract.as_dict()["prototype"])

    def test_full_data_clears_the_prototype_flag(self) -> None:
        contract = DataContract(
            price_source="vendor",
            membership_source="vendor",
            survivorship_free_prices=True,
            delisting_returns=True,
            permanent_security_ids=True,
            corporate_actions=True,
        )
        self.assertFalse(contract.prototype)


class SignalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.days = business_days(date(2020, 1, 1), 300)
        self.prices = {
            "SPY": series("SPY", self.days, [100.0] * 300),
            "UP": series("UP", self.days, [10.0 + 0.05 * i for i in range(300)]),
            "DOWN": series("DOWN", self.days, [50.0 - 0.05 * i for i in range(300)]),
        }
        self.market = MarketData(self.prices, self.days)
        self.context = SignalContext(
            signal_day=self.days[290],
            signal_index=290,
            calendar=self.days,
            prices=self.prices,
            eligible=("UP", "DOWN"),
            benchmark=self.prices["SPY"],
            market=self.market,
        )

    def test_momentum_prefers_the_riser(self) -> None:
        scores = momentum_12_1(self.context)
        self.assertGreater(scores["UP"], scores["DOWN"])

    def test_short_term_reversal_prefers_the_faller(self) -> None:
        scores = short_term_reversal(self.context, universe_size=2)
        self.assertGreater(scores["DOWN"], scores["UP"])

    def test_quality_signal_refuses_to_run_without_point_in_time_data(self) -> None:
        with self.assertRaises(MissingPointInTimeData):
            make_momentum_with_quality({})

    def test_quality_signal_ignores_snapshots_published_later(self) -> None:
        snapshots = {
            "UP": (
                QualitySnapshot("UP", self.days[299], 0.9, 0.9, 0.1),
            ),
            "DOWN": (
                QualitySnapshot("DOWN", self.days[10], 0.5, 0.5, 0.2),
            ),
        }
        signal = make_momentum_with_quality(snapshots)
        scores = signal(self.context)
        # UP's only snapshot is dated after the signal day, so it must not be
        # scored at all rather than being scored with tomorrow's fundamentals.
        self.assertNotIn("UP", scores)
        self.assertIn("DOWN", scores)


if __name__ == "__main__":
    unittest.main()
