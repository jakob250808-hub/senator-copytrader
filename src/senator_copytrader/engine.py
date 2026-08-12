from __future__ import annotations

import re
import hashlib
from datetime import date, timedelta
from typing import Dict, List

from .broker import BrokerResult, PaperBroker
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

        # Laufende Zähler für Geld-, Positions- und Portfoliolimits. Sie werden
        # während dieses Laufs mitgeführt, damit mehrere Käufe im selben Lauf
        # sich gegenseitig korrekt begrenzen (nicht nur der einzelne Aufruf).
        remaining_cash = snapshot.cash
        portfolio_invested = snapshot.invested_usd()
        position_invested: Dict[str, float] = dict(snapshot.position_values)
        daily_spent = self.store.daily_buy_notional(current_date)

        results: List[ExecutionResult] = []
        for planned in self.plan(today=today):
            trade = planned.trade
            client_order_id = "senate-{}".format(trade.event_id[:32])

            if planned.action == "buy":
                notional = float(planned.notional_usd)
                ticker = trade.ticker.upper()
                skip_reason = None
                if notional > remaining_cash:
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
                )
            else:
                broker_result = self.broker.close_position(trade.ticker)
                if broker_result.status == "submitted":
                    closed_value = position_invested.pop(trade.ticker.upper(), 0.0)
                    portfolio_invested = max(0.0, portfolio_invested - closed_value)
                self.store.record(
                    trade,
                    broker_result.status,
                    broker_order_id=broker_result.order_id,
                    details=broker_result.message,
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
