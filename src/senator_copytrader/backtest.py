from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote
from urllib.request import Request, urlopen

from .models import normalize_person_name, parse_date


TARGET_SENATORS = (
    "Thomas H Tuberville",
    "Sheldon Whitehouse",
    "Shelley M Capito",
    "Susan M Collins",
    "Markwayne Mullin",
    "John Boozman",
    "David H McCormick",
    "Rick Scott",
    "Ron L Wyden",
    "Jerry Moran",
)

YAHOO_CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?period1={start}&period2={end}&interval=1d&events=history"
    "&includeAdjustedClose=true"
)
TICKER_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,9}")
YAHOO_TICKER_PATTERN = re.compile(r"[?&]s=([^&\"']+)", re.IGNORECASE)
RESULT_FIELDS = (
    "event_id",
    "senator",
    "disclosure_date",
    "transaction_date",
    "ticker",
    "asset_type",
    "amount_range",
    "status",
    "exclusion_reason",
    "entry_date",
    "exit_date",
    "entry_adjusted_open",
    "exit_adjusted_close",
    "spy_entry_adjusted_open",
    "spy_exit_adjusted_close",
    "notional_usd",
    "strategy_final_usd",
    "spy_final_usd",
    "strategy_return_pct",
    "spy_return_pct",
    "excess_return_pct_points",
)


@dataclass(frozen=True)
class Candidate:
    event_id: str
    senator: str
    disclosure_date: Optional[date]
    transaction_date: Optional[date]
    ticker: str
    asset_type: str
    amount_range: str
    initial_exclusion: str = ""


@dataclass(frozen=True)
class PricePoint:
    adjusted_open: float
    adjusted_close: float


@dataclass(frozen=True)
class PriceSeries:
    symbol: str
    instrument_type: str
    prices: Mapping[date, PricePoint]
    error: str = ""


@dataclass(frozen=True)
class Extraction:
    candidates: Sequence[Candidate]
    filings_by_senator: Mapping[str, int]
    transactions_by_senator: Mapping[str, int]


def _parse_ticker(value: object) -> str:
    text = html.unescape(str(value or "").strip())
    link_match = YAHOO_TICKER_PATTERN.search(text)
    if link_match:
        text = unquote(link_match.group(1))
    else:
        text = re.sub(r"<[^>]+>", "", text).strip()
    ticker = text.upper().replace("/", ".")
    if ticker in {"", "--", "N/A", "NA"} or not TICKER_PATTERN.fullmatch(ticker):
        return ""
    return ticker


def _yahoo_symbol(ticker: str) -> str:
    return ticker.replace(".", "-")


