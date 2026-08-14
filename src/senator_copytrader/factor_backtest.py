from __future__ import annotations

import csv
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .backtest import PricePoint, PriceSeries


@dataclass(frozen=True)
class MembershipInterval:
    ticker: str
    start_date: date
    end_date: Optional[date] = None

    def active_on(self, day: date) -> bool:
        return self.start_date <= day and (
            self.end_date is None or day <= self.end_date
        )


@dataclass(frozen=True)
class QualitySnapshot:
    ticker: str
    available_date: date
    return_on_assets: float
    gross_profitability: float
    debt_to_assets: float


@dataclass(frozen=True)
class FactorConfig:
    holdings: int = 20
    momentum_long_days: int = 252
    momentum_skip_days: int = 21
    trend_sma_days: int = 200
    liquidity_lookback_days: int = 63
    minimum_price_usd: float = 5.0
    minimum_average_dollar_volume_usd: float = 10_000_000.0
    quality_weight: float = 0.0
    max_quality_age_days: int = 550
    target_exposure: float = 1.0
    max_position_weight: float = 0.10
    cost_per_side: float = 0.001

    def __post_init__(self) -> None:
        if self.holdings < 1:
            raise ValueError("holdings must be positive")
        if self.momentum_long_days <= self.momentum_skip_days:
            raise ValueError("momentum_long_days must exceed momentum_skip_days")
        if self.trend_sma_days < 1 or self.liquidity_lookback_days < 2:
            raise ValueError("lookback windows are too short")
        if not 0.0 <= self.quality_weight <= 1.0:
            raise ValueError("quality_weight must be between zero and one")
        if not 0.0 < self.target_exposure <= 1.0:
            raise ValueError("target_exposure must be in (0, 1]")
        if not 0.0 < self.max_position_weight <= 1.0:
            raise ValueError("max_position_weight must be in (0, 1]")
        if not 0.0 <= self.cost_per_side <= 0.05:
            raise ValueError("cost_per_side must be between zero and 5%")


@dataclass
class _Position:
    shares: float


def load_membership_intervals(path: Path) -> Sequence[MembershipInterval]:
    intervals: List[MembershipInterval] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"ticker", "start_date", "end_date"}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError("membership CSV needs ticker,start_date,end_date")
        for row in reader:
            ticker = str(row.get("ticker") or "").strip().upper()
            start_text = str(row.get("start_date") or "").strip()
            end_text = str(row.get("end_date") or "").strip()
            if not ticker or not start_text:
                continue
            start_day = date.fromisoformat(start_text)
            end_day = date.fromisoformat(end_text) if end_text else None
            if end_day is not None and end_day < start_day:
                raise ValueError(f"membership end precedes start for {ticker}")
            intervals.append(MembershipInterval(ticker, start_day, end_day))
    return tuple(sorted(intervals, key=lambda item: (item.start_date, item.ticker)))


