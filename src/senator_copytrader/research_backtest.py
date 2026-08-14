"""Signal-agnostic research backtester with an explicit data contract.

This module exists because the first factor backtester
(:mod:`senator_copytrader.factor_backtest`) hard-wired one strategy and one
reporting shape.  The methodology review documented in ``HANDOFF.md`` found
several issues that cannot be fixed by tuning parameters:

* a held security whose price series simply stops (delisting, acquisition,
  bankruptcy) was valued at its last close forever and was never liquidated,
* the ``ticker`` string was used as the security identity even though the
  membership data contains 52 recycled tickers,
* the reported headline mixed a full-year history with a six-month stub,
* the report lacked the risk statistics that decide the research gate.

Everything here is standard library only so the repository keeps running with
a bare ``python3`` on the maintainer's machine.
"""

from __future__ import annotations

import math
import statistics
from array import array
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta
from typing import (
    Callable,
    Dict,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
)

from .backtest import PriceSeries
from .factor_backtest import MembershipInterval

TRADING_DAYS_PER_YEAR = 252.0


# ---------------------------------------------------------------------------
# Data contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataContract:
    """What the run really had, so no report can silently overstate it.

    ``prototype`` is derived, not hand-set: a run is a prototype unless every
    hard requirement is met.  The renderer refuses to print gate verdicts for a
    prototype run.
    """

    price_source: str
    membership_source: str
    survivorship_free_prices: bool = False
    delisting_returns: bool = False
    permanent_security_ids: bool = False
    point_in_time_fundamentals: bool = False
    point_in_time_estimates: bool = False
    point_in_time_sectors: bool = False
    corporate_actions: bool = False
    missing_for_production: Tuple[str, ...] = ()

    @property
    def prototype(self) -> bool:
        return not (
            self.survivorship_free_prices
            and self.delisting_returns
            and self.permanent_security_ids
            and self.corporate_actions
        )

    def as_dict(self) -> Mapping[str, object]:
        payload = dict(asdict(self))
        payload["prototype"] = self.prototype
        return payload


# ---------------------------------------------------------------------------
# Security identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecurityId:
    """Ticker plus the membership interval that ticker belonged to.

    A bare ticker is not a security.  ``SNDK`` is SanDisk Corporation between
    2006 and 2016 and a different company (the 2025 Western Digital spin-off)
    afterwards.  Keying anything on the plain string silently mixes the two.
    """

    ticker: str
    interval_start: date
    interval_end: Optional[date] = None

    @property
    def key(self) -> str:
        end = self.interval_end.isoformat() if self.interval_end else "open"
        return f"{self.ticker}@{self.interval_start.isoformat()}:{end}"

    def active_on(self, day: date) -> bool:
        return self.interval_start <= day and (
            self.interval_end is None or day <= self.interval_end
        )


def security_ids(
    membership: Sequence[MembershipInterval],
) -> Sequence[SecurityId]:
    return tuple(
        SecurityId(item.ticker, item.start_date, item.end_date) for item in membership
    )


def detect_identifier_conflicts(
    membership: Sequence[MembershipInterval],
    prices: Mapping[str, PriceSeries],
) -> Mapping[str, object]:
    """Find tickers whose price history cannot belong to the listed interval.

    Two distinct problems are reported separately because they have different
    consequences:

    ``recycled`` – the ticker has more than one membership interval, so the
    single price series returned by a ticker-keyed provider covers at best one
    of them.

    ``price_starts_after_membership_end`` – the series we actually hold starts
    after the interval ended, which proves the downloaded prices belong to a
    later, different issuer.
    """

    per_ticker: MutableMapping[str, List[MembershipInterval]] = defaultdict(list)
    for item in membership:
        per_ticker[item.ticker].append(item)

    recycled = sorted(ticker for ticker, items in per_ticker.items() if len(items) > 1)
    wrong_issuer: List[Mapping[str, object]] = []
    covered_late: List[Mapping[str, object]] = []
    # A ticker whose series simply predates the cache window is not a conflict,
    # so only intervals that begin inside the downloaded window are checked for
    # a late start.
    window_start = min(
        (min(series.prices) for series in prices.values() if series.prices),
        default=None,
    )
    for item in membership:
        series = prices.get(item.ticker)
        if series is None or not series.prices:
            continue
        first = min(series.prices)
        if window_start is not None and item.end_date is not None and item.end_date < window_start:
            # The whole interval predates the data; nothing can be checked.
            continue
        if item.end_date is not None and first > item.end_date:
            wrong_issuer.append(
                {
                    "ticker": item.ticker,
                    "membership_start": item.start_date.isoformat(),
                    "membership_end": item.end_date.isoformat(),
                    "price_series_starts": first.isoformat(),
                }
            )
        elif (
            window_start is not None
            and item.start_date > window_start
            and first > item.start_date + timedelta(days=10)
        ):
            covered_late.append(
                {
                    "ticker": item.ticker,
                    "membership_start": item.start_date.isoformat(),
                    "price_series_starts": first.isoformat(),
                }
            )
    return {
        "recycled_ticker_count": len(recycled),
        "recycled_tickers": tuple(recycled),
        "price_series_after_membership_end": tuple(wrong_issuer),
        "price_series_starts_after_index_entry": tuple(covered_late),
    }


# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineConfig:
    holdings: int = 20
    max_position_weight: float = 0.10
    target_exposure: float = 1.0
    cost_per_side: float = 0.001
    rebalance: str = "month"
    minimum_price_usd: float = 5.0
    minimum_average_dollar_volume_usd: float = 10_000_000.0
    liquidity_lookback_days: int = 63
    trend_sma_days: Optional[int] = 200
    #: A held security whose provider series stops for this many *trading*
    #: days is treated as delisted and liquidated.  Without this the engine
    #: carries a dead position at its last close until the end of the run.
    max_stale_trading_days: int = 5
    #: Haircut applied to the final delisting proceeds.  Free providers do not
    #: publish final delisting payouts, so the value is a deliberately
    #: pessimistic placeholder, not a measured number.
    delisting_haircut: float = 0.30
    #: When set, position sizes are scaled so the ex-ante portfolio volatility
    #: matches this annualised target.  Never scales above ``target_exposure``.
    volatility_target: Optional[float] = None
    volatility_lookback_days: int = 63

    def __post_init__(self) -> None:
        if self.holdings < 1:
            raise ValueError("holdings must be positive")
        if self.rebalance not in {"month", "week"}:
            raise ValueError("rebalance must be 'month' or 'week'")
        if not 0.0 < self.target_exposure <= 1.0:
            raise ValueError("target_exposure must be in (0, 1]")
        if not 0.0 < self.max_position_weight <= 1.0:
            raise ValueError("max_position_weight must be in (0, 1]")
        if not 0.0 <= self.cost_per_side <= 0.05:
            raise ValueError("cost_per_side must be between zero and 5%")
        if not 0.0 <= self.delisting_haircut < 1.0:
            raise ValueError("delisting_haircut must be in [0, 1)")
        if self.max_stale_trading_days < 1:
            raise ValueError("max_stale_trading_days must be positive")
        if self.volatility_target is not None and self.volatility_target <= 0.0:
            raise ValueError("volatility_target must be positive when set")


class MarketData:
    """Calendar-aligned view of the raw price mapping.

    Every strategy run walks the same 3,000-day calendar for ~750 tickers.
    Doing that through ``dict`` lookups keyed by :class:`datetime.date` made a
    single residual-momentum pass take three quarters of a minute, which makes
    a seven-window walk-forward impractical.  This class flattens each series
    into calendar-indexed lists once and is shared by every run against the
    same price mapping.
    """

    def __init__(
        self,
        prices: Mapping[str, PriceSeries],
        calendar: Sequence[date],
        benchmark_symbol: str = "SPY",
    ):
        self.prices = prices
        self.benchmark_symbol = benchmark_symbol
        self._regression_cache: Dict[str, Sequence[array]] = {}
        self.calendar = tuple(calendar)
        self.index_of = {day: index for index, day in enumerate(self.calendar)}
        self.closes: Dict[str, List[Optional[float]]] = {}
        self.opens: Dict[str, List[Optional[float]]] = {}
        self.dollar_volume_prefix: Dict[str, List[float]] = {}
        self.observation_prefix: Dict[str, List[int]] = {}
        self.returns: Dict[str, List[Optional[float]]] = {}
        size = len(self.calendar)
        for ticker, series in prices.items():
            closes: List[Optional[float]] = [None] * size
            opens: List[Optional[float]] = [None] * size
            volume_prefix = [0.0] * (size + 1)
            observation_prefix = [0] * (size + 1)
            for day, point in series.prices.items():
                index = self.index_of.get(day)
                if index is None:
                    continue
                closes[index] = point.adjusted_close
                opens[index] = point.adjusted_open
            for index in range(size):
                volume = 0.0
                observed = 0
                if closes[index] is not None:
                    point = series.prices.get(self.calendar[index])
                    if point is not None and point.dollar_volume > 0.0:
                        volume = point.dollar_volume
                        observed = 1
                volume_prefix[index + 1] = volume_prefix[index] + volume
                observation_prefix[index + 1] = observation_prefix[index] + observed
            returns: List[Optional[float]] = [None] * size
            previous_index: Optional[int] = None
            for index in range(size):
                value = closes[index]
                if value is None:
                    continue
                if previous_index is not None and previous_index == index - 1:
                    before = closes[previous_index]
                    if before and before > 0.0:
                        returns[index] = value / before - 1.0
                previous_index = index
            self.closes[ticker] = closes
            self.opens[ticker] = opens
            self.dollar_volume_prefix[ticker] = volume_prefix
            self.observation_prefix[ticker] = observation_prefix
            self.returns[ticker] = returns

    def average_dollar_volume(
        self, ticker: str, first_index: int, last_index: int
    ) -> Tuple[float, int]:
        prefix = self.dollar_volume_prefix.get(ticker)
        counts = self.observation_prefix.get(ticker)
        if prefix is None or counts is None:
            return 0.0, 0
        low = max(0, first_index)
        observed = counts[last_index + 1] - counts[low]
        if observed == 0:
            return 0.0, 0
        total = prefix[last_index + 1] - prefix[low]
        return total / observed, observed

    def _regression_prefix(self, ticker: str) -> Optional[Sequence[array]]:
        """Cumulative sums for an O(1) market-model regression on any window.

        A residual-momentum pass regresses ~500 tickers on the benchmark at
        every rebalance.  Recomputing 230 daily returns per ticker per date
        made a single eleven-year pass take half a minute and a seven-window
        walk-forward unusable.  These prefix sums make each regression a
        constant-time subtraction.
        """

        cached = self._regression_cache.get(ticker)
        if cached is not None:
            return cached
        asset = self.returns.get(ticker)
        bench = self.returns.get(self.benchmark_symbol)
        if asset is None or bench is None:
            return None
        size = len(self.calendar)
        count = array("d", [0.0] * (size + 1))
        sum_a = array("d", [0.0] * (size + 1))
        sum_b = array("d", [0.0] * (size + 1))
        sum_aa = array("d", [0.0] * (size + 1))
        sum_bb = array("d", [0.0] * (size + 1))
        sum_ab = array("d", [0.0] * (size + 1))
        for index in range(size):
            a = asset[index]
            b = bench[index]
            step_count = step_a = step_b = step_aa = step_bb = step_ab = 0.0
            if a is not None and b is not None:
                step_count = 1.0
                step_a, step_b = a, b
                step_aa, step_bb, step_ab = a * a, b * b, a * b
            count[index + 1] = count[index] + step_count
            sum_a[index + 1] = sum_a[index] + step_a
            sum_b[index + 1] = sum_b[index] + step_b
            sum_aa[index + 1] = sum_aa[index] + step_aa
            sum_bb[index + 1] = sum_bb[index] + step_bb
            sum_ab[index + 1] = sum_ab[index] + step_ab
        prefix = (count, sum_a, sum_b, sum_aa, sum_bb, sum_ab)
        self._regression_cache[ticker] = prefix
        return prefix

    def market_model(
        self, ticker: str, first_index: int, last_index: int
    ) -> Optional[Tuple[float, float, float, int]]:
        """``(alpha, beta, residual_std, observations)`` on ``[first, last]``.

        ``alpha`` is the daily intercept of a regression of the security's
        return on the benchmark return; ``residual_std`` is the standard
        deviation of the regression residuals.
        """

        prefix = self._regression_prefix(ticker)
        if prefix is None:
            return None
        count, sum_a, sum_b, sum_aa, sum_bb, sum_ab = prefix
        low = max(0, first_index)
        high = last_index + 1
        n = count[high] - count[low]
        if n < 3:
            return None
        total_a = sum_a[high] - sum_a[low]
        total_b = sum_b[high] - sum_b[low]
        mean_a = total_a / n
        mean_b = total_b / n
        ss_b = (sum_bb[high] - sum_bb[low]) - n * mean_b * mean_b
        ss_a = (sum_aa[high] - sum_aa[low]) - n * mean_a * mean_a
        if ss_b <= 0.0:
            return None
        covariance = (sum_ab[high] - sum_ab[low]) - n * mean_a * mean_b
        beta = covariance / ss_b
        alpha = mean_a - beta * mean_b
        residual_ss = max(0.0, ss_a - beta * beta * ss_b)
        residual_std = math.sqrt(residual_ss / (n - 2)) if n > 2 else 0.0
        return alpha, beta, residual_std, int(n)