def _candidate_id(filing_identity: str, raw: Mapping[str, object], occurrence: int) -> str:
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
    identity = f"{filing_identity}\n{canonical}\n{occurrence}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def load_purchase_candidates(
    data_dir: Path, target_senators: Sequence[str] = TARGET_SENATORS
) -> Extraction:
    """Load and deduplicate purchases from daily Senate disclosure files."""

    target_by_key = {normalize_person_name(name): name for name in target_senators}
    candidates: Dict[str, Candidate] = {}
    filing_ids = {name: set() for name in target_senators}
    transaction_ids = {name: set() for name in target_senators}

    for path in sorted(data_dir.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            filings = json.load(handle)
        for filing in filings:
            raw_name = " ".join(
                f"{filing.get('first_name', '')} {filing.get('last_name', '')}".split()
            )
            senator = target_by_key.get(normalize_person_name(raw_name))
            if senator is None:
                continue
            ptr_link = str(filing.get("ptr_link") or "")
            filing_identity = ptr_link or json.dumps(
                {
                    "name": raw_name,
                    "received": filing.get("date_recieved"),
                    "transactions": filing.get("transactions"),
                },
                sort_keys=True,
            )
            filing_ids[senator].add(filing_identity)
            occurrences: Counter[str] = Counter()
            for transaction in filing.get("transactions") or []:
                canonical = json.dumps(
                    transaction, sort_keys=True, separators=(",", ":"), default=str
                )
                occurrence = occurrences[canonical]
                occurrences[canonical] += 1
                event_id = _candidate_id(filing_identity, transaction, occurrence)
                transaction_ids[senator].add(event_id)
                if str(transaction.get("type") or "").strip() != "Purchase":
                    continue
                asset_type = str(transaction.get("asset_type") or "").strip()
                ticker = _parse_ticker(transaction.get("ticker"))
                exclusion = ""
                if asset_type != "Stock":
                    exclusion = "source_asset_type_not_stock"
                elif not ticker:
                    exclusion = "invalid_or_missing_ticker"
                disclosure_date = parse_date(filing.get("date_recieved"))
                if disclosure_date is None:
                    exclusion = exclusion or "invalid_disclosure_date"
                candidate = Candidate(
                    event_id=event_id,
                    senator=senator,
                    disclosure_date=disclosure_date,
                    transaction_date=parse_date(transaction.get("transaction_date")),
                    ticker=ticker,
                    asset_type=asset_type,
                    amount_range=str(transaction.get("amount") or "").strip(),
                    initial_exclusion=exclusion,
                )
                candidates.setdefault(event_id, candidate)

    return Extraction(
        candidates=tuple(
            sorted(
                candidates.values(),
                key=lambda item: (
                    item.disclosure_date or date.min,
                    item.senator,
                    item.event_id,
                ),
            )
        ),
        filings_by_senator={name: len(ids) for name, ids in filing_ids.items()},
        transactions_by_senator={
            name: len(ids) for name, ids in transaction_ids.items()
        },
    )


def _read_json_url(url: str, attempts: int = 4) -> Mapping[str, object]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 senator-backtest/1.0"})
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code != 429:
                raise
            if attempt + 1 == attempts:
                raise
            time.sleep(2**attempt)
        except (URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 == attempts:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def download_price_series(symbol: str, start: date, end: date) -> PriceSeries:
    yahoo_symbol = _yahoo_symbol(symbol)
    start_epoch = int(datetime.combine(start, datetime.min.time(), timezone.utc).timestamp())
    end_epoch = int(
        datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp()
    )
    url = YAHOO_CHART_URL.format(
        symbol=quote(yahoo_symbol), start=start_epoch, end=end_epoch
    )
    try:
        payload = _read_json_url(url)
        chart = payload.get("chart", {})
        error = chart.get("error")
        results = chart.get("result") or []
        if error or not results:
            return PriceSeries(symbol, "", {}, f"provider_error:{error or 'no_result'}")
        result = results[0]
        metadata = result.get("meta") or {}
        timestamps = result.get("timestamp") or []
        indicators = result.get("indicators") or {}
        quotes = (indicators.get("quote") or [{}])[0]
        adjusted = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
        opens = quotes.get("open") or []
        closes = quotes.get("close") or []
        prices: Dict[date, PricePoint] = {}
        for timestamp, open_price, close_price, adjusted_close in zip(
            timestamps, opens, closes, adjusted
        ):
            if None in (open_price, close_price, adjusted_close) or float(close_price) <= 0:
                continue
            trading_day = datetime.fromtimestamp(int(timestamp), timezone.utc).date()
            factor = float(adjusted_close) / float(close_price)
            prices[trading_day] = PricePoint(
                adjusted_open=float(open_price) * factor,
                adjusted_close=float(adjusted_close),
            )
        return PriceSeries(
            symbol=symbol,
            instrument_type=str(metadata.get("instrumentType") or "").upper(),
            prices=prices,
        )
    except HTTPError as exc:
        return PriceSeries(symbol, "", {}, f"price_provider_http_{exc.code}")
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return PriceSeries(symbol, "", {}, f"download_error:{type(exc).__name__}")


def _series_to_json(series: PriceSeries) -> Mapping[str, object]:
    return {
        "symbol": series.symbol,
        "instrument_type": series.instrument_type,
        "error": series.error,
        "prices": {
            day.isoformat(): [point.adjusted_open, point.adjusted_close]
            for day, point in sorted(series.prices.items())
        },
    }


def _series_from_json(raw: Mapping[str, object]) -> PriceSeries:
    return PriceSeries(
        symbol=str(raw.get("symbol") or ""),
        instrument_type=str(raw.get("instrument_type") or ""),
        error=str(raw.get("error") or ""),
        prices={
            date.fromisoformat(day): PricePoint(float(values[0]), float(values[1]))
            for day, values in (raw.get("prices") or {}).items()
        },
    )


def load_or_download_prices(
    symbols: Iterable[str], start: date, end: date, cache_path: Path, workers: int = 4
) -> Mapping[str, PriceSeries]:
    cache: Dict[str, PriceSeries] = {}
    cached_start: Optional[date] = None
    cached_end: Optional[date] = None
    legacy_cache = False
    if cache_path.exists():
        with cache_path.open(encoding="utf-8") as handle:
            stored = json.load(handle)
        if "series" in stored:
            metadata = stored.get("metadata") or {}
            cached_start = parse_date(metadata.get("start"))
            cached_end = parse_date(metadata.get("end"))
            stored_series = stored["series"]
        else:
            legacy_cache = True
            stored_series = stored
        cache = {
            symbol: _series_from_json(raw) for symbol, raw in stored_series.items()
        }

    requested = sorted(set(symbols) | {"SPY"})
    range_changed = bool(
        cached_start
        and cached_end
        and (start < cached_start or end > cached_end)
    )
    missing = [
        symbol
        for symbol in requested
        if range_changed
        or symbol not in cache
        or cache[symbol].error.startswith("download_error:")
    ]
    if missing:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {
                executor.submit(download_price_series, symbol, start, end): symbol
                for symbol in missing
            }
            for future in as_completed(futures):
                series = future.result()
                cache[series.symbol] = series
    if missing or legacy_cache or not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "metadata": {"start": start.isoformat(), "end": end.isoformat()},
                    "series": {
                        symbol: _series_to_json(series)
                        for symbol, series in sorted(cache.items())
                    },
                },
                handle,
                separators=(",", ":"),
            )
    return {symbol: cache[symbol] for symbol in requested}


