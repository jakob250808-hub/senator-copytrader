from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

from .models import Trade


class StateStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                representative TEXT NOT NULL,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                report_date TEXT,
                status TEXT NOT NULL,
                broker_order_id TEXT,
                details TEXT NOT NULL,
                processed_at TEXT NOT NULL
            );
            """
        )
        existing_columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(events)")
        }
        if "notional_usd" not in existing_columns:
            self.connection.execute("ALTER TABLE events ADD COLUMN notional_usd REAL")
        self.connection.commit()

    def is_bootstrapped(self, selection_key: Optional[str] = None) -> bool:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = 'bootstrapped'"
        ).fetchone()
        if not bool(row and row["value"] == "yes"):
            return False
        if selection_key is None:
            return True
        selection_row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = 'selection_key'"
        ).fetchone()
        return bool(selection_row and selection_row["value"] == selection_key)

    def bootstrap(self, trades: Iterable[Trade], selection_key: str) -> int:
        count = 0
        for trade in trades:
            if self.record(trade, "baseline", details="Vorhandene Meldung beim Erststart"):
                count += 1
        self.connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES('bootstrapped', 'yes')"
        )
        self.connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES('selection_key', ?)",
            (selection_key,),
        )
        self.connection.commit()
        return count

    def contains(self, event_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None

    def record(
        self,
        trade: Trade,
        status: str,
        broker_order_id: Optional[str] = None,
        details: str = "",
        notional_usd: Optional[float] = None,
    ) -> bool:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO events(
                event_id, representative, ticker, action, report_date,
                status, broker_order_id, details, processed_at, notional_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.event_id,
                trade.representative,
                trade.ticker,
                trade.action,
                trade.report_date.isoformat() if trade.report_date else None,
                status,
                broker_order_id,
                details,
                datetime.now(timezone.utc).isoformat(),
                notional_usd,
            ),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def daily_buy_notional(self, day: date) -> float:
        """Summe der an diesem Kalendertag (UTC) bereits übermittelten Käufe.

        Dient als lokale Tagesbudget-Bremse, unabhängig davon, was Alpaca an
        Kaufkraft meldet. Nur tatsächlich übermittelte ('submitted') Käufe
        zählen; abgelehnte oder übersprungene Versuche nicht.
        """
        row = self.connection.execute(
            """
            SELECT COALESCE(SUM(notional_usd), 0) AS total
            FROM events
            WHERE action = 'buy'
              AND status = 'submitted'
              AND substr(processed_at, 1, 10) = ?
            """,
            (day.isoformat(),),
        ).fetchone()
        return float(row["total"]) if row else 0.0

    def summary(self) -> Dict[str, int]:
        rows = self.connection.execute(
            "SELECT status, COUNT(*) AS count FROM events GROUP BY status"
        ).fetchall()
        result = {str(row["status"]): int(row["count"]) for row in rows}
        result["bootstrapped"] = int(self.is_bootstrapped())
        return result
