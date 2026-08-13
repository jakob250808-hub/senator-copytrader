from datetime import date
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path

from senator_copytrader.broker import (
    AccountSnapshot,
    BrokerResult,
    OpenPosition,
    PaperBroker,
)
from senator_copytrader.config import (
    AppConfig,
    SourceConfig,
    StorageConfig,
    StrategyConfig,
)
from senator_copytrader.engine import CopyEngine, SafetyError
from senator_copytrader.models import Trade
from senator_copytrader.source import TradeSource
from senator_copytrader.storage import StateStore


class FakeSource(TradeSource):
    def __init__(self, trades):
        self.trades = trades

    def fetch(self):
        return self.trades


class FakeBroker(PaperBroker):
    def __init__(
        self,
        cash=100_000.0,
        position_values=None,
        open_positions=None,
        pending_closes=None,
    ):
        self.buys = []
        self.closes = []
        self.cash = cash
        self.position_values = dict(position_values or {})
        self.open_positions = dict(open_positions or {})
        self.pending_closes = set(pending_closes or set())
        self.get_open_positions_calls = 0

    def validate(self):
        return "PAPER123"

    def is_market_open(self):
        return True

    def get_account_snapshot(self):
        return AccountSnapshot(
            cash=self.cash,
            portfolio_value=self.cash + sum(self.position_values.values()),
            is_margin_account=False,
            position_values=dict(self.position_values),
        )

    def get_open_positions(self):
        self.get_open_positions_calls += 1
        return dict(self.open_positions)

    def has_pending_close_order(self, symbol):
        return symbol in self.pending_closes

    def buy_notional(self, symbol, notional_usd, client_order_id):
        self.buys.append((symbol, notional_usd, client_order_id))
        # Wie beim echten Alpaca-Paperkonto wirkt sich ein ausgefuehrter Kauf
        # auf den naechsten Kontostand-Snapshot aus (Cash sinkt, Position waechst).
        self.cash -= notional_usd
        self.position_values[symbol] = self.position_values.get(symbol, 0.0) + notional_usd
        return BrokerResult("submitted", "ok", "buy-order")

    def close_position(self, symbol):
        self.closes.append(symbol)
        if symbol not in self.position_values:
            return BrokerResult("skipped", "no position")
        self.position_values.pop(symbol, None)
        self.open_positions.pop(symbol, None)
        return BrokerResult("submitted", "closed", "close-order")


def make_trade(ticker="O", action="Purchase", report_date="2026-08-11"):
    return Trade.from_quiver(
        {
            "Representative": "Gary Peters",
            "ReportDate": report_date,
            "TransactionDate": "2026-08-10",
            "Ticker": ticker,
            "Transaction": action,
            "House": "Senate",
            "TickerType": "Stock",
        }
    )


def make_config(db_path, **overrides):
    strategy_kwargs = dict(
        buy_notional_usd=25.0,
        sell_policy="close_position",
        allowed_ticker_types=["Stock", "ETF"],
        require_market_open=True,
        max_position_usd=1_000.0,
        max_portfolio_usd=5_000.0,
        max_daily_notional_usd=1_000.0,
        stop_loss_pct=None,
        take_profit_pct=None,
        max_holding_days=None,
    )
    strategy_kwargs.update(overrides)
    return AppConfig(
        source=SourceConfig(
            provider="json",
            endpoint="",
            chamber="Senate",
            politicians=["Gary Peters"],
            max_report_age_days=7,
            file="unused.json",
        ),
        strategy=StrategyConfig(**strategy_kwargs),
        storage=StorageConfig(database=str(db_path)),
    )