def _first_day_after(days: Sequence[date], threshold: date, inclusive: bool) -> Optional[date]:
    for day in days:
        if (inclusive and day >= threshold) or (not inclusive and day > threshold):
            return day
    return None


def run_backtest(
    extraction: Extraction,
    price_series: Mapping[str, PriceSeries],
    notional_usd: float = 1000.0,
    holding_days: int = 90,
    cost_per_side: float = 0.001,
) -> List[Mapping[str, object]]:
    spy = price_series.get("SPY")
    if spy is None or not spy.prices:
        raise ValueError("SPY price history is required as the trading calendar")
    trading_days = sorted(spy.prices)
    rows: List[Mapping[str, object]] = []

    for candidate in extraction.candidates:
        row = {field: "" for field in RESULT_FIELDS}
        row.update(
            {
                "event_id": candidate.event_id,
                "senator": candidate.senator,
                "disclosure_date": candidate.disclosure_date.isoformat()
                if candidate.disclosure_date
                else "",
                "transaction_date": candidate.transaction_date.isoformat()
                if candidate.transaction_date
                else "",
                "ticker": candidate.ticker,
                "asset_type": candidate.asset_type,
                "amount_range": candidate.amount_range,
                "notional_usd": f"{notional_usd:.2f}",
            }
        )
        if candidate.initial_exclusion:
            row.update(status="excluded", exclusion_reason=candidate.initial_exclusion)
            rows.append(row)
            continue

        series = price_series.get(candidate.ticker)
        if series is None or not series.prices:
            reason = series.error if series and series.error else "no_price_history"
            row.update(status="excluded", exclusion_reason=reason)
            rows.append(row)
            continue
        if series.instrument_type not in {"EQUITY", "ETF"}:
            row.update(
                status="excluded",
                exclusion_reason=f"provider_instrument_type_{series.instrument_type or 'unknown'}",
            )
            rows.append(row)
            continue

        entry_day = _first_day_after(
            trading_days, candidate.disclosure_date, inclusive=False
        )
        exit_day = (
            _first_day_after(
                trading_days, entry_day + timedelta(days=holding_days), inclusive=True
            )
            if entry_day
            else None
        )
        if entry_day is None or exit_day is None:
            row.update(status="excluded", exclusion_reason="incomplete_spy_holding_window")
            rows.append(row)
            continue
        entry = series.prices.get(entry_day)
        exit_price = series.prices.get(exit_day)
        if entry is None:
            row.update(status="excluded", exclusion_reason="no_security_price_on_entry_day")
            rows.append(row)
            continue
        if exit_price is None:
            row.update(status="excluded", exclusion_reason="no_security_price_on_exit_day")
            rows.append(row)
            continue

        spy_entry = spy.prices[entry_day]
        spy_exit = spy.prices[exit_day]
        strategy_multiplier = (
            (1.0 - cost_per_side)
            * (exit_price.adjusted_close / entry.adjusted_open)
            * (1.0 - cost_per_side)
        )
        spy_multiplier = (
            (1.0 - cost_per_side)
            * (spy_exit.adjusted_close / spy_entry.adjusted_open)
            * (1.0 - cost_per_side)
        )
        strategy_return = (strategy_multiplier - 1.0) * 100.0
        spy_return = (spy_multiplier - 1.0) * 100.0
        row.update(
            status="scored",
            entry_date=entry_day.isoformat(),
            exit_date=exit_day.isoformat(),
            entry_adjusted_open=f"{entry.adjusted_open:.6f}",
            exit_adjusted_close=f"{exit_price.adjusted_close:.6f}",
            spy_entry_adjusted_open=f"{spy_entry.adjusted_open:.6f}",
            spy_exit_adjusted_close=f"{spy_exit.adjusted_close:.6f}",
            strategy_final_usd=f"{notional_usd * strategy_multiplier:.2f}",
            spy_final_usd=f"{notional_usd * spy_multiplier:.2f}",
            strategy_return_pct=f"{strategy_return:.4f}",
            spy_return_pct=f"{spy_return:.4f}",
            excess_return_pct_points=f"{strategy_return - spy_return:.4f}",
        )
        rows.append(row)
    return rows