@dataclass(frozen=True)
class SignalContext:
    """Everything a signal may look at — and nothing that is dated later."""

    signal_day: date
    signal_index: int
    calendar: Sequence[date]
    prices: Mapping[str, PriceSeries]
    eligible: Sequence[str]
    benchmark: PriceSeries
    market: "MarketData"

    def closes(self, ticker: str, first_index: int, last_index: int) -> Sequence[float]:
        """Adjusted closes for calendar days ``[first_index, last_index]``.

        Missing days are skipped rather than forward filled so that a signal
        can see how thin a series is.  Indices past ``signal_index`` raise:
        that is the look-ahead guard rail, enforced in code rather than by
        convention.
        """

        if last_index > self.signal_index:
            raise ValueError("signal may not read prices after the signal day")
        values = self.market.closes.get(ticker)
        if values is None:
            return ()
        return tuple(
            value
            for value in values[max(0, first_index) : last_index + 1]
            if value is not None
        )

    def average_dollar_volume(
        self, ticker: str, first_index: int, last_index: int
    ) -> float:
        if last_index > self.signal_index:
            raise ValueError("signal may not read volume after the signal day")
        return self.market.average_dollar_volume(ticker, first_index, last_index)[0]

    def market_model(
        self, ticker: str, first_index: int, last_index: int
    ):
        """Constant-time market-model regression over the window."""

        if last_index > self.signal_index:
            raise ValueError("signal may not read prices after the signal day")
        return self.market.market_model(ticker, first_index, last_index)

    def aligned_returns(
        self, ticker: str, first_index: int, last_index: int
    ) -> Tuple[Sequence[float], Sequence[float]]:
        """Daily returns of ``ticker`` and of the benchmark on common days."""

        if last_index > self.signal_index:
            raise ValueError("signal may not read prices after the signal day")
        asset_returns = self.market.returns.get(ticker)
        bench_returns = self.market.returns.get(self.benchmark.symbol or "SPY")
        if asset_returns is None or bench_returns is None:
            return (), ()
        asset: List[float] = []
        bench: List[float] = []
        for index in range(max(1, first_index), last_index + 1):
            a = asset_returns[index]
            b = bench_returns[index]
            if a is None or b is None:
                continue
            asset.append(a)
            bench.append(b)
        return tuple(asset), tuple(bench)


#: A signal maps the context to ``{ticker: score}``; higher scores are bought
#: first.  Returning fewer names than ``holdings`` is allowed and leaves the
#: remainder in cash.
SignalFn = Callable[[SignalContext], Mapping[str, float]]


@dataclass
class _Position:
    shares: float = 0.0
    last_seen: Optional[date] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rebalance_key(day: date, mode: str) -> Tuple[int, int]:
    if mode == "month":
        return (day.year, day.month)
    iso = day.isocalendar()
    return (iso[0], iso[1])


