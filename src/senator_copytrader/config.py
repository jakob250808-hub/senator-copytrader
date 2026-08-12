from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List
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