def load_quality_snapshots(path: Path) -> Mapping[str, Sequence[QualitySnapshot]]:
    by_ticker: Dict[str, List[QualitySnapshot]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {
            "ticker",
            "available_date",
            "return_on_assets",
            "gross_profitability",
            "debt_to_assets",
        }
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError("quality CSV is missing required point-in-time fields")
        for row in reader:
            try:
                item = QualitySnapshot(
                    ticker=str(row["ticker"]).strip().upper(),
                    available_date=date.fromisoformat(str(row["available_date"]).strip()),
                    return_on_assets=float(row["return_on_assets"]),
                    gross_profitability=float(row["gross_profitability"]),
                    debt_to_assets=float(row["debt_to_assets"]),
                )
            except (TypeError, ValueError):
                continue
            if item.ticker and all(
                math.isfinite(value)
                for value in (
                    item.return_on_assets,
                    item.gross_profitability,
                    item.debt_to_assets,
                )
            ):
                by_ticker[item.ticker].append(item)
    return {
        ticker: tuple(sorted(items, key=lambda item: item.available_date))
        for ticker, items in by_ticker.items()
    }


def _latest_quality(
    snapshots: Mapping[str, Sequence[QualitySnapshot]],
    ticker: str,
    signal_day: date,
    max_age_days: int,
) -> Optional[QualitySnapshot]:
    eligible = [
        item
        for item in snapshots.get(ticker, ())
        if item.available_date <= signal_day
    ]
    if not eligible:
        return None
    latest = eligible[-1]
    if (signal_day - latest.available_date).days > max_age_days:
        return None
    return latest


def _percentile_ranks(values: Mapping[str, float]) -> Mapping[str, float]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    if len(ordered) <= 1:
        return {ticker: 1.0 for ticker, _ in ordered}
    ranks: Dict[str, float] = {}
    index = 0
    while index < len(ordered):
        upper = index
        while upper + 1 < len(ordered) and ordered[upper + 1][1] == ordered[index][1]:
            upper += 1
        average_index = (index + upper) / 2.0
        rank = average_index / (len(ordered) - 1)
        for offset in range(index, upper + 1):
            ranks[ordered[offset][0]] = rank
        index = upper + 1
    return ranks


def _point_on_or_before(
    series: PriceSeries, target: date, max_stale_days: int = 7
) -> Optional[Tuple[date, PricePoint]]:
    point = series.prices.get(target)
    if point is not None:
        return target, point
    days = [day for day in series.prices if day <= target]
    if not days:
        return None
    day = max(days)
    if (target - day).days > max_stale_days:
        return None
    return day, series.prices[day]


def _score_candidates(
    signal_day: date,
    signal_index: int,
    calendar: Sequence[date],
    membership: Sequence[MembershipInterval],
    prices: Mapping[str, PriceSeries],
    quality_snapshots: Mapping[str, Sequence[QualitySnapshot]],
    config: FactorConfig,
) -> Tuple[Sequence[str], Mapping[str, int]]:
    exclusions: Counter[str] = Counter()
    if signal_index < config.momentum_long_days:
        return (), {"insufficient_benchmark_history": 1}
    long_day = calendar[signal_index - config.momentum_long_days]
    skip_day = calendar[signal_index - config.momentum_skip_days]
    volume_start = max(0, signal_index - config.liquidity_lookback_days + 1)
    volume_days = calendar[volume_start : signal_index + 1]
    active = sorted({item.ticker for item in membership if item.active_on(signal_day)})
    momentum: Dict[str, float] = {}
    fundamentals: Dict[str, QualitySnapshot] = {}
    for ticker in active:
        series = prices.get(ticker)
        if series is None or not series.prices:
            exclusions["missing_price_series"] += 1
            continue
        if series.instrument_type != "EQUITY":
            exclusions["not_equity"] += 1
            continue
        long_point = _point_on_or_before(series, long_day)
        skip_point = _point_on_or_before(series, skip_day)
        signal_point = _point_on_or_before(series, signal_day)
        if long_point is None or skip_point is None or signal_point is None:
            exclusions["incomplete_momentum_history"] += 1
            continue
        if signal_point[1].adjusted_close < config.minimum_price_usd:
            exclusions["minimum_price"] += 1
            continue
        dollar_volumes = [
            series.prices[day].dollar_volume
            for day in volume_days
            if day in series.prices and series.prices[day].dollar_volume > 0.0
        ]
        if config.minimum_average_dollar_volume_usd > 0.0 and (
            len(dollar_volumes) < max(2, len(volume_days) // 2)
            or statistics.mean(dollar_volumes)
            < config.minimum_average_dollar_volume_usd
        ):
            exclusions["minimum_liquidity"] += 1
            continue
        start_price = long_point[1].adjusted_close
        end_price = skip_point[1].adjusted_close
        if start_price <= 0.0 or end_price <= 0.0:
            exclusions["invalid_price"] += 1
            continue
        momentum[ticker] = end_price / start_price - 1.0
        if config.quality_weight > 0.0:
            snapshot = _latest_quality(
                quality_snapshots, ticker, signal_day, config.max_quality_age_days
            )
            if snapshot is None:
                exclusions["missing_point_in_time_quality"] += 1
                momentum.pop(ticker, None)
                continue
            fundamentals[ticker] = snapshot

    if not momentum:
        return (), dict(sorted(exclusions.items()))
    momentum_rank = _percentile_ranks(momentum)
    quality_rank = {ticker: 0.0 for ticker in momentum}
    if config.quality_weight > 0.0:
        roa = _percentile_ranks(
            {ticker: fundamentals[ticker].return_on_assets for ticker in momentum}
        )
        profitability = _percentile_ranks(
            {ticker: fundamentals[ticker].gross_profitability for ticker in momentum}
        )
        low_debt = _percentile_ranks(
            {ticker: -fundamentals[ticker].debt_to_assets for ticker in momentum}
        )
        quality_rank = {
            ticker: (roa[ticker] + profitability[ticker] + low_debt[ticker]) / 3.0
            for ticker in momentum
        }
    scores = {
        ticker: (1.0 - config.quality_weight) * momentum_rank[ticker]
        + config.quality_weight * quality_rank[ticker]
        for ticker in momentum
    }
    selected = sorted(scores, key=lambda ticker: (-scores[ticker], ticker))[
        : config.holdings
    ]
    exclusions["eligible"] = len(momentum)
    return tuple(selected), dict(sorted(exclusions.items()))


def _returns(values: Sequence[float]) -> Sequence[float]:
    return tuple(
        values[index] / values[index - 1] - 1.0
        for index in range(1, len(values))
        if values[index - 1] > 0.0
    )


def _period_returns(
    days: Sequence[date], values: Sequence[float], period: str, starting_value: float
) -> Sequence[Mapping[str, object]]:
    endpoints: Dict[str, Tuple[date, float]] = {}
    for day, value in zip(days, values):
        key = day.strftime("%Y-%m") if period == "month" else str(day.year)
        endpoints[key] = (day, value)
    result = []
    previous = starting_value
    for key, (day, value) in sorted(endpoints.items()):
        result.append(
            {
                period: key,
                "end_date": day.isoformat(),
                "ending_value_usd": value,
                "return_pct": (value / previous - 1.0) * 100.0,
            }
        )
        previous = value
    return tuple(result)


def run_factor_backtest(
    membership: Sequence[MembershipInterval],
    prices: Mapping[str, PriceSeries],
    start: date,
    end: date,
    starting_cash_usd: float = 100_000.0,
    quality_snapshots: Optional[Mapping[str, Sequence[QualitySnapshot]]] = None,
    config: Optional[FactorConfig] = None,
) -> Tuple[Mapping[str, object], Sequence[Mapping[str, object]]]:
    """Monthly, long-only 12-1 momentum backtest with optional PIT quality."""

    config = config or FactorConfig()
    quality_snapshots = quality_snapshots or {}
    spy = prices.get("SPY")
    if spy is None or not spy.prices:
        raise ValueError("SPY price history is required")
    calendar = sorted(spy.prices)
    evaluation_days = [day for day in calendar if start <= day <= end]
    if not evaluation_days:
        raise ValueError("no benchmark trading days in requested window")
    calendar_index = {day: index for index, day in enumerate(calendar)}
    membership_by_ticker: Dict[str, List[MembershipInterval]] = defaultdict(list)
    for item in membership:
        membership_by_ticker[item.ticker].append(item)

    cash = float(starting_cash_usd)
    positions: Dict[str, _Position] = {}
    daily_values: List[float] = []
    daily_invested: List[float] = []
    rebalance_rows: List[Mapping[str, object]] = []
    total_turnover = 0.0
    total_costs = 0.0
    forced_exit_count = 0
    stale_position_day_count = 0
    regime_off_count = 0

    def is_active(ticker: str, day: date) -> bool:
        return any(item.active_on(day) for item in membership_by_ticker.get(ticker, ()))

    def latest_value(ticker: str, day: date, use_open: bool = False) -> Tuple[float, bool]:
        series = prices[ticker]
        point = series.prices.get(day)
        if point is not None:
            price = point.adjusted_open if use_open else point.adjusted_close
            return positions[ticker].shares * price, False
        prior = [price_day for price_day in series.prices if price_day < day]
        if not prior:
            return 0.0, True
        prior_day = max(prior)
        return positions[ticker].shares * series.prices[prior_day].adjusted_close, True

    previous_month: Optional[Tuple[int, int]] = None
    for current_day in evaluation_days:
        # Index deletions are handled on the first day they are no longer active,
        # independently of the normal monthly rebalance.
        for ticker in sorted(tuple(positions)):
            if is_active(ticker, current_day):
                continue
            series = prices[ticker]
            point = series.prices.get(current_day)
            if point is not None:
                exit_price = point.adjusted_open
            else:
                prior = [day for day in series.prices if day < current_day]
                if not prior:
                    continue
                exit_price = series.prices[max(prior)].adjusted_close
            notional = positions.pop(ticker).shares * exit_price
            cost = notional * config.cost_per_side
            cash += notional - cost
            total_turnover += notional
            total_costs += cost
            forced_exit_count += 1

        month = (current_day.year, current_day.month)
        is_rebalance_day = month != previous_month
        if is_rebalance_day:
            previous_month = month
            signal_index = calendar_index[current_day] - 1
            if signal_index >= 0:
                signal_day = calendar[signal_index]
                spy_history_start = signal_index - config.trend_sma_days + 1
                regime_on = spy_history_start >= 0 and (
                    spy.prices[signal_day].adjusted_close
                    > statistics.mean(
                        spy.prices[day].adjusted_close
                        for day in calendar[spy_history_start : signal_index + 1]
                    )
                )
                if regime_on:
                    selected, exclusions = _score_candidates(
                        signal_day,
                        signal_index,
                        calendar,
                        membership,
                        prices,
                        quality_snapshots,
                        config,
                    )
                else:
                    selected, exclusions = (), {"market_regime_off": 1}
                    regime_off_count += 1

                equity_open = cash
                for ticker in positions:
                    value, _ = latest_value(ticker, current_day, use_open=True)
                    equity_open += value
                weight = min(
                    config.max_position_weight,
                    config.target_exposure / len(selected) if selected else 0.0,
                )
                desired = {ticker: equity_open * weight for ticker in selected}
                rebalance_turnover = 0.0
                rebalance_cost = 0.0

                # Reduce and close first so buys use actual post-cost cash.
                for ticker in sorted(tuple(positions)):
                    point = prices[ticker].prices.get(current_day)
                    if point is None:
                        continue
                    current_value = positions[ticker].shares * point.adjusted_open
                    target_value = desired.get(ticker, 0.0)
                    if current_value <= target_value:
                        continue
                    notional = current_value - target_value
                    cost = notional * config.cost_per_side
                    positions[ticker].shares -= notional / point.adjusted_open
                    cash += notional - cost
                    rebalance_turnover += notional
                    rebalance_cost += cost
                    if positions[ticker].shares <= 1e-12:
                        positions.pop(ticker, None)

                shortfalls: Dict[str, float] = {}
                for ticker, target_value in desired.items():
                    point = prices.get(ticker, PriceSeries(ticker, "", {})).prices.get(
                        current_day
                    )
                    if point is None:
                        continue
                    current_value = (
                        positions[ticker].shares * point.adjusted_open
                        if ticker in positions
                        else 0.0
                    )
                    if target_value > current_value:
                        shortfalls[ticker] = target_value - current_value
                required = sum(shortfalls.values()) * (1.0 + config.cost_per_side)
                scale = min(1.0, cash / required) if required > 0.0 else 0.0
                for ticker in sorted(shortfalls):
                    point = prices[ticker].prices[current_day]
                    notional = shortfalls[ticker] * scale
                    cost = notional * config.cost_per_side
                    positions.setdefault(ticker, _Position(0.0)).shares += (
                        notional / point.adjusted_open
                    )
                    cash -= notional + cost
                    rebalance_turnover += notional
                    rebalance_cost += cost

                total_turnover += rebalance_turnover
                total_costs += rebalance_cost
                rebalance_rows.append(
                    {
                        "signal_date": signal_day.isoformat(),
                        "execution_date": current_day.isoformat(),
                        "market_regime": "on" if regime_on else "off",
                        "selected": ",".join(selected),
                        "selected_count": len(selected),
                        "eligible_count": int(exclusions.get("eligible", 0)),
                        "exclusions": dict(exclusions),
                        "turnover_usd": rebalance_turnover,
                        "costs_usd": rebalance_cost,
                        "cash_after_usd": cash,
                    }
                )

        invested = 0.0
        for ticker in positions:
            value, stale = latest_value(ticker, current_day)
            invested += value
            stale_position_day_count += int(stale)
        daily_invested.append(invested)
        daily_values.append(cash + invested)

    ending_value = daily_values[-1]
    peak = daily_values[0]
    max_drawdown = 0.0
    for value in daily_values:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1.0)
    daily_returns = _returns(daily_values)
    mean_daily = statistics.mean(daily_returns) if daily_returns else 0.0
    daily_std = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0.0
    downside = [min(0.0, value) for value in daily_returns]
    downside_std = statistics.stdev(downside) if len(downside) > 1 else 0.0
    years = max(1.0 / 365.25, (evaluation_days[-1] - evaluation_days[0]).days / 365.25)
    cagr = (ending_value / starting_cash_usd) ** (1.0 / years) - 1.0

    spy_start = spy.prices[evaluation_days[0]].adjusted_open
    spy_end = spy.prices[evaluation_days[-1]].adjusted_close
    spy_multiplier = (1.0 - config.cost_per_side) * spy_end / spy_start
    monthly = _period_returns(evaluation_days, daily_values, "month", starting_cash_usd)
    annual = _period_returns(evaluation_days, daily_values, "year", starting_cash_usd)
    member_tickers = {
        item.ticker
        for item in membership
        if item.start_date <= end and (item.end_date is None or item.end_date >= start)
    }
    available_tickers = {
        ticker for ticker in member_tickers if ticker in prices and prices[ticker].prices
    }
    summary = {
        "parameters": asdict(config),
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "market_start": evaluation_days[0].isoformat(),
        "market_end": evaluation_days[-1].isoformat(),
        "starting_cash_usd": starting_cash_usd,
        "ending_value_usd": ending_value,
        "return_pct": (ending_value / starting_cash_usd - 1.0) * 100.0,
        "cagr_pct": cagr * 100.0,
        "max_drawdown_pct": max_drawdown * 100.0,
        "annualized_volatility_pct": daily_std * math.sqrt(252.0) * 100.0,
        "sharpe_zero_rate": (
            mean_daily / daily_std * math.sqrt(252.0) if daily_std else None
        ),
        "sortino_zero_rate": (
            mean_daily / downside_std * math.sqrt(252.0) if downside_std else None
        ),
        "calmar_zero_rate": cagr / abs(max_drawdown) if max_drawdown else None,
        "spy_return_pct": (spy_multiplier - 1.0) * 100.0,
        "excess_return_pct_points": (
            ending_value / starting_cash_usd - spy_multiplier
        )
        * 100.0,
        "average_invested_usd": statistics.mean(daily_invested),
        "peak_invested_usd": max(daily_invested),
        "turnover_usd": total_turnover,
        "transaction_costs_usd": total_costs,
        "rebalance_count": len(rebalance_rows),
        "regime_off_rebalance_count": regime_off_count,
        "forced_membership_exit_count": forced_exit_count,
        "stale_position_day_count": stale_position_day_count,
        "monthly_returns": monthly,
        "annual_returns": annual,
        "data_coverage": {
            "membership_ticker_count": len(member_tickers),
            "available_price_ticker_count": len(available_tickers),
            "missing_price_ticker_count": len(member_tickers - available_tickers),
            "available_price_share": (
                len(available_tickers) / len(member_tickers) if member_tickers else 0.0
            ),
            "quality_ticker_count": len(quality_snapshots),
        },
        "ending_positions": {
            ticker: positions[ticker].shares for ticker in sorted(positions)
        },
    }
    return summary, tuple(rebalance_rows)