def _eligible_universe(
    signal_day: date,
    signal_index: int,
    active_tickers: Sequence[str],
    market: MarketData,
    config: EngineConfig,
) -> Tuple[Sequence[str], Counter]:
    exclusions: Counter = Counter()
    volume_start = max(0, signal_index - config.liquidity_lookback_days + 1)
    window_length = signal_index - volume_start + 1
    eligible: List[str] = []
    for ticker in active_tickers:
        series = market.prices.get(ticker)
        if series is None or not series.prices:
            exclusions["missing_price_series"] += 1
            continue
        if series.instrument_type != "EQUITY":
            exclusions["not_equity"] += 1
            continue
        close = market.closes[ticker][signal_index]
        if close is None:
            exclusions["no_price_on_signal_day"] += 1
            continue
        if close < config.minimum_price_usd:
            exclusions["minimum_price"] += 1
            continue
        average, observed = market.average_dollar_volume(
            ticker, volume_start, signal_index
        )
        if config.minimum_average_dollar_volume_usd > 0.0 and (
            observed < max(2, window_length // 2)
            or average < config.minimum_average_dollar_volume_usd
        ):
            exclusions["minimum_liquidity"] += 1
            continue
        eligible.append(ticker)
    return tuple(eligible), exclusions


def _trading_days_since_last_bar(
    series: PriceSeries, sorted_days: Sequence[date], day: date, calendar_index: Mapping[date, int]
) -> Optional[int]:
    """How many trading days ago the provider last published a bar."""

    position = bisect_right(sorted_days, day)
    if position == 0:
        return None
    last = sorted_days[position - 1]
    return calendar_index[day] - calendar_index.get(last, calendar_index[day])


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _drawdown(values: Sequence[float]) -> float:
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst


def _daily_returns(values: Sequence[float]) -> Sequence[float]:
    return tuple(
        values[index] / values[index - 1] - 1.0
        for index in range(1, len(values))
        if values[index - 1] > 0.0
    )


def _period_endpoints(
    days: Sequence[date], values: Sequence[float], period: str
) -> Sequence[Tuple[str, date, float]]:
    endpoints: Dict[str, Tuple[date, float]] = {}
    for day, value in zip(days, values):
        key = day.strftime("%Y-%m") if period == "month" else str(day.year)
        endpoints[key] = (day, value)
    return tuple((key, day, value) for key, (day, value) in sorted(endpoints.items()))


def _period_returns(
    days: Sequence[date], values: Sequence[float], period: str, starting_value: float
) -> Sequence[Mapping[str, object]]:
    out: List[Mapping[str, object]] = []
    previous = starting_value
    for key, day, value in _period_endpoints(days, values, period):
        out.append(
            {
                period: key,
                "end_date": day.isoformat(),
                "ending_value_usd": value,
                "return_pct": (value / previous - 1.0) * 100.0,
            }
        )
        previous = value
    return tuple(out)


def _rolling_returns(
    days: Sequence[date], values: Sequence[float], window_days: int
) -> Sequence[Mapping[str, object]]:
    index_by_day = {day: index for index, day in enumerate(days)}
    out: List[Mapping[str, object]] = []
    for index, day in enumerate(days):
        target = day - timedelta(days=window_days)
        earlier = [candidate for candidate in days[: index + 1] if candidate <= target]
        if not earlier:
            continue
        base_index = index_by_day[earlier[-1]]
        base = values[base_index]
        if base <= 0.0:
            continue
        out.append(
            {
                "end_date": day.isoformat(),
                "start_date": days[base_index].isoformat(),
                "return_pct": (values[index] / base - 1.0) * 100.0,
            }
        )
    return tuple(out)


def performance_metrics(
    days: Sequence[date],
    values: Sequence[float],
    starting_value: float,
    benchmark_values: Optional[Sequence[float]] = None,
) -> Mapping[str, object]:
    """The full statistic block the research gate is judged on."""

    ending = values[-1]
    returns = _daily_returns(values)
    mean_daily = statistics.mean(returns) if returns else 0.0
    std_daily = statistics.stdev(returns) if len(returns) > 1 else 0.0
    downside = [value for value in returns if value < 0.0]
    downside_std = statistics.stdev(downside) if len(downside) > 1 else 0.0
    years = max(1.0 / 365.25, (days[-1] - days[0]).days / 365.25)
    cagr = (ending / starting_value) ** (1.0 / years) - 1.0
    # The peak must start at the deposited capital, not at the value after the
    # first rebalance — otherwise a loss on day one is invisible.
    max_dd = _drawdown([starting_value, *values])
    monthly = _period_returns(days, values, "month", starting_value)
    annual = _period_returns(days, values, "year", starting_value)
    rolling = _rolling_returns(days, values, 365)
    monthly_values = [float(item["return_pct"]) for item in monthly]
    annual_values = [float(item["return_pct"]) for item in annual]
    rolling_values = [float(item["return_pct"]) for item in rolling]

    metrics: Dict[str, object] = {
        "start_date": days[0].isoformat(),
        "end_date": days[-1].isoformat(),
        "years": years,
        "starting_value_usd": starting_value,
        "ending_value_usd": ending,
        "total_return_pct": (ending / starting_value - 1.0) * 100.0,
        "cagr_pct": cagr * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "annualized_volatility_pct": std_daily * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0,
        "sharpe_zero_rate": (
            mean_daily / std_daily * math.sqrt(TRADING_DAYS_PER_YEAR) if std_daily else None
        ),
        "sortino_zero_rate": (
            mean_daily / downside_std * math.sqrt(TRADING_DAYS_PER_YEAR)
            if downside_std
            else None
        ),
        "calmar_zero_rate": cagr / abs(max_dd) if max_dd else None,
        "monthly_returns": monthly,
        "annual_returns": annual,
        "rolling_12m_returns": rolling,
        "worst_month": min(monthly, key=lambda item: item["return_pct"], default=None),
        "best_month": max(monthly, key=lambda item: item["return_pct"], default=None),
        "worst_year": min(annual, key=lambda item: item["return_pct"], default=None),
        "best_year": max(annual, key=lambda item: item["return_pct"], default=None),
        "positive_year_count": sum(value > 0.0 for value in annual_values),
        "year_count": len(annual_values),
        "positive_month_count": sum(value > 0.0 for value in monthly_values),
        "month_count": len(monthly_values),
        "rolling_12m_min_pct": min(rolling_values) if rolling_values else None,
        "rolling_12m_median_pct": (
            statistics.median(rolling_values) if rolling_values else None
        ),
        "rolling_12m_max_pct": max(rolling_values) if rolling_values else None,
        "rolling_12m_negative_share": (
            sum(value < 0.0 for value in rolling_values) / len(rolling_values)
            if rolling_values
            else None
        ),
    }

    if benchmark_values is not None:
        bench_annual = _period_returns(days, benchmark_values, "year", starting_value)
        bench_by_year = {item["year"]: float(item["return_pct"]) for item in bench_annual}
        beat = [
            key
            for key, value in ((item["year"], float(item["return_pct"])) for item in annual)
            if key in bench_by_year and value > bench_by_year[key]
        ]
        bench_returns = _daily_returns(benchmark_values)
        bench_std = statistics.stdev(bench_returns) if len(bench_returns) > 1 else 0.0
        metrics.update(
            {
                "benchmark_total_return_pct": (
                    benchmark_values[-1] / starting_value - 1.0
                )
                * 100.0,
                "benchmark_annualized_volatility_pct": bench_std
                * math.sqrt(TRADING_DAYS_PER_YEAR)
                * 100.0,
                "benchmark_max_drawdown_pct": _drawdown(
                    [starting_value, *benchmark_values]
                )
                * 100.0,
                "years_beating_benchmark": len(beat),
                "years_beating_benchmark_share": (
                    len(beat) / len(annual_values) if annual_values else None
                ),
                "benchmark_annual_returns": bench_annual,
            }
        )
    return metrics


def benchmark_paths(
    days: Sequence[date],
    benchmark: PriceSeries,
    starting_value: float,
    cost_per_side: float,
    strategy_values: Optional[Sequence[float]] = None,
) -> Mapping[str, Sequence[float]]:
    """Buy-and-hold benchmark and a volatility-matched variant.

    The volatility-matched path holds ``w`` of the benchmark and ``1 - w`` in
    cash at zero interest, where ``w`` equals the ratio of realised strategy
    volatility to realised benchmark volatility, capped at one.  It never
    levers up, so it stays comparable with a cash-only paper account.
    """

    entry = benchmark.prices[days[0]].adjusted_open
    closes = []
    last = entry
    for day in days:
        point = benchmark.prices.get(day)
        if point is not None:
            last = point.adjusted_close
        closes.append(last)
    gross = [
        starting_value * (1.0 - cost_per_side) * close / entry for close in closes
    ]
    paths: Dict[str, Sequence[float]] = {"buy_and_hold": tuple(gross)}
    if strategy_values is not None:
        strategy_returns = _daily_returns(strategy_values)
        bench_returns = _daily_returns(gross)
        strategy_std = (
            statistics.stdev(strategy_returns) if len(strategy_returns) > 1 else 0.0
        )
        bench_std = statistics.stdev(bench_returns) if len(bench_returns) > 1 else 0.0
        weight = min(1.0, strategy_std / bench_std) if bench_std > 0.0 else 0.0
        matched = [starting_value]
        for value in bench_returns:
            matched.append(matched[-1] * (1.0 + weight * value))
        paths["volatility_matched"] = tuple(matched)
        paths["volatility_matched_weight"] = (weight,)
    return paths


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


@dataclass
class _RunState:
    cash: float
    positions: Dict[str, _Position] = field(default_factory=dict)
    turnover: float = 0.0
    costs: float = 0.0
    delisting_exits: int = 0
    delisting_loss_usd: float = 0.0
    membership_exits: int = 0
    stale_valuation_days: int = 0


def run_research_backtest(
    membership: Sequence[MembershipInterval],
    prices: Mapping[str, PriceSeries],
    signal: SignalFn,
    start: date,
    end: date,
    starting_cash_usd: float = 100_000.0,
    config: Optional[EngineConfig] = None,
    contract: Optional[DataContract] = None,
    sector_map: Optional[Mapping[str, str]] = None,
) -> Tuple[Mapping[str, object], Sequence[Mapping[str, object]]]:
    config = config or EngineConfig()
    benchmark = prices.get("SPY")
    if benchmark is None or not benchmark.prices:
        raise ValueError("SPY price history is required as trading calendar")
    calendar = sorted(benchmark.prices)
    calendar_index = {day: index for index, day in enumerate(calendar)}
    evaluation_days = [day for day in calendar if start <= day <= end]
    if not evaluation_days:
        raise ValueError("no benchmark trading days in requested window")
    market = market_data(prices, calendar)
    active_cache: Dict[date, Sequence[str]] = {}

    sorted_days_cache: Dict[str, Sequence[date]] = {}

    def sorted_days(ticker: str) -> Sequence[date]:
        cached = sorted_days_cache.get(ticker)
        if cached is None:
            cached = tuple(sorted(prices[ticker].prices))
            sorted_days_cache[ticker] = cached
        return cached

    membership_by_ticker: Dict[str, List[MembershipInterval]] = defaultdict(list)
    for item in membership:
        membership_by_ticker[item.ticker].append(item)

    def is_member(ticker: str, day: date) -> bool:
        return any(item.active_on(day) for item in membership_by_ticker.get(ticker, ()))

    def last_close_before_or_on(ticker: str, day: date) -> Optional[Tuple[date, float]]:
        days = sorted_days(ticker)
        position = bisect_right(days, day)
        if position == 0:
            return None
        last = days[position - 1]
        return last, prices[ticker].prices[last].adjusted_close

    state = _RunState(cash=float(starting_cash_usd))
    daily_values: List[float] = []
    daily_invested: List[float] = []
    rows: List[Mapping[str, object]] = []
    holding_days_by_ticker: Counter = Counter()
    buys_by_ticker: Counter = Counter()
    exit_events: List[Mapping[str, object]] = []

    def liquidate(ticker: str, price: float, day: date, reason: str, haircut: float = 0.0) -> None:
        position = state.positions.pop(ticker)
        gross = position.shares * price * (1.0 - haircut)
        cost = gross * config.cost_per_side
        state.cash += gross - cost
        state.turnover += gross
        state.costs += cost
        exit_events.append(
            {
                "date": day.isoformat(),
                "ticker": ticker,
                "reason": reason,
                "proceeds_usd": gross - cost,
                "haircut_pct": haircut * 100.0,
            }
        )

    previous_key: Optional[Tuple[int, int]] = None
    for current_day in evaluation_days:
        index = calendar_index[current_day]

        # 1. Delisting / data-stop handling.  A provider series that simply
        #    ends is the normal footprint of an acquisition or a bankruptcy.
        #    Carrying such a position at its last close is the single largest
        #    source of fictitious performance in a survivorship-biased sample.
        for ticker in sorted(tuple(state.positions)):
            stale = _trading_days_since_last_bar(
                prices[ticker], sorted_days(ticker), current_day, calendar_index
            )
            if stale is None or stale <= config.max_stale_trading_days:
                continue
            resolved = last_close_before_or_on(ticker, current_day)
            if resolved is None:
                state.positions.pop(ticker, None)
                continue
            _, price = resolved
            before = state.positions[ticker].shares * price
            liquidate(
                ticker, price, current_day, "delisted_or_data_stop", config.delisting_haircut
            )
            state.delisting_exits += 1
            state.delisting_loss_usd += before * config.delisting_haircut

        # 2. Index deletions are acted on the first day the name is no longer a
        #    member, independently of the rebalance calendar.
        for ticker in sorted(tuple(state.positions)):
            if is_member(ticker, current_day):
                continue
            point = prices[ticker].prices.get(current_day)
            if point is not None:
                price = point.adjusted_open
            else:
                resolved = last_close_before_or_on(ticker, current_day)
                if resolved is None:
                    continue
                price = resolved[1]
            liquidate(ticker, price, current_day, "index_deletion")
            state.membership_exits += 1

        key = _rebalance_key(current_day, config.rebalance)
        if key != previous_key:
            previous_key = key
            signal_index = index - 1
            if signal_index >= 0:
                signal_day = calendar[signal_index]
                regime_on = True
                if config.trend_sma_days:
                    window_start = signal_index - config.trend_sma_days + 1
                    regime_on = window_start >= 0 and (
                        benchmark.prices[signal_day].adjusted_close
                        > statistics.mean(
                            benchmark.prices[day].adjusted_close
                            for day in calendar[window_start : signal_index + 1]
                        )
                    )
                if regime_on:
                    active = active_cache.get(signal_day)
                    if active is None:
                        active = tuple(
                            sorted(
                                {
                                    item.ticker
                                    for item in membership
                                    if item.active_on(signal_day)
                                }
                            )
                        )
                        active_cache[signal_day] = active
                    eligible, exclusions = _eligible_universe(
                        signal_day,
                        signal_index,
                        active,
                        market,
                        config,
                    )
                    context = SignalContext(
                        signal_day=signal_day,
                        signal_index=signal_index,
                        calendar=calendar,
                        prices=prices,
                        eligible=eligible,
                        benchmark=benchmark,
                        market=market,
                    )
                    scores = signal(context)
                    ranked = sorted(
                        scores, key=lambda ticker: (-scores[ticker], ticker)
                    )[: config.holdings]
                else:
                    eligible, exclusions = (), Counter({"market_regime_off": 1})
                    ranked = []

                exposure = config.target_exposure
                if config.volatility_target is not None and ranked:
                    exposure = min(
                        config.target_exposure,
                        _volatility_scaled_exposure(ranked, signal_index, market, config),
                    )

                equity = state.cash
                for ticker in state.positions:
                    point = prices[ticker].prices.get(current_day)
                    if point is not None:
                        equity += state.positions[ticker].shares * point.adjusted_open
                    else:
                        resolved = last_close_before_or_on(ticker, current_day)
                        equity += (
                            state.positions[ticker].shares * resolved[1]
                            if resolved
                            else 0.0
                        )
                weight = (
                    min(config.max_position_weight, exposure / len(ranked))
                    if ranked
                    else 0.0
                )
                desired = {ticker: equity * weight for ticker in ranked}

                turnover_before = state.turnover
                # Sell down first so buys can only use realised cash.
                for ticker in sorted(tuple(state.positions)):
                    point = prices[ticker].prices.get(current_day)
                    if point is None:
                        # No tradable open: the stale/delisting branch above
                        # owns this case.  Never silently keep an untradable
                        # name at full weight.
                        continue
                    current_value = state.positions[ticker].shares * point.adjusted_open
                    target = desired.get(ticker, 0.0)
                    if current_value <= target:
                        continue
                    notional = current_value - target
                    cost = notional * config.cost_per_side
                    state.positions[ticker].shares -= notional / point.adjusted_open
                    state.cash += notional - cost
                    state.turnover += notional
                    state.costs += cost
                    if state.positions[ticker].shares <= 1e-12:
                        state.positions.pop(ticker, None)

                shortfalls: Dict[str, float] = {}
                for ticker, target in desired.items():
                    point = prices[ticker].prices.get(current_day)
                    if point is None:
                        continue
                    held = (
                        state.positions[ticker].shares * point.adjusted_open
                        if ticker in state.positions
                        else 0.0
                    )
                    if target > held:
                        shortfalls[ticker] = target - held
                required = sum(shortfalls.values()) * (1.0 + config.cost_per_side)
                scale = min(1.0, state.cash / required) if required > 0.0 else 0.0
                for ticker in sorted(shortfalls):
                    point = prices[ticker].prices[current_day]
                    notional = shortfalls[ticker] * scale
                    if notional <= 0.0:
                        continue
                    cost = notional * config.cost_per_side
                    state.positions.setdefault(ticker, _Position()).shares += (
                        notional / point.adjusted_open
                    )
                    state.cash -= notional + cost
                    state.turnover += notional
                    state.costs += cost
                    buys_by_ticker[ticker] += 1

                rows.append(
                    {
                        "signal_date": signal_day.isoformat(),
                        "execution_date": current_day.isoformat(),
                        "market_regime": "on" if regime_on else "off",
                        "exposure": exposure if ranked else 0.0,
                        "selected": ",".join(ranked),
                        "selected_count": len(ranked),
                        "eligible_count": len(eligible),
                        "exclusions": dict(sorted(exclusions.items())),
                        "turnover_usd": state.turnover - turnover_before,
                        "cash_after_usd": state.cash,
                    }
                )

        invested = 0.0
        for ticker in state.positions:
            point = prices[ticker].prices.get(current_day)
            if point is not None:
                invested += state.positions[ticker].shares * point.adjusted_close
            else:
                resolved = last_close_before_or_on(ticker, current_day)
                invested += state.positions[ticker].shares * resolved[1] if resolved else 0.0
                state.stale_valuation_days += 1
            holding_days_by_ticker[ticker] += 1
        daily_invested.append(invested)
        daily_values.append(state.cash + invested)

    paths = benchmark_paths(
        evaluation_days,
        benchmark,
        starting_cash_usd,
        config.cost_per_side,
        daily_values,
    )
    metrics = performance_metrics(
        evaluation_days,
        daily_values,
        starting_cash_usd,
        benchmark_values=paths["buy_and_hold"],
    )
    vol_matched = performance_metrics(
        evaluation_days, list(paths["volatility_matched"]), starting_cash_usd
    )

    total_holding_days = sum(holding_days_by_ticker.values()) or 1
    total_buys = sum(buys_by_ticker.values()) or 1
    sector_concentration: Optional[Mapping[str, object]] = None
    if sector_map:
        by_sector: Counter = Counter()
        for ticker, days_held in holding_days_by_ticker.items():
            by_sector[sector_map.get(ticker, "unknown")] += days_held
        sector_concentration = {
            "holding_day_share": {
                sector: count / total_holding_days
                for sector, count in by_sector.most_common()
            },
            "largest_sector_share": (
                by_sector.most_common(1)[0][1] / total_holding_days if by_sector else 0.0
            ),
        }

    summary = {
        "engine": "research_backtest",
        #: Full equity curve so callers can compute cross-strategy correlation
        #: and crisis behaviour.  Runners are expected to move this into a CSV
        #: rather than keep it in the JSON summary.
        "daily_equity": tuple(
            {
                "date": day.isoformat(),
                "value_usd": value,
                "invested_usd": invested,
            }
            for day, value, invested in zip(evaluation_days, daily_values, daily_invested)
        ),
        "parameters": asdict(config),
        "data_contract": contract.as_dict() if contract else None,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "metrics": metrics,
        "benchmark_volatility_matched": {
            "weight": paths["volatility_matched_weight"][0],
            "metrics": vol_matched,
        },
        "turnover_usd": state.turnover,
        "transaction_costs_usd": state.costs,
        "annual_turnover_ratio": (
            state.turnover
            / max(1e-9, statistics.mean(daily_values))
            / max(1e-9, metrics["years"])
        ),
        "average_invested_usd": statistics.mean(daily_invested),
        "peak_invested_usd": max(daily_invested),
        "average_exposure_pct": (
            statistics.mean(
                invested / value if value > 0 else 0.0
                for invested, value in zip(daily_invested, daily_values)
            )
            * 100.0
        ),
        "rebalance_count": len(rows),
        "defensive_rebalance_count": sum(
            1 for row in rows if row["market_regime"] == "off"
        ),
        "delisting_exit_count": state.delisting_exits,
        "delisting_modelled_loss_usd": state.delisting_loss_usd,
        "index_deletion_exit_count": state.membership_exits,
        "stale_valuation_day_count": state.stale_valuation_days,
        "exit_events": tuple(exit_events),
        "concentration": {
            "holding_day_share_by_ticker": {
                ticker: count / total_holding_days
                for ticker, count in holding_days_by_ticker.most_common(15)
            },
            "largest_ticker_holding_share": (
                holding_days_by_ticker.most_common(1)[0][1] / total_holding_days
                if holding_days_by_ticker
                else 0.0
            ),
            "distinct_tickers_held": len(holding_days_by_ticker),
            "buy_share_by_ticker": {
                ticker: count / total_buys for ticker, count in buys_by_ticker.most_common(15)
            },
            "sector": sector_concentration,
        },
    }
    return summary, tuple(rows)


def _volatility_scaled_exposure(
    tickers: Sequence[str],
    signal_index: int,
    market: MarketData,
    config: EngineConfig,
) -> float:
    """Equal-weight portfolio volatility over the lookback, scaled to target."""

    first = max(1, signal_index - config.volatility_lookback_days)
    portfolio: List[float] = []
    for index in range(first, signal_index + 1):
        values = [
            market.returns[ticker][index]
            for ticker in tickers
            if ticker in market.returns and market.returns[ticker][index] is not None
        ]
        if values:
            portfolio.append(statistics.mean(values))  # type: ignore[arg-type]
    if len(portfolio) < 10:
        return config.target_exposure
    realised = statistics.stdev(portfolio) * math.sqrt(TRADING_DAYS_PER_YEAR)
    if realised <= 0.0:
        return config.target_exposure
    assert config.volatility_target is not None
    return max(0.0, min(config.target_exposure, config.volatility_target / realised))


_MARKET_CACHE: Dict[Tuple[int, int], MarketData] = {}


def market_data(prices: Mapping[str, PriceSeries], calendar: Sequence[date]) -> MarketData:
    """Cached :class:`MarketData` so repeated runs do not rebuild the arrays."""

    key = (id(prices), len(calendar))
    cached = _MARKET_CACHE.get(key)
    if cached is None or cached.prices is not prices:
        cached = MarketData(prices, calendar)
        _MARKET_CACHE.clear()
        _MARKET_CACHE[key] = cached
    return cached


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------


def walk_forward(
    membership: Sequence[MembershipInterval],
    prices: Mapping[str, PriceSeries],
    signal: SignalFn,
    start: date,
    end: date,
    training_years: int = 5,
    starting_cash_usd: float = 100_000.0,
    config: Optional[EngineConfig] = None,
) -> Mapping[str, object]:
    """Rolling ``training_years`` diagnosis window plus one unseen test year.

    Nothing is fitted on the training window — the rules are frozen — so the
    training block is a diagnosis, not a selection step.  It is reported so a
    reader can see whether the test year looked anything like the run-up.
    """

    windows: List[Mapping[str, object]] = []
    compounded = 1.0
    for test_year in range(start.year + training_years, end.year + 1):
        test_start = max(start, date(test_year, 1, 1))
        test_end = min(end, date(test_year, 12, 31))
        if test_start > test_end:
            continue
        training_start = max(start, date(test_year - training_years, 1, 1))
        training_end = date(test_year - 1, 12, 31)
        training, _ = run_research_backtest(
            membership,
            prices,
            signal,
            training_start,
            training_end,
            starting_cash_usd=starting_cash_usd,
            config=config,
        )
        test, _ = run_research_backtest(
            membership,
            prices,
            signal,
            test_start,
            test_end,
            starting_cash_usd=starting_cash_usd,
            config=config,
        )
        test_metrics = test["metrics"]
        compounded *= 1.0 + float(test_metrics["total_return_pct"]) / 100.0
        windows.append(
            {
                "test_year": test_year,
                "partial_year": test_end < date(test_year, 12, 31),
                "training_cagr_pct": training["metrics"]["cagr_pct"],
                "training_max_drawdown_pct": training["metrics"]["max_drawdown_pct"],
                "test_return_pct": test_metrics["total_return_pct"],
                "test_max_drawdown_pct": test_metrics["max_drawdown_pct"],
                "test_benchmark_return_pct": test_metrics["benchmark_total_return_pct"],
                "test_volatility_pct": test_metrics["annualized_volatility_pct"],
            }
        )
    complete = [item for item in windows if not item["partial_year"]]
    complete_returns = [float(item["test_return_pct"]) for item in complete]
    return {
        "training_years": training_years,
        "windows": tuple(windows),
        "compounded_test_return_pct": (compounded - 1.0) * 100.0,
        "positive_test_count": sum(
            float(item["test_return_pct"]) > 0.0 for item in windows
        ),
        "tests_beating_benchmark_count": sum(
            float(item["test_return_pct"]) > float(item["test_benchmark_return_pct"])
            for item in windows
        ),
        "complete_year_count": len(complete),
        "complete_year_median_return_pct": (
            statistics.median(complete_returns) if complete_returns else None
        ),
        "complete_year_min_return_pct": min(complete_returns) if complete_returns else None,
    }


def cost_stress(
    membership: Sequence[MembershipInterval],
    prices: Mapping[str, PriceSeries],
    signal: SignalFn,
    start: date,
    end: date,
    levels: Sequence[float] = (0.0, 0.001, 0.0025, 0.005),
    starting_cash_usd: float = 100_000.0,
    config: Optional[EngineConfig] = None,
) -> Mapping[str, Mapping[str, object]]:
    base = config or EngineConfig()
    out: Dict[str, Mapping[str, object]] = {}
    for level in levels:
        summary, _ = run_research_backtest(
            membership,
            prices,
            signal,
            start,
            end,
            starting_cash_usd=starting_cash_usd,
            config=replace(base, cost_per_side=level),
        )
        metrics = summary["metrics"]
        out[f"{level:.4f}"] = {
            "cagr_pct": metrics["cagr_pct"],
            "total_return_pct": metrics["total_return_pct"],
            "max_drawdown_pct": metrics["max_drawdown_pct"],
            "transaction_costs_usd": summary["transaction_costs_usd"],
            "annual_turnover_ratio": summary["annual_turnover_ratio"],
        }
    return out
