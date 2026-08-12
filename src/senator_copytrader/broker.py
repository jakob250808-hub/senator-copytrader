from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class BrokerError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrokerResult:
    status: str
    message: str
    order_id: Optional[str] = None


@dataclass(frozen=True)
class AccountSnapshot:
    """Kontostand-Ausschnitt für die lokale Limitprüfung.

    ``cash`` wird bewusst statt ``buying_power`` als Obergrenze für neue Käufe
    verwendet: ``buying_power`` schließt bei Alpaca-Margin-Konten geliehenes
    Kapital ein. Indem wir Käufe niemals über ``cash`` hinaus zulassen, kann
    der Bot strukturell nie auf Margin handeln, unabhängig davon, wie das
    Paperkonto in Alpaca konfiguriert ist.
    """

    cash: float
    portfolio_value: float
    is_margin_account: bool
    position_values: Dict[str, float] = field(default_factory=dict)

    def invested_usd(self) -> float:
        return sum(self.position_values.values())

    def position_usd(self, symbol: str) -> float:
        return self.position_values.get(symbol.upper(), 0.0)


class PaperBroker:
    def validate(self) -> str:
        raise NotImplementedError

    def is_market_open(self) -> bool:
        raise NotImplementedError

    def get_account_snapshot(self) -> AccountSnapshot:
        raise NotImplementedError

    def buy_notional(self, symbol: str, notional_usd: float, client_order_id: str) -> BrokerResult:
        raise NotImplementedError

    def close_position(self, symbol: str) -> BrokerResult:
        raise NotImplementedError


class AlpacaPaperBroker(PaperBroker):
    """Alpaca adapter deliberately hard-wired to the paper REST endpoint."""

    BASE_URL = "https://paper-api.alpaca.markets"

    def __init__(self, api_key: str = "", secret_key: str = "") -> None:
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY", "")

    def validate(self) -> str:
        account = self._request("GET", "/v2/account")
        if not isinstance(account, dict):
            raise BrokerError("Unerwartete Antwort vom Alpaca-Paperkonto")
        if bool(account.get("trading_blocked", False)):
            raise BrokerError("Das Alpaca-Paperkonto ist für Trading gesperrt")
        return str(account.get("account_number", "paper-account"))

    def is_market_open(self) -> bool:
        clock = self._request("GET", "/v2/clock")
        if not isinstance(clock, dict) or "is_open" not in clock:
            raise BrokerError("Unerwartete Antwort von der Alpaca-Marktuhr")
        return bool(clock["is_open"])

    def get_account_snapshot(self) -> AccountSnapshot:
        account = self._request("GET", "/v2/account")
        if not isinstance(account, dict):
            raise BrokerError("Unerwartete Antwort vom Alpaca-Paperkonto")
        positions = self._positions()
        position_values = {
            str(position.get("symbol", "")).upper(): abs(float(position.get("market_value", 0.0) or 0.0))
            for position in positions
        }
        multiplier = float(account.get("multiplier", 1) or 1)
        return AccountSnapshot(
            cash=float(account.get("cash", 0.0) or 0.0),
            portfolio_value=float(account.get("portfolio_value", 0.0) or 0.0),
            is_margin_account=multiplier > 1,
            position_values=position_values,
        )

    def _positions(self) -> list:
        positions = self._request("GET", "/v2/positions")
        if not isinstance(positions, list):
            raise BrokerError("Unerwartete Antwort für Alpaca-Positionen")
        return [position for position in positions if isinstance(position, dict)]

    def buy_notional(self, symbol: str, notional_usd: float, client_order_id: str) -> BrokerResult:
        asset = self._request("GET", "/v2/assets/{}".format(quote(symbol, safe="")))
        if not isinstance(asset, dict):
            raise BrokerError("Unerwartete Asset-Antwort für {}".format(symbol))
        if str(asset.get("class", "")).casefold() != "us_equity":
            return BrokerResult("skipped", "Ticker ist keine eindeutige US-Aktie oder kein ETF")
        if str(asset.get("status", "")).casefold() != "active":
            return BrokerResult("skipped", "Ticker ist bei Alpaca nicht aktiv")
        if not bool(asset.get("tradable", False)):
            return BrokerResult("skipped", "Ticker ist bei Alpaca nicht handelbar")
        if not bool(asset.get("fractionable", False)):
            return BrokerResult("skipped", "Ticker unterstützt keine Dollar-/Teilorders")

        order = self._request(
            "POST",
            "/v2/orders",
            {
                "symbol": symbol.upper(),
                "notional": "{:.2f}".format(notional_usd),
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
                "client_order_id": client_order_id,
            },
        )
        if not isinstance(order, dict) or not order.get("id"):
            raise BrokerError("Unerwartete Order-Antwort für {}".format(symbol))
        return BrokerResult("submitted", "Paper-Kauf übermittelt", str(order["id"]))

    def close_position(self, symbol: str) -> BrokerResult:
        asset = self._request("GET", "/v2/assets/{}".format(quote(symbol, safe="")))
        if not isinstance(asset, dict):
            raise BrokerError("Unerwartete Asset-Antwort für {}".format(symbol))
        if str(asset.get("class", "")).casefold() != "us_equity":
            return BrokerResult("skipped", "Ticker ist keine eindeutige US-Aktie oder kein ETF")
        if str(asset.get("status", "")).casefold() != "active":
            return BrokerResult("skipped", "Ticker ist bei Alpaca nicht aktiv")
        if not bool(asset.get("tradable", False)):
            return BrokerResult("skipped", "Ticker ist bei Alpaca nicht handelbar")
        held_symbols = {position.get("symbol", "").upper() for position in self._positions()}
        if symbol.upper() not in held_symbols:
            return BrokerResult("skipped", "Keine Paper-Position vorhanden; kein Leerverkauf")

        order = self._request(
            "DELETE", "/v2/positions/{}".format(quote(symbol, safe=""))
        )
        if not isinstance(order, dict) or not order.get("id"):
            raise BrokerError("Unerwartete Schließungsantwort für {}".format(symbol))
        return BrokerResult("submitted", "Paper-Position wird geschlossen", str(order["id"]))

    def _request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Any:
        if not self.api_key or not self.secret_key:
            raise BrokerError("ALPACA_API_KEY oder ALPACA_SECRET_KEY fehlt")

        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            self.BASE_URL + path,
            data=body,
            method=method,
            headers={
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.secret_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "senator-copytrader/0.1",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                response_body = response.read()
            if not response_body:
                return None
            return json.loads(response_body.decode("utf-8"))
        except HTTPError as exc:
            message = "HTTP {}".format(exc.code)
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
                if isinstance(error_payload, dict) and error_payload.get("message"):
                    message = "{}: {}".format(message, str(error_payload["message"])[:300])
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                pass
            raise BrokerError("Alpaca-Paper-API antwortete mit {}".format(message)) from exc
        except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BrokerError("Alpaca-Paper-API nicht erreichbar: {}".format(exc)) from exc
