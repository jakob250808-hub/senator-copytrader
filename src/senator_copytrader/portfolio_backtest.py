from __future__ import annotations

import csv
import json
import random
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .backtest import PriceSeries, _first_day_after
from .models import normalize_action, normalize_person_name, normalize_ticker, parse_date


TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
KADOA_NAME_ALIASES = {
    "daniel sullivan": "Dan Sullivan",
    "john reed": "Jack Reed",
    "katie britt": "Katie Boyd Britt",
    "mitchell": "Mitch McConnell",
    "mitchell mcconnell": "Mitch McConnell",
    "rafael cruz": "Ted Cruz",
    "thomas tillis": "Thom Tillis",
    "thomas tuberville": "Tommy Tuberville",
    "william cassidy": "Bill Cassidy",
    "william hagerty": "Bill Hagerty",
}
PORTFOLIO_RESULT_FIELDS = (
    "event_id",
    "senator",
    "filing_date",
    "transaction_date",
    "execution_date",
    "action",
    "ticker",
    "asset_type",
    "owner",
    "amount_range",
    "status",
    "reason",
    "execution_price",
    "notional_usd",
    "shares",
    "cash_after_usd",
)


@dataclass(frozen=True)
class PortfolioSignal:
    event_id: str
    senator: str
    filing_date: date
    transaction_date: Optional[date]
    action: str
    ticker: str
    asset_type: str
    owner: str
    amount_range: str
    initial_exclusion: str = ""


@dataclass
class _Position:
    shares: float = 0.0
    paid_notional_usd: float = 0.0
    entry_value_usd: float = 0.0
    opened_on: Optional[date] = None


def _resolve_kadoa_name(source_name: str, politicians: Sequence[str]) -> Optional[str]:
    configured = {normalize_person_name(name): name for name in politicians}
    key = normalize_person_name(source_name)
    direct = configured.get(key)
    if direct:
        return direct
    alias = KADOA_NAME_ALIASES.get(key)
    return alias if alias in politicians else None


def load_kadoa_signals(
    filer_dir: Path,
    politicians: Sequence[str],
    start: date,
    end: date,
) -> Sequence[PortfolioSignal]:
    """Load one signal per Kadoa transaction using its publication date."""

    signals: Dict[str, PortfolioSignal] = {}
    for path in sorted(filer_dir.glob("senate_*.json")):
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        filer = payload.get("filer") or {}
        senator = _resolve_kadoa_name(str(filer.get("full_name") or ""), politicians)
        if senator is None:
            continue
        for raw in payload.get("trades") or []:
            filing_date = parse_date(raw.get("filing_date"))
            if filing_date is None or not start <= filing_date <= end:
                continue
            event_id = str(raw.get("id") or "").strip()
            if not event_id:
                continue
            action = normalize_action(raw.get("transaction_type"))
            asset_type = str(raw.get("asset_type") or "").strip()
            ticker = normalize_ticker(raw.get("ticker"))
            exclusion = ""
            if action == "unsupported":
                exclusion = "unsupported_action"
            elif asset_type != "Stock":
                exclusion = "source_asset_type_not_stock"
            elif not TICKER_PATTERN.fullmatch(ticker):
                exclusion = "invalid_or_missing_ticker"
            signals.setdefault(
                event_id,
                PortfolioSignal(
                    event_id=event_id,
                    senator=senator,
                    filing_date=filing_date,
                    transaction_date=parse_date(raw.get("transaction_date")),
                    action=action,
                    ticker=ticker,
                    asset_type=asset_type,
                    owner=str(raw.get("owner") or "").strip(),
                    amount_range=str(raw.get("amount_range_label") or "").strip(),
                    initial_exclusion=exclusion,
                ),
            )
    return tuple(
        sorted(
            signals.values(),
            key=lambda item: (
                item.filing_date,
                item.transaction_date or date.min,
                item.senator,
                item.ticker,
                item.event_id,
            ),
        )
    )


def _empty_result(signal: PortfolioSignal) -> Dict[str, object]:
    row = {field: "" for field in PORTFOLIO_RESULT_FIELDS}
    row.update(
        event_id=signal.event_id,
        senator=signal.senator,
        filing_date=signal.filing_date.isoformat(),
        transaction_date=(
            signal.transaction_date.isoformat() if signal.transaction_date else ""
        ),
        action=signal.action,
        ticker=signal.ticker,
        asset_type=signal.asset_type,
        owner=signal.owner,
        amount_range=signal.amount_range,
    )
    return row


