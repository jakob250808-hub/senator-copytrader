from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple

from .broker import BrokerResult, OpenPosition, PaperBroker
from .config import AppConfig
from .models import (
    ExecutionResult,
    PlannedAction,
    Trade,
    normalize_asset_type,
    normalize_person_name,
)
from .source import TradeSource
from .storage import StateStore


TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


class SafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class _StrategyExitCandidate:
    ticker: str
    reason_code: str
    reason_text: str
    position: OpenPosition
    opened_on: date
    holding_days: int
    return_pct: Optional[float]


class CopyEngine:
    def __init__(
        self,
        config: AppConfig,
        source: TradeSource,
        store: StateStore,
        broker: PaperBroker,
    ) -> None:
        self.config = config
        self.source = source
        self.store = store
        self.broker = broker

    def selected_trades(self) -> List[Trade]:
        chamber = self.config.source.chamber.casefold()
        names = {normalize_person_name(name) for name in self.config.source.politicians}
        return [
            trade
            for trade in self.source.fetch()
            if trade.chamber.casefold() == chamber
            and normalize_person_name(trade.representative) in names
        ]

    def bootstrap(self) -> int:
        return self.store.bootstrap(self.selected_trades(), self.selection_key())

    def selection_key(self) -> str:
        selection = "{}|{}".format(
            self.config.source.chamber.casefold(),
            "|".join(sorted(name.casefold() for name in self.config.source.politicians)),
        )
        return hashlib.sha256(selection.encode("utf-8")).hexdigest()

    def plan(self, today: date = None) -> List[PlannedAction]:
        current_date = today or date.today()
        cutoff = current_date - timedelta(days=self.config.source.max_report_age_days)
        allowed_types = {
            normalize_asset_type(item) for item in self.config.strategy.allowed_ticker_types
        }
        actions: List[PlannedAction] = []

        trades = sorted(
            self.selected_trades(),
            key=lambda item: (item.report_date or date.min, item.transaction_date or date.min),
        )
        for trade in trades:
            if self.store.contains(trade.event_id):
                continue
            if not trade.report_date or trade.report_date < cutoff:
                continue
            if trade.action not in {"buy", "sell"}:
                continue
            if trade.ticker_type not in allowed_types:
                continue
            if not TICKER_PATTERN.fullmatch(trade.ticker):
                continue
            if trade.action == "buy":
                actions.append(
                    PlannedAction(
                        trade=trade,
                        action="buy",
                        reason="Neu veröffentlichter Senatoren-Kauf",
                        notional_usd=self.config.strategy.buy_notional_usd,
                    )
                )
            else:
                actions.append(
                    PlannedAction(
                        trade=trade,
                        action="close_position",
                        reason="Neu veröffentlichter Senatoren-Verkauf; niemals leerverkaufen",
                    )
                )
        return actions

    def execute(self, today: date = None) -> List[ExecutionResult]:
        if not self.store.is_bootstrapped(self.selection_key()):
            raise SafetyError(
                "Zuerst 'bootstrap' für diese Senatoren-Auswahl ausführen, "
                "damit keine alten Meldungen gehandelt werden"
            )
        if self.config.strategy.require_market_open and not self.broker.is_market_open():
            raise SafetyError("US-Aktienmarkt ist geschlossen; es wurden keine Ereignisse verbraucht")

        self.broker.validate()
        current_date = today or date.today()
        strategy = self.config.strategy
        snapshot = self.broker.get_account_snapshot()

        # Unabhängige Risikoregeln laufen vor neuen Signalen. Sie werden nur
        # für Positionen angewendet, deren Kauf in der lokalen Bot-Historie
        # steht; Ticker ohne lokalen Bot-Kauf bleiben unberührt. Übermittelte
        # Schließungen geben erst im nächsten Snapshot neues Cash/Portfoliobudget
        # frei.
        exit_results, exit_tickers = self._execute_strategy_exits(current_date)

        # Laufende Zähler für Geld-, Positions- und Portfoliolimits. Sie werden
        # während dieses Laufs mitgeführt, damit mehrere Käufe im selben Lauf
        # sich gegenseitig korrekt begrenzen (nicht nur der einzelne Aufruf).
        remaining_cash = snapshot.cash
        portfolio_invested = snapshot.invested_usd()
        position_invested: Dict[str, float] = dict(snapshot.position_values)
        daily_spent = self.store.daily_buy_notional(current_date)

        results: List[ExecutionResult] = list(exit_results)
        for planned in self.plan(today=today):
            trade = planned.trade
            client_order_id = "senate-{}".format(trade.event_id[:32])

            if planned.action == "buy":
                notional = float(planned.notional_usd)
                ticker = trade.ticker.upper()
                skip_reason = None
                if ticker in exit_tickers:
                    skip_reason = (
                        "Ticker wurde in diesem Lauf durch eine unabhängige "
                        "Exit-Regel geschlossen; kein sofortiger Wiedereinstieg"
                    )
                elif notional > remaining_cash:
                    skip_reason = (
                        "Nicht genug freies Paper-Cash ({:.2f} USD verfügbar); "
                        "kein Kauf auf Margin".format(remaining_cash)
                    )
                elif position_invested.get(ticker, 0.0) + notional > strategy.max_position_usd:
                    skip_reason = "Positionslimit für {} erreicht ({:.2f} USD)".format(
                        ticker, strategy.max_position_usd
                    )
                elif portfolio_invested + notional > strategy.max_portfolio_usd:
                    skip_reason = "Portfoliolimit erreicht ({:.2f} USD)".format(
                        strategy.max_portfolio_usd
                    )
                elif daily_spent + notional > strategy.max_daily_notional_usd:
                    skip_reason = "Tageslimit erreicht ({:.2f} USD)".format(
                        strategy.max_daily_notional_usd
                    )

                if skip_reason is not None:
                    broker_result = BrokerResult("skipped", skip_reason)
                else:
                    broker_result = self.broker.buy_notional(ticker, notional, client_order_id)
                    if broker_result.status == "submitted":
                        remaining_cash -= notional
                        portfolio_invested += notional
                        position_invested[ticker] = position_invested.get(ticker, 0.0) + notional
                        daily_spent += notional

                self.store.record(
                    trade,
                    broker_result.status,
                    broker_order_id=broker_result.order_id,
                    details=broker_result.message,
                    notional_usd=notional,
                    processed_on=current_date,
                )
            else:
                ticker = trade.ticker.upper()
                if ticker in exit_tickers:
                    broker_result = BrokerResult(
                        "skipped",
                        "Ticker wurde in diesem Lauf bereits durch eine "
                        "unabhängige Exit-Regel geschlossen",
                    )
                else:
                    broker_result = self.broker.close_position(trade.ticker)
                if broker_result.status == "submitted":
                    closed_value = position_invested.pop(ticker, 0.0)
                    portfolio_invested = max(0.0, portfolio_invested - closed_value)
                self.store.record(
                    trade,
                    broker_result.status,
                    broker_order_id=broker_result.order_id,
                    details=broker_result.message,
                    processed_on=current_date,
                )

            results.append(
                ExecutionResult(
                    event_id=trade.event_id,
                    ticker=trade.ticker,
                    action=planned.action,
                    status=broker_result.status,
                    message=broker_result.message,
                    broker_order_id=broker_result.order_id,
                )
            )
        return results

    def preview_strategy_exits(self, today: date = None) -> List[ExecutionResult]:
        """Zeige mechanische Exits mit Brokerkursen, ohne Orders zu senden."""

        current_date = today or date.today()
        return [
            ExecutionResult(
                event_id="strategy-exit-{}-{}".format(
                    current_date.isoformat(), candidate.ticker
                ),
                ticker=candidate.ticker,
                action="close_position",
                status="planned",
                message=_exit_details(
                    reason_text=candidate.reason_text,
                    opened_on=candidate.opened_on,
                    holding_days=candidate.holding_days,
                    avg_entry_price=candidate.position.avg_entry_price,
                    current_price=candidate.position.current_price,
                    return_pct=candidate.return_pct,
                    broker_message="Keine Order gesendet (Vorschau)",
                ),
            )
            for candidate in self._strategy_exit_candidates(current_date)
        ]

    def _execute_strategy_exits(
        self, current_date: date
    ) -> Tuple[List[ExecutionResult], Set[str]]:
        results: List[ExecutionResult] = []
        triggered_tickers: Set[str] = set()
        for candidate in self._strategy_exit_candidates(current_date):
            ticker = candidate.ticker
            position = candidate.position
            triggered_tickers.add(ticker)
            if self.broker.has_pending_close_order(ticker):
                broker_result = BrokerResult(
                    "skipped", "Schließungsorder ist bereits beim Broker offen"
                )
            else:
                broker_result = self.broker.close_position(ticker)

            details = _exit_details(
                reason_text=candidate.reason_text,
                opened_on=candidate.opened_on,
                holding_days=candidate.holding_days,
                avg_entry_price=position.avg_entry_price,
                current_price=position.current_price,
                return_pct=candidate.return_pct,
                broker_message=broker_result.message,
            )
            event_id = self.store.record_strategy_exit(
                ticker=ticker,
                status=broker_result.status,
                reason=candidate.reason_code,
                details=details,
                broker_order_id=broker_result.order_id,
                processed_on=current_date,
                notional_usd=position.market_value,
            )
            results.append(
                ExecutionResult(
                    event_id=event_id,
                    ticker=ticker,
                    action="close_position",
                    status=broker_result.status,
                    message=details,
                    broker_order_id=broker_result.order_id,
                )
            )
        return results, triggered_tickers

    def _strategy_exit_candidates(
        self, current_date: date
    ) -> List[_StrategyExitCandidate]:
        strategy = self.config.strategy
        if (
            strategy.stop_loss_pct is None
            and strategy.take_profit_pct is None
            and strategy.max_holding_days is None
        ):
            return []

        candidates: List[_StrategyExitCandidate] = []
        for ticker, position in sorted(self.broker.get_open_positions().items()):
            if position.side != "long":
                continue
            opened_on = self.store.position_opened_on(ticker)
            if opened_on is None:
                # Kein lokal übermittelter Kauf: vermutlich manuelle/fremde
                # Paperposition. Der Bot darf sie nicht eigenmächtig schließen.
                continue

            return_pct = _position_return_pct(
                position.avg_entry_price,
                position.current_price,
                position.unrealized_return_pct,
            )
            holding_days = max(0, (current_date - opened_on).days)
            reason_code = ""
            reason_text = ""
            if (
                strategy.stop_loss_pct is not None
                and return_pct is not None
                and return_pct <= -strategy.stop_loss_pct
            ):
                reason_code = "stop_loss"
                reason_text = "Stop-Loss ausgelöst"
            elif (
                strategy.take_profit_pct is not None
                and return_pct is not None
                and return_pct >= strategy.take_profit_pct
            ):
                reason_code = "take_profit"
                reason_text = "Take-Profit ausgelöst"
            elif (
                strategy.max_holding_days is not None
                and holding_days >= strategy.max_holding_days
            ):
                reason_code = "max_holding_days"
                reason_text = "Maximale Haltefrist erreicht"
            if reason_code:
                candidates.append(
                    _StrategyExitCandidate(
                        ticker=ticker,
                        reason_code=reason_code,
                        reason_text=reason_text,
                        position=position,
                        opened_on=opened_on,
                        holding_days=holding_days,
                        return_pct=return_pct,
                    )
                )
        return candidates


def _position_return_pct(
    avg_entry_price: Optional[float],
    current_price: Optional[float],
    broker_return_pct: Optional[float],
) -> Optional[float]:
    if (
        avg_entry_price is not None
        and current_price is not None
        and avg_entry_price > 0
        and current_price >= 0
    ):
        return (current_price / avg_entry_price - 1.0) * 100.0
    return broker_return_pct


def _exit_details(
    reason_text: str,
    opened_on: date,
    holding_days: int,
    avg_entry_price: Optional[float],
    current_price: Optional[float],
    return_pct: Optional[float],
    broker_message: str,
) -> str:
    def number(value: Optional[float]) -> str:
        return "unbekannt" if value is None else "{:.4f}".format(value)

    return (
        "{}; Einstiegstag {}; Haltedauer {} Kalendertage; "
        "Einstiegspreis {}; beobachteter Kurs {}; Ergebnis {} %; {}"
    ).format(
        reason_text,
        opened_on.isoformat(),
        holding_days,
        number(avg_entry_price),
        number(current_price),
        number(return_pct),
        broker_message,
    )
