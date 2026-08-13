from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional


PERSON_SEPARATOR_PATTERN = re.compile(r"[^a-z0-9]+")
PERSON_IGNORED_TOKENS = {
    "hon",
    "honorable",
    "ii",
    "iii",
    "iv",
    "jr",
    "mr",
    "mrs",
    "ms",
    "sen",
    "senator",
    "sr",
}
ASSET_TYPE_ALIASES = {
    "stock": "stock",
    "stocks": "stock",
    "equity": "stock",
    "common stock": "stock",
    "ordinary shares": "stock",
    "etf": "etf",
    "exchange traded fund": "etf",
    "exchange-traded fund": "etf",
}


def parse_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    for pattern in ("%m/%d/%Y", "%m/%d/%y", "%d %b %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def normalize_action(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if text.startswith("purchase") or text.startswith("buy"):
        return "buy"
    if text.startswith("sale") or text.startswith("sell"):
        return "sell"
    return "unsupported"


def normalize_person_name(value: Any) -> str:
    """Return a comparison key for the name variants used by disclosure feeds."""

    text = unicodedata.normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode("ascii")
    if "," in text:
        family_name, given_names = text.split(",", 1)
        text = "{} {}".format(given_names, family_name)

    tokens = PERSON_SEPARATOR_PATTERN.sub(" ", text.casefold()).split()
    return " ".join(
        token
        for token in tokens
        if len(token) > 1 and token not in PERSON_IGNORED_TOKENS
    )


def normalize_ticker(value: Any) -> str:
    """Normalize common disclosure notation without guessing missing symbols."""

    text = str(value or "").strip().upper()
    if text.startswith("$"):
        text = text[1:]
    return text.replace("/", ".").replace(" ", "")


def normalize_asset_type(value: Any) -> str:
    text = " ".join(str(value or "").strip().casefold().split())
    return ASSET_TYPE_ALIASES.get(text, "unsupported")


@dataclass(frozen=True)
class Trade:
    event_id: str
    representative: str
    chamber: str
    ticker: str
    action: str
    transaction_date: Optional[date]
    report_date: Optional[date]
    amount_range: str
    ticker_type: str
    raw: Dict[str, Any]

    @classmethod
    def from_quiver(cls, raw: Dict[str, Any]) -> "Trade":
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
        event_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return cls(
            event_id=event_id,
            representative=str(raw.get("Representative") or raw.get("Name") or "").strip(),
            chamber=str(raw.get("House") or raw.get("Chamber") or "").strip(),
            ticker=normalize_ticker(raw.get("Ticker")),
            action=normalize_action(raw.get("Transaction") or raw.get("Type")),
            transaction_date=parse_date(raw.get("TransactionDate") or raw.get("Traded")),
            report_date=parse_date(raw.get("ReportDate") or raw.get("Published")),
            amount_range=str(raw.get("Range") or raw.get("Amount") or "").strip(),
            ticker_type=normalize_asset_type(
                raw.get("TickerType") or raw.get("AssetType")
            ),
            raw=raw,
        )


@dataclass(frozen=True)
class PlannedAction:
    trade: Trade
    action: str
    reason: str
    notional_usd: Optional[float] = None


@dataclass(frozen=True)
class ExecutionResult:
    event_id: str
    ticker: str
    action: str
    status: str
    message: str
    broker_order_id: Optional[str] = None
