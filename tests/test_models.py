import unittest

from senator_copytrader.models import (
    Trade,
    normalize_action,
    normalize_asset_type,
    normalize_person_name,
    normalize_ticker,
    parse_date,
)


class ModelTests(unittest.TestCase):
    def test_quiver_trade_is_normalized_and_stable(self):
        raw = {
            "Representative": "Gary Peters",
            "ReportDate": "2026-08-07",
            "TransactionDate": "2026-07-23",
            "Ticker": "o",
            "Transaction": "Purchase",
            "Range": "$1,001 - $15,000",
            "House": "Senate",
            "TickerType": "Stock",
        }
        first = Trade.from_quiver(raw)
        second = Trade.from_quiver(dict(reversed(list(raw.items()))))

        self.assertEqual(first.event_id, second.event_id)
        self.assertEqual(first.ticker, "O")
        self.assertEqual(first.action, "buy")
        self.assertEqual(first.report_date.isoformat(), "2026-08-07")

    def test_normalizers_handle_sale_and_dates(self):
        self.assertEqual(normalize_action("Sale (Partial)"), "sell")
        self.assertEqual(normalize_action("Exchange"), "unsupported")
        self.assertEqual(parse_date("08/07/2026").isoformat(), "2026-08-07")

    def test_identity_and_asset_normalizers_are_conservative(self):
        self.assertEqual(normalize_person_name("Thomas H. Tuberville"), "thomas h tuberville")
        self.assertEqual(normalize_ticker(" $brk/b "), "BRK.B")
        self.assertEqual(normalize_asset_type("Exchange Traded Fund"), "etf")
        self.assertEqual(normalize_asset_type("Option"), "unsupported")
        self.assertEqual(normalize_asset_type(None), "unsupported")


if __name__ == "__main__":
    unittest.main()
