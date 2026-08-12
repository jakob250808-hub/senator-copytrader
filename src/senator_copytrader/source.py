from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import SourceConfig
from .models import Trade


class SourceError(RuntimeError):
    pass


class TradeSource:
    def fetch(self) -> List[Trade]:
        raise NotImplementedError


class QuiverSource(TradeSource):
    def __init__(self, config: SourceConfig, api_key: str = "") -> None:
        self.config = config
        self.api_key = api_key or os.environ.get("QUIVER_API_KEY", "")

    def fetch(self) -> List[Trade]:
        if not self.api_key:
            raise SourceError("QUIVER_API_KEY ist nicht gesetzt")
        request = Request(
            self.config.endpoint,
            headers={
                "Authorization": "Bearer {}".format(self.api_key),
                "Accept": "application/json",
                "User-Agent": "senator-copytrader/0.1",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise SourceError("Quiver antwortete mit HTTP {}".format(exc.code)) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise SourceError("Quiver-Daten konnten nicht geladen werden: {}".format(exc)) from exc
        return _parse_payload(payload)


class JsonSource(TradeSource):
    """Local fixture provider for tests and zero-risk demonstrations."""

    def __init__(self, config: SourceConfig, config_dir: Path) -> None:
        path = Path(config.file).expanduser()
        self.path = path if path.is_absolute() else config_dir / path

    def fetch(self) -> List[Trade]:
        with self.path.open("r", encoding="utf-8") as handle:
            return _parse_payload(json.load(handle))


def _parse_payload(payload: Any) -> List[Trade]:
    rows: Iterable[Dict[str, Any]]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        rows = payload["data"]
    else:
        raise SourceError("Unerwartetes Datenformat der Trade-Quelle")
    return [Trade.from_quiver(row) for row in rows if isinstance(row, dict)]


def build_source(config: SourceConfig, config_path: str) -> TradeSource:
    if config.provider == "quiver":
        return QuiverSource(config)
    return JsonSource(config, Path(config_path).expanduser().resolve().parent)

