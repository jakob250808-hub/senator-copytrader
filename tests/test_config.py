import json
import tempfile
import unittest
from pathlib import Path

from senator_copytrader.config import load_config


class ConfigTests(unittest.TestCase):
    def test_quiver_key_cannot_be_redirected_to_another_host(self):
        payload = {
            "source": {
                "provider": "quiver",
                "endpoint": "https://example.com/collect-key",
                "politicians": ["Gary Peters"],
            },
            "strategy": {},
            "storage": {"database": "state.db"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "api.quiverquant.com"):
                load_config(str(path))

    def test_legacy_order_cap_is_ignored_and_not_part_of_strategy(self):
        payload = {
            "source": {"provider": "json", "file": "trades.json", "politicians": ["Gary Peters"]},
            "strategy": {"max_orders_per_run": 200, "buy_notional_usd": 50},
            "storage": {"database": "state.db"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            config = load_config(str(path))
            self.assertFalse(hasattr(config.strategy, "max_orders_per_run"))

    def test_unknown_allowed_asset_type_is_rejected(self):
        payload = {
            "source": {"provider": "json", "file": "trades.json", "politicians": ["Gary Peters"]},
            "strategy": {"allowed_ticker_types": ["Stock", "Option"]},
            "storage": {"database": "state.db"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Aktien und ETFs"):
                load_config(str(path))

    def test_buy_notional_cannot_exceed_position_limit(self):
        payload = {
            "source": {"provider": "json", "file": "trades.json", "politicians": ["Gary Peters"]},
            "strategy": {"buy_notional_usd": 5_000, "max_position_usd": 1_000},
            "storage": {"database": "state.db"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "max_position_usd"):
                load_config(str(path))

    def test_position_limit_cannot_exceed_portfolio_limit(self):
        payload = {
            "source": {"provider": "json", "file": "trades.json", "politicians": ["Gary Peters"]},
            "strategy": {"max_position_usd": 50_000, "max_portfolio_usd": 10_000},
            "storage": {"database": "state.db"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "max_portfolio_usd"):
                load_config(str(path))

    def test_defaults_are_internally_consistent(self):
        payload = {
            "source": {"provider": "json", "file": "trades.json", "politicians": ["Gary Peters"]},
            "strategy": {},
            "storage": {"database": "state.db"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            config = load_config(str(path))
            self.assertEqual(config.strategy.buy_notional_usd, 1_000.0)
            self.assertGreaterEqual(config.strategy.max_position_usd, config.strategy.buy_notional_usd)
            self.assertGreaterEqual(config.strategy.max_portfolio_usd, config.strategy.max_position_usd)


if __name__ == "__main__":
    unittest.main()
