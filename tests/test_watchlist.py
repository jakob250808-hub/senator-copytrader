import json
import unittest
from pathlib import Path

from senator_copytrader.config import load_config
from senator_copytrader.engine import CopyEngine
from senator_copytrader.models import Trade, normalize_person_name


PROJECT_ROOT = Path(__file__).resolve().parents[1]

QUIVER_CANONICAL_NAMES = [
    "John Boozman",
    "David McCormick",
    "Shelley Moore Capito",
    "Sheldon Whitehouse",
    "Tommy Tuberville",
    "John Fetterman",
    "John R. Curtis",
    "Rick Scott",
    "Angus S. King Jr.",
    "Gary C. Peters",
    "John W. Hickenlooper",
    "Jerry Moran",
    "Tina Smith",
    "Bernie Moreno",
    "Katie Boyd Britt",
    "Mitch McConnell",
    "Susan M. Collins",
    "Ron Wyden",
    "Ted Cruz",
    "Adam B. Schiff",
    "James Conley Justice II",
    "Bill Cassidy",
    "Jack Reed",
    "Dan Sullivan",
    "Patty Murray",
    "John Hoeven",
    "Mark R. Warner",
    "Thom Tillis",
    "Ashley B. Moody",
    "Bill Hagerty",
]


class StaticSource:
    def __init__(self, trades):
        self.trades = trades

    def fetch(self):
        return self.trades


def make_trade(representative):
    return Trade.from_quiver(
        {
            "Representative": representative,
            "ReportDate": "2026-08-13",
            "TransactionDate": "2026-08-12",
            "Ticker": "MSFT",
            "Transaction": "Purchase",
            "House": "Senate",
            "TickerType": "Stock",
        }
    )


class WatchlistTests(unittest.TestCase):
    def test_example_watchlist_has_30_quiver_names_and_user_approved_money_limits(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))

        self.assertEqual(config.source.politicians, QUIVER_CANONICAL_NAMES)
        self.assertEqual(len(config.source.politicians), 30)
        self.assertEqual(config.strategy.buy_notional_usd, 2_000.0)
        self.assertEqual(config.strategy.max_position_usd, 6_000.0)
        self.assertEqual(config.strategy.max_portfolio_usd, 60_000.0)
        self.assertEqual(config.strategy.max_daily_notional_usd, 16_000.0)
        self.assertEqual(
            config.strategy.max_position_usd % config.strategy.buy_notional_usd,
            0.0,
        )
        self.assertEqual(
            config.strategy.max_portfolio_usd % config.strategy.buy_notional_usd,
            0.0,
        )
        self.assertEqual(
            config.strategy.max_daily_notional_usd
            % config.strategy.buy_notional_usd,
            0.0,
        )

    def test_every_configured_quiver_name_passes_engine_filter(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        trades = [make_trade(name) for name in QUIVER_CANONICAL_NAMES]
        engine = CopyEngine(config, StaticSource(trades), object(), object())

        self.assertEqual(engine.selected_trades(), trades)

    def test_local_sample_gary_peters_matches_quiver_profile_name_in_config(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        with (PROJECT_ROOT / "examples" / "trades.sample.json").open(
            encoding="utf-8"
        ) as handle:
            trades = [Trade.from_quiver(raw) for raw in json.load(handle)]
        engine = CopyEngine(config, StaticSource(trades), object(), object())

        self.assertEqual(
            [trade.representative for trade in engine.selected_trades()],
            ["Gary Peters"],
        )

    def test_quiver_and_sample_name_variants_share_comparison_key(self):
        variants = {
            "Gary Peters": "Gary C. Peters",
            "Peters, Gary C.": "Gary C. Peters",
            "Tuberville, Tommy": "Tommy Tuberville",
            "McConnell, Mitch": "Mitch McConnell",
            "Mr. David H. McCormick": "David McCormick",
            "King, Angus S., Jr.": "Angus S. King Jr.",
        }

        for feed_name, configured_name in variants.items():
            with self.subTest(feed_name=feed_name):
                self.assertEqual(
                    normalize_person_name(feed_name),
                    normalize_person_name(configured_name),
                )


if __name__ == "__main__":
    unittest.main()
