from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from typing import Sequence

from .broker import AlpacaPaperBroker
from .config import load_config
from .engine import CopyEngine, SafetyError
from .source import SourceError, build_source
from .storage import StateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="senator-copytrader",
        description="US-Senatorenmeldungen ausschließlich im Alpaca-Paperkonto simulieren",
    )
    parser.add_argument("--config", default="config.json", help="Pfad zur JSON-Konfiguration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="Datenquelle und Paperkonto prüfen")
    subparsers.add_parser("bootstrap", help="Aktuelle Meldungen als Startbestand markieren")
    run_parser = subparsers.add_parser("run", help="Neue Meldungen planen oder ausführen")
    run_parser.add_argument(
        "--execute-paper",
        action="store_true",
        help="Orders wirklich an das Alpaca-Paperkonto senden",
    )
    subparsers.add_parser("status", help="Lokalen Verarbeitungsstand anzeigen")
    return parser


def main(argv: Sequence[str] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        store = StateStore(config.storage.database)
        try:
            if args.command == "status":
                _print_json(store.summary())
                return 0

            source = build_source(config.source, args.config)
            broker = AlpacaPaperBroker()
            engine = CopyEngine(config, source, store, broker)

            if args.command == "check":
                trades = engine.selected_trades()
                account = broker.validate()
                _print_json(
                    {
                        "source": "ok",
                        "matching_trades": len(trades),
                        "alpaca_paper_account": account,
                        "live_trading": False,
                    }
                )
                return 0

            if args.command == "bootstrap":
                count = engine.bootstrap()
                _print_json(
                    {
                        "status": "bootstrapped",
                        "baseline_events": count,
                        "message": "Bestehende Meldungen werden nicht gehandelt.",
                    }
                )
                return 0

            if not args.execute_paper:
                plans = [asdict(item) for item in engine.plan()]
                for item in plans:
                    item["trade"]["transaction_date"] = _date_text(
                        item["trade"]["transaction_date"]
                    )
                    item["trade"]["report_date"] = _date_text(item["trade"]["report_date"])
                _print_json(
                    {
                        "mode": "dry-run",
                        "planned_actions": plans,
                        "message": "Keine Order wurde gesendet.",
                    }
                )
                return 0

            if os.environ.get("PAPER_TRADING_CONFIRM") != "YES":
                raise SafetyError(
                    "Für Paper-Orders zusätzlich PAPER_TRADING_CONFIRM=YES setzen"
                )
            results = [asdict(item) for item in engine.execute()]
            _print_json({"mode": "alpaca-paper", "results": results, "live_trading": False})
            return 0
        finally:
            store.close()
    except (ValueError, OSError, SourceError, SafetyError, RuntimeError) as exc:
        print("Fehler: {}".format(exc), file=sys.stderr)
        return 2


def _date_text(value):
    return value.isoformat() if value else None


def _print_json(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