def seed_bot_position(store, ticker, opened_on):
    trade = make_trade(ticker=ticker, report_date=opened_on.isoformat())
    store.record(
        trade,
        "submitted",
        broker_order_id="seed-buy",
        details="seed",
        notional_usd=1_000.0,
        processed_on=opened_on,
    )


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_execute_requires_bootstrap(self):
        store = StateStore(str(self.tmp_path / "state.db"))
        engine = CopyEngine(
            make_config(self.tmp_path / "state.db"), FakeSource([]), store, FakeBroker()
        )
        with self.assertRaises(SafetyError):
            engine.execute(today=date(2026, 8, 12))
        store.close()

    def test_bootstrap_blocks_backlog_and_new_trade_executes_once(self):
        old_trade = make_trade(ticker="O", report_date="2026-08-07")
        source = FakeSource([old_trade])
        store = StateStore(str(self.tmp_path / "state.db"))
        broker = FakeBroker()
        engine = CopyEngine(make_config(self.tmp_path / "state.db"), source, store, broker)

        self.assertEqual(engine.bootstrap(), 1)
        self.assertEqual(engine.plan(today=date(2026, 8, 12)), [])

        new_trade = make_trade(ticker="MSFT", report_date="2026-08-12")
        source.trades.append(new_trade)
        planned = engine.plan(today=date(2026, 8, 12))
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0].notional_usd, 25.0)

        results = engine.execute(today=date(2026, 8, 12))
        self.assertEqual(results[0].status, "submitted")
        self.assertEqual(broker.buys[0][0:2], ("MSFT", 25.0))
        self.assertEqual(engine.execute(today=date(2026, 8, 12)), [])
        store.close()

    def test_sale_never_shorts(self):
        source = FakeSource([])
        store = StateStore(str(self.tmp_path / "state.db"))
        broker = FakeBroker()
        engine = CopyEngine(make_config(self.tmp_path / "state.db"), source, store, broker)
        engine.bootstrap()
        source.trades.append(make_trade(ticker="AAPL", action="Sale (Full)"))

        result = engine.execute(today=date(2026, 8, 12))[0]
        self.assertEqual(result.status, "skipped")
        self.assertEqual(broker.closes, ["AAPL"])
        self.assertEqual(broker.buys, [])
        store.close()

    def test_no_fixed_cap_all_valid_signals_execute_within_money_limits(self):
        # Es gibt bewusst keine feste Grenze wie "hoechstens drei Orders":
        # Mehr als drei gueltige Tagesmeldungen muessen verarbeitet werden,
        # solange die Geld-/Positions-/Portfoliolimits das zulassen.
        tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
        source = FakeSource([])
        store = StateStore(str(self.tmp_path / "state.db"))
        broker = FakeBroker(cash=100_000.0)
        config = make_config(
            self.tmp_path / "state.db",
            max_position_usd=1_000.0,
            max_portfolio_usd=1_000_000.0,
            max_daily_notional_usd=1_000_000.0,
        )
        engine = CopyEngine(config, source, store, broker)
        engine.bootstrap()
        for ticker in tickers:
            source.trades.append(make_trade(ticker=ticker, report_date="2026-08-12"))

        results = engine.execute(today=date(2026, 8, 12))
        self.assertEqual(len(results), len(tickers))
        self.assertTrue(all(result.status == "submitted" for result in results))
        self.assertEqual(len(broker.buys), len(tickers))
        store.close()

    def test_more_than_former_technical_cap_is_not_truncated(self):
        source = FakeSource([])
        store = StateStore(str(self.tmp_path / "state.db"))
        config = make_config(
            self.tmp_path / "state.db",
            buy_notional_usd=1.0,
            max_position_usd=10.0,
            max_portfolio_usd=1_000_000.0,
            max_daily_notional_usd=1_000_000.0,
        )
        engine = CopyEngine(config, source, store, FakeBroker(cash=100_000.0))
        engine.bootstrap()
        source.trades.extend(
            make_trade(ticker="T{:03d}".format(index), report_date="2026-08-12")
            for index in range(75)
        )

        self.assertEqual(len(engine.plan(today=date(2026, 8, 12))), 75)
        store.close()

    def test_watchlist_name_matching_ignores_punctuation(self):
        trade = Trade.from_quiver(
            {
                "Representative": "Gary W. Peters",
                "ReportDate": "2026-08-12",
                "TransactionDate": "2026-08-10",
                "Ticker": "MSFT",
                "Transaction": "Purchase",
                "House": "Senate",
                "TickerType": "Stock",
            }
        )
        config = make_config(self.tmp_path / "state.db")
        config = replace(
            config,
            source=replace(config.source, politicians=["Gary W Peters"]),
        )
        store = StateStore(str(self.tmp_path / "state.db"))
        engine = CopyEngine(config, FakeSource([trade]), store, FakeBroker())

        self.assertEqual(engine.selected_trades(), [trade])
        store.close()

    def test_missing_asset_type_is_never_assumed_to_be_stock(self):
        trade = Trade.from_quiver(
            {
                "Representative": "Gary Peters",
                "ReportDate": "2026-08-12",
                "TransactionDate": "2026-08-10",
                "Ticker": "MSFT",
                "Transaction": "Purchase",
                "House": "Senate",
            }
        )
        store = StateStore(str(self.tmp_path / "state.db"))
        engine = CopyEngine(
            make_config(self.tmp_path / "state.db"), FakeSource([trade]), store, FakeBroker()
        )

        self.assertEqual(trade.ticker_type, "unsupported")
        self.assertEqual(engine.plan(today=date(2026, 8, 12)), [])
        store.close()

    def test_position_limit_skips_further_buys_of_same_ticker(self):
        source = FakeSource([])
        store = StateStore(str(self.tmp_path / "state.db"))
        broker = FakeBroker(cash=100_000.0)
        config = make_config(
            self.tmp_path / "state.db",
            buy_notional_usd=600.0,
            max_position_usd=1_000.0,
            max_portfolio_usd=1_000_000.0,
            max_daily_notional_usd=1_000_000.0,
        )
        engine = CopyEngine(config, source, store, broker)
        engine.bootstrap()
        source.trades.append(make_trade(ticker="AAA", report_date="2026-08-12"))
        results_first = engine.execute(today=date(2026, 8, 12))
        self.assertEqual(results_first[0].status, "submitted")

        source.trades.append(make_trade(ticker="AAA", report_date="2026-08-13"))
        results_second = engine.execute(today=date(2026, 8, 13))
        self.assertEqual(results_second[0].status, "skipped")
        self.assertIn("Positionslimit", results_second[0].message)
        self.assertEqual(len(broker.buys), 1)
        store.close()

    def test_portfolio_limit_skips_buys_once_reached(self):
        source = FakeSource([])
        store = StateStore(str(self.tmp_path / "state.db"))
        broker = FakeBroker(cash=100_000.0)
        config = make_config(
            self.tmp_path / "state.db",
            buy_notional_usd=600.0,
            max_position_usd=1_000_000.0,
            max_portfolio_usd=1_000.0,
            max_daily_notional_usd=1_000_000.0,
        )
        engine = CopyEngine(config, source, store, broker)
        engine.bootstrap()
        source.trades.append(make_trade(ticker="AAA", report_date="2026-08-12"))
        source.trades.append(make_trade(ticker="BBB", report_date="2026-08-12"))

        results = engine.execute(today=date(2026, 8, 12))
        self.assertEqual(results[0].status, "submitted")
        self.assertEqual(results[1].status, "skipped")
        self.assertIn("Portfoliolimit", results[1].message)
        store.close()

    def test_daily_limit_persists_across_runs_on_same_day(self):
        source = FakeSource([])
        store = StateStore(str(self.tmp_path / "state.db"))
        broker = FakeBroker(cash=100_000.0)
        config = make_config(
            self.tmp_path / "state.db",
            buy_notional_usd=600.0,
            max_position_usd=1_000_000.0,
            max_portfolio_usd=1_000_000.0,
            max_daily_notional_usd=1_000.0,
        )
        engine = CopyEngine(config, source, store, broker)
        engine.bootstrap()
        source.trades.append(make_trade(ticker="AAA", report_date="2026-08-12"))
        first = engine.execute(today=date(2026, 8, 12))
        self.assertEqual(first[0].status, "submitted")

        source.trades.append(make_trade(ticker="BBB", report_date="2026-08-12"))
        second = engine.execute(today=date(2026, 8, 12))
        new_result = [r for r in second if r.ticker == "BBB"][0]
        self.assertEqual(new_result.status, "skipped")
        self.assertIn("Tageslimit", new_result.message)
        store.close()

    def test_never_buys_beyond_available_paper_cash_no_margin(self):
        source = FakeSource([])
        store = StateStore(str(self.tmp_path / "state.db"))
        broker = FakeBroker(cash=100.0)
        config = make_config(
            self.tmp_path / "state.db",
            buy_notional_usd=500.0,
            max_position_usd=1_000_000.0,
            max_portfolio_usd=1_000_000.0,
            max_daily_notional_usd=1_000_000.0,
        )
        engine = CopyEngine(config, source, store, broker)
        engine.bootstrap()
        source.trades.append(make_trade(ticker="AAA", report_date="2026-08-12"))

        results = engine.execute(today=date(2026, 8, 12))
        self.assertEqual(results[0].status, "skipped")
        self.assertIn("Margin", results[0].message)
        self.assertEqual(broker.buys, [])
        store.close()

    def test_changed_politician_selection_requires_new_bootstrap(self):
        store = StateStore(str(self.tmp_path / "state.db"))
        original_config = make_config(self.tmp_path / "state.db")
        original = CopyEngine(original_config, FakeSource([]), store, FakeBroker())
        original.bootstrap()

        changed_source = replace(
            original_config.source, politicians=["Mark Warner"]
        )
        changed_config = replace(original_config, source=changed_source)
        changed = CopyEngine(changed_config, FakeSource([]), store, FakeBroker())

        with self.assertRaises(SafetyError):
            changed.execute(today=date(2026, 8, 12))
        store.close()

    def test_stop_loss_closes_bot_owned_position(self):
        store = StateStore(str(self.tmp_path / "state.db"))
        seed_bot_position(store, "AAPL", date(2026, 8, 1))
        broker = FakeBroker(
            position_values={"AAPL": 900.0},
            open_positions={
                "AAPL": OpenPosition("AAPL", 900.0, 100.0, 91.0, -9.0)
            },
        )
        engine = CopyEngine(
            make_config(self.tmp_path / "state.db", stop_loss_pct=8.0),
            FakeSource([]),
            store,
            broker,
        )
        engine.bootstrap()

        result = engine.execute(today=date(2026, 8, 12))[0]

        self.assertEqual(result.status, "submitted")
        self.assertIn("Stop-Loss ausgelöst", result.message)
        self.assertEqual(broker.closes, ["AAPL"])
        event = store.connection.execute(
            "SELECT action, exit_reason, details FROM events WHERE event_id = ?",
            (result.event_id,),
        ).fetchone()
        self.assertEqual(event["action"], "risk_exit")
        self.assertEqual(event["exit_reason"], "stop_loss")
        self.assertIn("-9.0000 %", event["details"])
        store.close()

    def test_take_profit_closes_bot_owned_position(self):
        store = StateStore(str(self.tmp_path / "state.db"))
        seed_bot_position(store, "MSFT", date(2026, 7, 1))
        broker = FakeBroker(
            position_values={"MSFT": 1_250.0},
            open_positions={
                "MSFT": OpenPosition("MSFT", 1_250.0, 100.0, 125.0, 25.0)
            },
        )
        engine = CopyEngine(
            make_config(self.tmp_path / "state.db", take_profit_pct=20.0),
            FakeSource([]),
            store,
            broker,
        )
        engine.bootstrap()

        result = engine.execute(today=date(2026, 8, 12))[0]

        self.assertEqual(result.status, "submitted")
        self.assertIn("Take-Profit ausgelöst", result.message)
        self.assertEqual(broker.closes, ["MSFT"])
        store.close()

    def test_max_holding_days_uses_local_history(self):
        store = StateStore(str(self.tmp_path / "state.db"))
        seed_bot_position(store, "NVDA", date(2026, 6, 1))
        broker = FakeBroker(
            position_values={"NVDA": 1_000.0},
            open_positions={
                "NVDA": OpenPosition("NVDA", 1_000.0, None, None, None)
            },
        )
        engine = CopyEngine(
            make_config(self.tmp_path / "state.db", max_holding_days=60),
            FakeSource([]),
            store,
            broker,
        )
        engine.bootstrap()

        result = engine.execute(today=date(2026, 8, 12))[0]

        self.assertEqual(result.status, "submitted")
        self.assertIn("Maximale Haltefrist erreicht", result.message)
        self.assertIn("72 Kalendertage", result.message)
        store.close()

    def test_disabled_exit_fields_preserve_existing_behavior(self):
        store = StateStore(str(self.tmp_path / "state.db"))
        seed_bot_position(store, "AAPL", date(2025, 1, 1))
        broker = FakeBroker(
            position_values={"AAPL": 100.0},
            open_positions={
                "AAPL": OpenPosition("AAPL", 100.0, 100.0, 10.0, -90.0)
            },
        )
        engine = CopyEngine(
            make_config(self.tmp_path / "state.db"), FakeSource([]), store, broker
        )
        engine.bootstrap()

        self.assertEqual(engine.execute(today=date(2026, 8, 12)), [])
        self.assertEqual(broker.get_open_positions_calls, 0)
        self.assertEqual(broker.closes, [])
        store.close()

    def test_exit_rules_ignore_positions_without_local_bot_buy(self):
        store = StateStore(str(self.tmp_path / "state.db"))
        broker = FakeBroker(
            position_values={"MANUAL": 100.0},
            open_positions={
                "MANUAL": OpenPosition("MANUAL", 100.0, 100.0, 10.0, -90.0)
            },
        )
        engine = CopyEngine(
            make_config(self.tmp_path / "state.db", stop_loss_pct=8.0),
            FakeSource([]),
            store,
            broker,
        )
        engine.bootstrap()

        self.assertEqual(engine.execute(today=date(2026, 8, 12)), [])
        self.assertEqual(broker.closes, [])
        store.close()

    def test_exit_blocks_immediate_reentry_from_same_run(self):
        source = FakeSource([])
        store = StateStore(str(self.tmp_path / "state.db"))
        seed_bot_position(store, "AAPL", date(2026, 8, 1))
        broker = FakeBroker(
            position_values={"AAPL": 900.0},
            open_positions={
                "AAPL": OpenPosition("AAPL", 900.0, 100.0, 90.0, -10.0)
            },
        )
        engine = CopyEngine(
            make_config(self.tmp_path / "state.db", stop_loss_pct=8.0),
            source,
            store,
            broker,
        )
        engine.bootstrap()
        source.trades.append(make_trade(ticker="AAPL", report_date="2026-08-12"))

        results = engine.execute(today=date(2026, 8, 12))

        self.assertEqual([item.action for item in results], ["close_position", "buy"])
        self.assertEqual(results[1].status, "skipped")
        self.assertIn("kein sofortiger Wiedereinstieg", results[1].message)
        self.assertEqual(broker.buys, [])
        store.close()

    def test_strategy_exit_preview_never_sends_or_records_order(self):
        store = StateStore(str(self.tmp_path / "state.db"))
        seed_bot_position(store, "AAPL", date(2026, 8, 1))
        broker = FakeBroker(
            position_values={"AAPL": 900.0},
            open_positions={
                "AAPL": OpenPosition("AAPL", 900.0, 100.0, 90.0, -10.0)
            },
        )
        engine = CopyEngine(
            make_config(self.tmp_path / "state.db", stop_loss_pct=8.0),
            FakeSource([]),
            store,
            broker,
        )

        preview = engine.preview_strategy_exits(today=date(2026, 8, 12))

        self.assertEqual(preview[0].status, "planned")
        self.assertIn("Vorschau", preview[0].message)
        self.assertEqual(broker.closes, [])
        self.assertIsNone(
            store.connection.execute(
                "SELECT 1 FROM events WHERE action = 'risk_exit'"
            ).fetchone()
        )
        store.close()


if __name__ == "__main__":
    unittest.main()