def _latest_close(series: PriceSeries, day: date, before: bool = False) -> Optional[float]:
    eligible = [
        price_day
        for price_day in series.prices
        if price_day < day or (not before and price_day == day)
    ]
    if not eligible:
        return None
    return series.prices[max(eligible)].adjusted_close


def run_portfolio_backtest(
    signals: Sequence[PortfolioSignal],
    price_series: Mapping[str, PriceSeries],
    start: date,
    end: date,
    starting_cash_usd: float = 100_000.0,
    buy_notional_usd: float = 1_000.0,
    max_position_usd: float = 3_000.0,
    max_portfolio_usd: float = 20_000.0,
    max_daily_notional_usd: float = 5_000.0,
    cost_per_side: float = 0.001,
    stop_loss_pct: Optional[float] = None,
    take_profit_pct: Optional[float] = None,
    max_holding_days: Optional[int] = None,
) -> Tuple[Mapping[str, object], Sequence[Mapping[str, object]]]:
    """Simulate the current bot rules from disclosure date through ``end``."""

    spy = price_series.get("SPY")
    if spy is None or not spy.prices:
        raise ValueError("SPY price history is required as the trading calendar")
    trading_days = sorted(day for day in spy.prices if start <= day <= end)
    if not trading_days:
        raise ValueError("SPY has no trading days inside the requested window")
    start_day, end_day = trading_days[0], trading_days[-1]

    scheduled: Dict[date, List[PortfolioSignal]] = defaultdict(list)
    results: Dict[str, Dict[str, object]] = {}
    for signal in signals:
        row = _empty_result(signal)
        results[signal.event_id] = row
        if signal.initial_exclusion:
            row.update(status="filtered", reason=signal.initial_exclusion)
            continue
        execution_day = _first_day_after(trading_days, signal.filing_date, inclusive=False)
        if execution_day is None:
            row.update(status="pending", reason="next_market_day_outside_window")
            continue
        scheduled[execution_day].append(signal)

    cash = float(starting_cash_usd)
    positions: Dict[str, _Position] = {}
    daily_values: List[float] = []
    daily_invested: List[float] = []
    total_buy_notional = 0.0
    total_sale_proceeds = 0.0
    strategy_exit_rows: List[Dict[str, object]] = []

    def position_value(ticker: str, day: date, at_open: bool = False) -> float:
        position = positions[ticker]
        series = price_series.get(ticker)
        if series is None:
            return 0.0
        point = series.prices.get(day)
        if at_open and point is not None:
            return position.shares * point.adjusted_open
        close = _latest_close(series, day, before=at_open)
        return position.shares * close if close is not None else 0.0

    for current_day in trading_days:
        daily_spent = 0.0
        exited_tickers_today = set()

        # Deterministische Exit-Prüfung am adjustierten Tages-Open, bevor neue
        # Senatorensignale verarbeitet werden. Tageskurse erlauben keine
        # ehrliche Intraday-Simulation; deshalb wird kein Hoch/Tief verwendet.
        if (
            stop_loss_pct is not None
            or take_profit_pct is not None
            or max_holding_days is not None
        ):
            for ticker in sorted(tuple(positions)):
                position = positions[ticker]
                series = price_series.get(ticker)
                point = series.prices.get(current_day) if series else None
                if point is None or position.shares <= 0 or position.opened_on is None:
                    continue
                avg_entry_price = position.entry_value_usd / position.shares
                return_pct = (point.adjusted_open / avg_entry_price - 1.0) * 100.0
                holding_days = max(0, (current_day - position.opened_on).days)
                exit_reason = ""
                if stop_loss_pct is not None and return_pct <= -stop_loss_pct:
                    exit_reason = "stop_loss"
                elif take_profit_pct is not None and return_pct >= take_profit_pct:
                    exit_reason = "take_profit"
                elif (
                    max_holding_days is not None
                    and holding_days >= max_holding_days
                ):
                    exit_reason = "max_holding_days"
                if not exit_reason:
                    continue

                position = positions.pop(ticker)
                proceeds = (
                    position.shares * point.adjusted_open * (1.0 - cost_per_side)
                )
                cash += proceeds
                total_sale_proceeds += proceeds
                exited_tickers_today.add(ticker)
                exit_row = {
                    field: "" for field in PORTFOLIO_RESULT_FIELDS
                }
                exit_row.update(
                    event_id="strategy-exit-{}-{}".format(
                        current_day.isoformat(), ticker
                    ),
                    senator="Strategy",
                    execution_date=current_day.isoformat(),
                    action="risk_exit",
                    ticker=ticker,
                    asset_type=series.instrument_type,
                    status="executed",
                    reason=exit_reason,
                    execution_price=f"{point.adjusted_open:.6f}",
                    notional_usd=f"{proceeds:.2f}",
                    shares=f"{-position.shares:.8f}",
                    cash_after_usd=f"{cash:.2f}",
                )
                strategy_exit_rows.append(exit_row)

        for signal in scheduled.get(current_day, []):
            row = results[signal.event_id]
            row["execution_date"] = current_day.isoformat()

            if signal.action == "sell" and signal.ticker not in positions:
                row.update(status="skipped", reason="no_position")
                continue

            if signal.action == "buy" and signal.ticker in exited_tickers_today:
                row.update(status="skipped", reason="same_day_strategy_exit")
                continue

            series = price_series.get(signal.ticker)
            if series is None or not series.prices:
                reason = series.error if series and series.error else "no_price_history"
                row.update(status="filtered", reason=reason)
                continue
            if series.instrument_type not in {"EQUITY", "ETF"}:
                row.update(
                    status="filtered",
                    reason="provider_instrument_type_{}".format(
                        series.instrument_type or "unknown"
                    ),
                )
                continue
            price = series.prices.get(current_day)
            if price is None:
                row.update(status="filtered", reason="no_security_price_on_execution_day")
                continue
            execution_price = price.adjusted_open

            if signal.action == "sell":
                position = positions.pop(signal.ticker)
                proceeds = position.shares * execution_price * (1.0 - cost_per_side)
                cash += proceeds
                total_sale_proceeds += proceeds
                row.update(
                    status="executed",
                    reason="position_closed",
                    execution_price=f"{execution_price:.6f}",
                    notional_usd=f"{proceeds:.2f}",
                    shares=f"{-position.shares:.8f}",
                    cash_after_usd=f"{cash:.2f}",
                )
                continue

            current_position_value = (
                position_value(signal.ticker, current_day, at_open=True)
                if signal.ticker in positions
                else 0.0
            )
            # Every leg of the limit check must be valued with information the
            # bot would actually have at the open.  Valuing the *other* holdings
            # at today's close (the previous behaviour) let the portfolio limit
            # react to a price that had not printed yet — a small but genuine
            # look-ahead in an otherwise clean simulation.
            current_portfolio_value = sum(
                position_value(ticker, current_day, at_open=True)
                for ticker in positions
            )
            skip_reason = ""
            if buy_notional_usd > cash:
                skip_reason = "cash_limit"
            elif current_position_value + buy_notional_usd > max_position_usd:
                skip_reason = "position_limit"
            elif current_portfolio_value + buy_notional_usd > max_portfolio_usd:
                skip_reason = "portfolio_limit"
            elif daily_spent + buy_notional_usd > max_daily_notional_usd:
                skip_reason = "daily_notional_limit"
            if skip_reason:
                row.update(status="skipped", reason=skip_reason)
                continue

            shares = buy_notional_usd * (1.0 - cost_per_side) / execution_price
            position = positions.setdefault(signal.ticker, _Position())
            if position.opened_on is None:
                position.opened_on = current_day
            position.shares += shares
            position.paid_notional_usd += buy_notional_usd
            position.entry_value_usd += shares * execution_price
            cash -= buy_notional_usd
            daily_spent += buy_notional_usd
            total_buy_notional += buy_notional_usd
            row.update(
                status="executed",
                reason="position_opened_or_increased",
                execution_price=f"{execution_price:.6f}",
                notional_usd=f"{buy_notional_usd:.2f}",
                shares=f"{shares:.8f}",
                cash_after_usd=f"{cash:.2f}",
            )

        invested = sum(position_value(ticker, current_day) for ticker in positions)
        daily_invested.append(invested)
        daily_values.append(cash + invested)

    ending_invested = daily_invested[-1]
    ending_value = daily_values[-1]
    liquidation_value = cash + ending_invested * (1.0 - cost_per_side)
    peak_value = daily_values[0]
    max_drawdown_pct = 0.0
    for value in daily_values:
        peak_value = max(peak_value, value)
        max_drawdown_pct = min(max_drawdown_pct, (value / peak_value - 1.0) * 100.0)

    month_end_values: Dict[str, Tuple[date, float]] = {}
    for trading_day, value in zip(trading_days, daily_values):
        month_end_values[trading_day.strftime("%Y-%m")] = (trading_day, value)
    monthly_returns = []
    previous_value = starting_cash_usd
    for month, (month_end_day, value) in sorted(month_end_values.items()):
        monthly_return = (value / previous_value - 1.0) * 100.0
        monthly_returns.append(
            {
                "month": month,
                "month_end": month_end_day.isoformat(),
                "ending_value_usd": value,
                "return_pct": monthly_return,
            }
        )
        previous_value = value
    monthly_return_values = [item["return_pct"] for item in monthly_returns]

    spy_entry = spy.prices[start_day].adjusted_open
    spy_exit = spy.prices[end_day].adjusted_close
    spy_multiplier = (1.0 - cost_per_side) * spy_exit / spy_entry
    spy_100k_value = starting_cash_usd * spy_multiplier
    risk_budget = min(starting_cash_usd, max_portfolio_usd)
    risk_matched_spy_value = (
        starting_cash_usd - risk_budget + risk_budget * spy_multiplier
    )

    ordered_rows = tuple(results[signal.event_id] for signal in signals) + tuple(
        strategy_exit_rows
    )
    status_counts = Counter(str(row["status"]) for row in ordered_rows)
    reason_counts = Counter(str(row["reason"]) for row in ordered_rows)
    executed_buys_by_senator = Counter(
        str(row["senator"])
        for row in ordered_rows
        if row["status"] == "executed" and row["action"] == "buy"
    )
    executed_buys_by_ticker = Counter(
        str(row["ticker"])
        for row in ordered_rows
        if row["status"] == "executed" and row["action"] == "buy"
    )
    executed_buy_count = sum(executed_buys_by_senator.values())
    largest_senator_buy_count = max(executed_buys_by_senator.values(), default=0)
    largest_ticker_buy_count = max(executed_buys_by_ticker.values(), default=0)
    limit_reasons = (
        "cash_limit",
        "position_limit",
        "portfolio_limit",
        "daily_notional_limit",
    )
    ending_positions = {
        ticker: {
            "shares": position.shares,
            "market_value_usd": position_value(ticker, end_day),
            "paid_notional_usd": position.paid_notional_usd,
        }
        for ticker, position in sorted(positions.items())
    }
    summary = {
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "market_start": start_day.isoformat(),
        "market_end": end_day.isoformat(),
        "starting_cash_usd": starting_cash_usd,
        "ending_cash_usd": cash,
        "ending_invested_usd": ending_invested,
        "ending_value_usd": ending_value,
        "liquidation_value_usd": liquidation_value,
        "return_pct": (ending_value / starting_cash_usd - 1.0) * 100.0,
        "liquidation_return_pct": (
            liquidation_value / starting_cash_usd - 1.0
        )
        * 100.0,
        "max_drawdown_pct": max_drawdown_pct,
        "average_invested_usd": sum(daily_invested) / len(daily_invested),
        "peak_invested_usd": max(daily_invested),
        "average_starting_cash_invested_pct": (
            sum(daily_invested) / len(daily_invested) / starting_cash_usd * 100.0
        ),
        "peak_starting_cash_invested_pct": (
            max(daily_invested) / starting_cash_usd * 100.0
        ),
        "average_portfolio_limit_utilization_pct": (
            sum(daily_invested) / len(daily_invested) / max_portfolio_usd * 100.0
        ),
        "total_buy_notional_usd": total_buy_notional,
        "total_sale_proceeds_usd": total_sale_proceeds,
        "turnover_usd": total_buy_notional + total_sale_proceeds,
        "spy_100k_value_usd": spy_100k_value,
        "spy_100k_return_pct": (spy_multiplier - 1.0) * 100.0,
        "risk_matched_spy_value_usd": risk_matched_spy_value,
        "risk_matched_spy_return_pct": (
            risk_matched_spy_value / starting_cash_usd - 1.0
        )
        * 100.0,
        "signal_count": len(signals),
        "strategy_exit_count": len(strategy_exit_rows),
        "strategy_exit_counts": dict(
            sorted(Counter(str(row["reason"]) for row in strategy_exit_rows).items())
        ),
        "status_counts": dict(sorted(status_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "limit_skip_counts": {
            reason: reason_counts.get(reason, 0) for reason in limit_reasons
        },
        "executed_buy_count": executed_buy_count,
        "executed_buys_by_senator": dict(executed_buys_by_senator.most_common()),
        "executed_buys_by_ticker": dict(executed_buys_by_ticker.most_common()),
        "largest_senator_buy_share": (
            largest_senator_buy_count / executed_buy_count
            if executed_buy_count
            else 0.0
        ),
        "largest_ticker_buy_share": (
            largest_ticker_buy_count / executed_buy_count
            if executed_buy_count
            else 0.0
        ),
        "monthly_returns": monthly_returns,
        "monthly_return_summary": {
            "month_count": len(monthly_returns),
            "best_month": max(
                monthly_returns, key=lambda item: item["return_pct"], default=None
            ),
            "worst_month": min(
                monthly_returns, key=lambda item: item["return_pct"], default=None
            ),
            "median_return_pct": statistics.median(monthly_return_values),
            "positive_month_count": sum(
                value > 0.0 for value in monthly_return_values
            ),
            "months_at_or_above_7_pct": sum(
                value >= 7.0 for value in monthly_return_values
            ),
        },
        "ending_positions": ending_positions,
    }
    return summary, ordered_rows


def write_portfolio_results(
    path: Path, rows: Sequence[Mapping[str, object]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=PORTFOLIO_RESULT_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def summarize_order_sensitivity(
    signals: Sequence[PortfolioSignal],
    price_series: Mapping[str, PriceSeries],
    start: date,
    end: date,
    runs: int = 200,
    **backtest_kwargs: float,
) -> Mapping[str, object]:
    """Measure the impact of unspecified same-day feed ordering on limit skips."""

    if runs < 1:
        raise ValueError("runs must be at least one")
    returns: List[float] = []
    risk_excess_returns: List[float] = []
    drawdowns: List[float] = []
    average_invested: List[float] = []
    peak_invested: List[float] = []
    turnovers: List[float] = []
    limit_skips: List[float] = []
    senator_concentration: List[float] = []
    ticker_concentration: List[float] = []
    for seed in range(runs):
        shuffled = list(signals)
        random.Random(seed).shuffle(shuffled)
        summary, _ = run_portfolio_backtest(
            shuffled, price_series, start, end, **backtest_kwargs
        )
        strategy_return = float(summary["return_pct"])
        risk_matched_return = float(summary["risk_matched_spy_return_pct"])
        returns.append(strategy_return)
        risk_excess_returns.append(strategy_return - risk_matched_return)
        drawdowns.append(float(summary["max_drawdown_pct"]))
        average_invested.append(float(summary["average_invested_usd"]))
        peak_invested.append(float(summary["peak_invested_usd"]))
        turnovers.append(float(summary["turnover_usd"]))
        limit_skips.append(
            float(sum(summary["limit_skip_counts"].values()))
        )
        senator_concentration.append(float(summary["largest_senator_buy_share"]))
        ticker_concentration.append(float(summary["largest_ticker_buy_share"]))

    returns.sort()

    def percentile(values: Sequence[float], fraction: float) -> float:
        ordered = sorted(values)
        index = (len(ordered) - 1) * fraction
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        weight = index - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    return {
        "runs": runs,
        "min_return_pct": min(returns),
        "p05_return_pct": percentile(returns, 0.05),
        "median_return_pct": statistics.median(returns),
        "mean_return_pct": statistics.mean(returns),
        "p95_return_pct": percentile(returns, 0.95),
        "max_return_pct": max(returns),
        "share_positive": sum(value > 0.0 for value in returns) / runs,
        "share_beating_risk_matched_spy": sum(
            value > 0.0 for value in risk_excess_returns
        )
        / runs,
        "median_max_drawdown_pct": statistics.median(drawdowns),
        "worst_max_drawdown_pct": min(drawdowns),
        "median_average_invested_usd": statistics.median(average_invested),
        "median_peak_invested_usd": statistics.median(peak_invested),
        "median_turnover_usd": statistics.median(turnovers),
        "median_limit_skip_count": statistics.median(limit_skips),
        "median_largest_senator_buy_share": statistics.median(
            senator_concentration
        ),
        "median_largest_ticker_buy_share": statistics.median(ticker_concentration),
    }
