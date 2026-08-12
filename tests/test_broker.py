import unittest

from senator_copytrader.broker import AlpacaPaperBroker


class RecordingBroker(AlpacaPaperBroker):
    def __init__(self, responses):
        super().__init__(api_key="paper-key", secret_key="paper-secret")
        self.responses = list(responses)
        self.requests = []

    def _request(self, method, path, payload=None):
        self.requests.append((method, path, payload))
        return self.responses.pop(0)


class BrokerTests(unittest.TestCase):
    def test_adapter_is_hard_wired_to_paper_api(self):
        self.assertEqual(
            AlpacaPaperBroker.BASE_URL, "https://paper-api.alpaca.markets"
        )

    def test_validate_and_market_clock(self):
        broker = RecordingBroker(
            [{"account_number": "PAPER123", "trading_blocked": False}, {"is_open": True}]
        )

        self.assertEqual(broker.validate(), "PAPER123")
        self.assertTrue(broker.is_market_open())
        self.assertEqual(
            broker.requests,
            [("GET", "/v2/account", None), ("GET", "/v2/clock", None)],
        )

    def test_buy_uses_notional_market_order(self):
        broker = RecordingBroker(
            [
                {
                    "class": "us_equity",
                    "status": "active",
                    "tradable": True,
                    "fractionable": True,
                },
                {"id": "paper-order-1"},
            ]
        )

        result = broker.buy_notional("MSFT", 25.0, "senate-event")

        self.assertEqual(result.status, "submitted")
        self.assertEqual(result.order_id, "paper-order-1")
        self.assertEqual(broker.requests[0], ("GET", "/v2/assets/MSFT", None))
        self.assertEqual(
            broker.requests[1],
            (
                "POST",
                "/v2/orders",
                {
                    "symbol": "MSFT",
                    "notional": "25.00",
                    "side": "buy",
                    "type": "market",
                    "time_in_force": "day",
                    "client_order_id": "senate-event",
                },
            ),
        )

    def test_close_position_never_opens_a_short(self):
        active_equity = {
            "class": "us_equity",
            "status": "active",
            "tradable": True,
        }
        no_position = RecordingBroker([active_equity, [{"symbol": "AAPL"}]])
        skipped = no_position.close_position("MSFT")
        self.assertEqual(skipped.status, "skipped")
        self.assertEqual(len(no_position.requests), 2)

        held_position = RecordingBroker(
            [active_equity, [{"symbol": "MSFT"}], {"id": "close-1"}]
        )
        submitted = held_position.close_position("MSFT")
        self.assertEqual(submitted.status, "submitted")
        self.assertEqual(
            held_position.requests[2], ("DELETE", "/v2/positions/MSFT", None)
        )

    def test_non_us_or_inactive_assets_never_reach_order_endpoint(self):
        crypto = RecordingBroker(
            [{"class": "crypto", "status": "active", "tradable": True, "fractionable": True}]
        )
        inactive = RecordingBroker(
            [{"class": "us_equity", "status": "inactive", "tradable": True, "fractionable": True}]
        )

        self.assertEqual(crypto.buy_notional("BTCUSD", 25.0, "event").status, "skipped")
        self.assertEqual(inactive.buy_notional("OLD", 25.0, "event").status, "skipped")
        self.assertEqual(len(crypto.requests), 1)
        self.assertEqual(len(inactive.requests), 1)

    def test_account_snapshot_uses_cash_not_buying_power(self):
        broker = RecordingBroker(
            [
                {
                    "cash": "1500.50",
                    "buying_power": "3001.00",
                    "portfolio_value": "2500.50",
                    "multiplier": "2",
                },
                [
                    {"symbol": "aapl", "market_value": "500.00"},
                    {"symbol": "msft", "market_value": "-200.00"},
                ],
            ]
        )

        snapshot = broker.get_account_snapshot()

        self.assertEqual(snapshot.cash, 1500.50)
        self.assertEqual(snapshot.portfolio_value, 2500.50)
        self.assertTrue(snapshot.is_margin_account)
        self.assertEqual(snapshot.position_values, {"AAPL": 500.0, "MSFT": 200.0})
        self.assertEqual(snapshot.invested_usd(), 700.0)
        self.assertEqual(snapshot.position_usd("aapl"), 500.0)


if __name__ == "__main__":
    unittest.main()
