from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from .models import normalize_asset_type


@dataclass(frozen=True)
class SourceConfig:
    provider: str
    endpoint: str
    chamber: str
    politicians: List[str]
    max_report_age_days: int
    file: str = ""


@dataclass(frozen=True)
class StrategyConfig:
    buy_notional_usd: float
    sell_policy: str
    allowed_ticker_types: List[str]
    require_market_open: bool
    max_position_usd: float
    max_portfolio_usd: float
    max_daily_notional_usd: float
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    max_holding_days: Optional[int] = None


@dataclass(frozen=True)
class StorageConfig:
    database: str


@dataclass(frozen=True)
class AppConfig:
    source: SourceConfig
    strategy: StrategyConfig
    storage: StorageConfig


def load_config(path: str) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    source_data = data.get("source", {})
    strategy_data = data.get("strategy", {})
    storage_data = data.get("storage", {})

    source = SourceConfig(
        provider=str(source_data.get("provider", "quiver")).casefold(),
        endpoint=str(
            source_data.get(
                "endpoint", "https://api.quiverquant.com/beta/live/congresstrading"
            )
        ),
        chamber=str(source_data.get("chamber", "Senate")),
        politicians=[str(item).strip() for item in source_data.get("politicians", [])],
        max_report_age_days=int(source_data.get("max_report_age_days", 7)),
        file=str(source_data.get("file", "")),
    )
    strategy = StrategyConfig(
        buy_notional_usd=float(strategy_data.get("buy_notional_usd", 1_000.0)),
        sell_policy=str(strategy_data.get("sell_policy", "close_position")),
        allowed_ticker_types=[
            normalize_asset_type(item)
            for item in strategy_data.get("allowed_ticker_types", ["Stock", "ETF"])
        ],
        require_market_open=bool(strategy_data.get("require_market_open", True)),
        max_position_usd=float(strategy_data.get("max_position_usd", 3_000.0)),
        max_portfolio_usd=float(strategy_data.get("max_portfolio_usd", 20_000.0)),
        max_daily_notional_usd=float(strategy_data.get("max_daily_notional_usd", 5_000.0)),
        stop_loss_pct=_optional_float(strategy_data, "stop_loss_pct"),
        take_profit_pct=_optional_float(strategy_data, "take_profit_pct"),
        max_holding_days=_optional_int(strategy_data, "max_holding_days"),
    )
    database = Path(str(storage_data.get("database", "var/state.sqlite3")))
    if not database.is_absolute():
        database = config_path.parent / database
    storage = StorageConfig(database=str(database.resolve()))

    _validate(source, strategy)
    return AppConfig(source=source, strategy=strategy, storage=storage)


def _validate(source: SourceConfig, strategy: StrategyConfig) -> None:
    if source.provider not in {"quiver", "json"}:
        raise ValueError("source.provider muss 'quiver' oder 'json' sein")
    if source.provider == "quiver":
        endpoint = urlparse(source.endpoint)
        if endpoint.scheme != "https" or endpoint.netloc.casefold() != "api.quiverquant.com":
            raise ValueError(
                "Quiver-Endpunkt muss HTTPS auf api.quiverquant.com verwenden"
            )
    if source.provider == "json" and not source.file:
        raise ValueError("source.file fehlt für den JSON-Provider")
    if not source.politicians:
        raise ValueError("Mindestens ein Politiker muss konfiguriert sein")
    if not 0 <= source.max_report_age_days <= 45:
        raise ValueError("max_report_age_days muss zwischen 0 und 45 liegen")
    if not 1 <= strategy.buy_notional_usd <= 100_000:
        raise ValueError("buy_notional_usd muss zwischen 1 und 100000 liegen")
    if strategy.sell_policy != "close_position":
        raise ValueError("Im MVP wird nur sell_policy='close_position' unterstützt")
    if not strategy.allowed_ticker_types:
        raise ValueError("allowed_ticker_types darf nicht leer sein")
    if any(item not in {"stock", "etf"} for item in strategy.allowed_ticker_types):
        raise ValueError("allowed_ticker_types darf nur eindeutige Aktien und ETFs enthalten")
    if not 1 <= strategy.max_position_usd <= 1_000_000:
        raise ValueError("max_position_usd muss zwischen 1 und 1000000 liegen")
    if not 1 <= strategy.max_portfolio_usd <= 1_000_000:
        raise ValueError("max_portfolio_usd muss zwischen 1 und 1000000 liegen")
    if not 1 <= strategy.max_daily_notional_usd <= 1_000_000:
        raise ValueError("max_daily_notional_usd muss zwischen 1 und 1000000 liegen")
    if strategy.buy_notional_usd > strategy.max_position_usd:
        raise ValueError("buy_notional_usd darf max_position_usd nicht überschreiten")
    if strategy.max_position_usd > strategy.max_portfolio_usd:
        raise ValueError("max_position_usd darf max_portfolio_usd nicht überschreiten")
    if strategy.buy_notional_usd > strategy.max_daily_notional_usd:
        raise ValueError("buy_notional_usd darf max_daily_notional_usd nicht überschreiten")
    if strategy.stop_loss_pct is not None and not (
        math.isfinite(strategy.stop_loss_pct) and 0 < strategy.stop_loss_pct <= 100
    ):
        raise ValueError("stop_loss_pct muss größer 0 und höchstens 100 sein")
    if strategy.take_profit_pct is not None and not (
        math.isfinite(strategy.take_profit_pct) and 0 < strategy.take_profit_pct <= 1_000
    ):
        raise ValueError("take_profit_pct muss größer 0 und höchstens 1000 sein")
    if strategy.max_holding_days is not None and not (
        1 <= strategy.max_holding_days <= 3_650
    ):
        raise ValueError("max_holding_days muss zwischen 1 und 3650 liegen")


def _optional_float(data: dict, key: str) -> Optional[float]:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("{} muss eine Zahl oder null sein".format(key))
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("{} muss eine Zahl oder null sein".format(key)) from exc


def _optional_int(data: dict, key: str) -> Optional[int]:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("{} muss eine ganze Zahl oder null sein".format(key))
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("{} muss eine ganze Zahl oder null sein".format(key)) from exc
