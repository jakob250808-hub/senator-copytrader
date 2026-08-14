"""Independent, economically motivated signals for the research backtester.

Each signal is a pure function of a :class:`~senator_copytrader.research_backtest.SignalContext`.
The context refuses to hand out prices dated after the signal day, so
look-ahead is prevented by the interface rather than by discipline.

Every signal here has at most two free parameters and each of them is fixed by
the published literature, not by a search over this sample:

``momentum_12_1``          Jegadeesh & Titman (1993); 12-month lookback, one
                           month skipped to avoid the short-term reversal.
``residual_momentum``      Blitz, Huij & Martens (2011); the same window, but
                           the market component is regressed out and the
                           residual is standardised by its own volatility.
``short_term_reversal``    Lehmann (1990), Jegadeesh (1990); one-week
                           reversal, restricted to the most liquid names
                           because the effect is a liquidity-provision premium.
``momentum_with_quality``  Novy-Marx (2013) profitability tilt.  Requires
                           point-in-time fundamentals and refuses to run
                           without them instead of falling back to today's
                           numbers.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Mapping, Optional, Sequence

from .factor_backtest import QualitySnapshot
from .research_backtest import SignalContext

MOMENTUM_LOOKBACK_DAYS = 252
MOMENTUM_SKIP_DAYS = 21
REVERSAL_LOOKBACK_DAYS = 5
MINIMUM_REGRESSION_DAYS = 120


class MissingPointInTimeData(RuntimeError):
    """Raised instead of silently substituting a present-day snapshot."""


def momentum_12_1(context: SignalContext) -> Mapping[str, float]:
    """Total return from t-12 months to t-1 month."""

    start_index = context.signal_index - MOMENTUM_LOOKBACK_DAYS
    end_index = context.signal_index - MOMENTUM_SKIP_DAYS
    if start_index < 0:
        return {}
    scores: Dict[str, float] = {}
    for ticker in context.eligible:
        closes = context.closes(ticker, start_index, end_index)
        if len(closes) < MOMENTUM_LOOKBACK_DAYS - MOMENTUM_SKIP_DAYS - 20:
            continue
        if closes[0] <= 0.0:
            continue
        scores[ticker] = closes[-1] / closes[0] - 1.0
    return scores


def residual_momentum(context: SignalContext) -> Mapping[str, float]:
    """Market-residual momentum, standardised by residual volatility.

    Plain 12-1 momentum loads heavily on whatever sector happened to run.  The
    residual version removes the part of the past year that the market itself
    explains and divides by the idiosyncratic volatility, so a quiet stock with
    a persistent residual outranks a violent one with the same raw return.
    """

    start_index = context.signal_index - MOMENTUM_LOOKBACK_DAYS
    end_index = context.signal_index - MOMENTUM_SKIP_DAYS
    if start_index < 0:
        return {}
    scores: Dict[str, float] = {}
    for ticker in context.eligible:
        model = context.market_model(ticker, start_index, end_index)
        if model is None:
            continue
        alpha, _beta, residual_std, observations = model
        if observations < MINIMUM_REGRESSION_DAYS or residual_std <= 0.0:
            continue
        # ``alpha`` is the daily intercept of the market model; scoring it
        # against the residual dispersion is the information-ratio form used
        # by Blitz et al.
        scores[ticker] = alpha / residual_std
    return scores


def short_term_reversal(
    context: SignalContext, universe_size: int = 100
) -> Mapping[str, float]:
    """Buy last week's losers among the most liquid names.

    The premium is compensation for absorbing short-term selling pressure, so
    it only exists where there is enough depth to absorb it.  Restricting the
    universe to the ``universe_size`` most liquid members is part of the
    hypothesis, not a fitted filter.
    """

    start_index = context.signal_index - REVERSAL_LOOKBACK_DAYS
    if start_index < 0:
        return {}
    liquidity: Dict[str, float] = {}
    for ticker in context.eligible:
        average = context.average_dollar_volume(
            ticker, context.signal_index - 20, context.signal_index
        )
        if average > 0.0:
            liquidity[ticker] = average
    most_liquid = sorted(liquidity, key=lambda ticker: (-liquidity[ticker], ticker))[
        :universe_size
    ]
    scores: Dict[str, float] = {}
    for ticker in most_liquid:
        closes = context.closes(ticker, start_index, context.signal_index)
        if len(closes) < REVERSAL_LOOKBACK_DAYS or closes[0] <= 0.0:
            continue
        scores[ticker] = -(closes[-1] / closes[0] - 1.0)
    return scores


def make_momentum_with_quality(
    snapshots: Mapping[str, Sequence[QualitySnapshot]],
    quality_weight: float = 0.30,
    max_age_days: int = 550,
):
    """Momentum blended with point-in-time profitability and leverage.

    Refuses to run without real ``available_date`` stamped fundamentals.  That
    refusal is the point: a quality tilt built from today's restated financials
    is the classic way to manufacture a backtest that cannot be traded.
    """

    if not snapshots:
        raise MissingPointInTimeData(
            "momentum_with_quality needs fundamentals stamped with the date they "
            "were first public; refusing to substitute a present-day snapshot"
        )

    def signal(context: SignalContext) -> Mapping[str, float]:
        raw = momentum_12_1(context)
        if not raw:
            return {}
        available: Dict[str, QualitySnapshot] = {}
        for ticker in raw:
            snapshot = _latest_snapshot(
                snapshots, ticker, context.signal_day, max_age_days
            )
            if snapshot is not None:
                available[ticker] = snapshot
        if not available:
            return {}
        momentum_rank = _ranks({t: raw[t] for t in available})
        roa = _ranks({t: available[t].return_on_assets for t in available})
        profitability = _ranks({t: available[t].gross_profitability for t in available})
        low_debt = _ranks({t: -available[t].debt_to_assets for t in available})
        return {
            ticker: (1.0 - quality_weight) * momentum_rank[ticker]
            + quality_weight
            * (roa[ticker] + profitability[ticker] + low_debt[ticker])
            / 3.0
            for ticker in available
        }

    return signal


def _latest_snapshot(
    snapshots: Mapping[str, Sequence[QualitySnapshot]],
    ticker: str,
    signal_day: date,
    max_age_days: int,
) -> Optional[QualitySnapshot]:
    eligible = [
        item for item in snapshots.get(ticker, ()) if item.available_date <= signal_day
    ]
    if not eligible:
        return None
    latest = eligible[-1]
    if (signal_day - latest.available_date).days > max_age_days:
        return None
    return latest


def _ranks(values: Mapping[str, float]) -> Mapping[str, float]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    if len(ordered) <= 1:
        return {ticker: 1.0 for ticker, _ in ordered}
    ranks: Dict[str, float] = {}
    index = 0
    while index < len(ordered):
        upper = index
        while upper + 1 < len(ordered) and ordered[upper + 1][1] == ordered[index][1]:
            upper += 1
        rank = ((index + upper) / 2.0) / (len(ordered) - 1)
        for offset in range(index, upper + 1):
            ranks[ordered[offset][0]] = rank
        index = upper + 1
    return ranks