def write_results(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize_results(
    extraction: Extraction, rows: Sequence[Mapping[str, object]]
) -> Mapping[str, object]:
    by_senator = {}
    for senator in TARGET_SENATORS:
        senator_rows = [row for row in rows if row["senator"] == senator]
        scored = [row for row in senator_rows if row["status"] == "scored"]
        strategy_returns = [float(row["strategy_return_pct"]) for row in scored]
        spy_returns = [float(row["spy_return_pct"]) for row in scored]
        excess_returns = [float(row["excess_return_pct_points"]) for row in scored]
        by_senator[senator] = {
            "filings": extraction.filings_by_senator.get(senator, 0),
            "transactions": extraction.transactions_by_senator.get(senator, 0),
            "purchases": len(senator_rows),
            "scored": len(scored),
            "strategy_return_pct": sum(strategy_returns) / len(scored) if scored else None,
            "spy_return_pct": sum(spy_returns) / len(scored) if scored else None,
            "excess_return_pct_points": sum(excess_returns) / len(scored) if scored else None,
        }
    scored_all = [row for row in rows if row["status"] == "scored"]
    exclusions = Counter(
        str(row["exclusion_reason"]) for row in rows if row["status"] == "excluded"
    )
    return {
        "by_senator": by_senator,
        "candidate_purchases": len(rows),
        "scored": len(scored_all),
        "strategy_return_pct": sum(
            float(row["strategy_return_pct"]) for row in scored_all
        )
        / len(scored_all)
        if scored_all
        else None,
        "spy_return_pct": sum(float(row["spy_return_pct"]) for row in scored_all)
        / len(scored_all)
        if scored_all
        else None,
        "excess_return_pct_points": sum(
            float(row["excess_return_pct_points"]) for row in scored_all
        )
        / len(scored_all)
        if scored_all
        else None,
        "exclusions": dict(sorted(exclusions.items())),
    }
