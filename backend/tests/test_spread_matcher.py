import unittest

from app.services.ibkr.spread_matcher import SpreadMatcher
from app.utils.expiry_format import normalize_expiry_iso


class ExpiryFormatTests(unittest.TestCase):
    def test_compact_to_iso(self):
        self.assertEqual(normalize_expiry_iso("20260718"), "2026-07-18")

    def test_iso_unchanged(self):
        self.assertEqual(normalize_expiry_iso("2026-08-14"), "2026-08-14")


class SpreadMatcherTests(unittest.TestCase):
    def test_bull_call_spread(self):
        positions = [
            {
                "assetClass": "OPT",
                "symbol": "QQQ",
                "expiry": "20260814",
                "strike": 715,
                "putOrCall": "C",
                "position": 1,
                "conid": 1,
                "avgCost": 800,
                "mktPrice": 8.0,
                "mktValue": 800,
                "unrealizedPnl": 50,
            },
            {
                "assetClass": "OPT",
                "symbol": "QQQ",
                "expiry": "20260814",
                "strike": 725,
                "putOrCall": "C",
                "position": -1,
                "conid": 2,
                "avgCost": 400,
                "mktPrice": 4.0,
                "mktValue": -400,
                "unrealizedPnl": -20,
            },
        ]
        spreads = SpreadMatcher().match(positions)
        self.assertEqual(len(spreads), 1)
        self.assertEqual(spreads[0].strategy_type, "Bull Call Spread")
        self.assertEqual(spreads[0].expiry, "2026-08-14")
        self.assertEqual(spreads[0].long_strike, 715)
        self.assertEqual(spreads[0].short_strike, 725)

    def test_bear_put_spread(self):
        positions = [
            {
                "assetClass": "OPT",
                "symbol": "SPY",
                "expiry": "2026-09-19",
                "strike": 520,
                "putOrCall": "P",
                "position": 1,
                "conid": 3,
            },
            {
                "assetClass": "OPT",
                "symbol": "SPY",
                "expiry": "2026-09-19",
                "strike": 510,
                "putOrCall": "P",
                "position": -1,
                "conid": 4,
            },
        ]
        spreads = SpreadMatcher().match(positions)
        self.assertEqual(len(spreads), 1)
        self.assertEqual(spreads[0].strategy_type, "Bear Put Spread")

    def test_tws_position_shape(self):
        positions = [
            {
                "symbol": "QQQ",
                "sec_type": "OPT",
                "expiry": "2026-08-14",
                "strike": 715,
                "right": "C",
                "position": 1,
                "avgCost": 800,
                "conId": 101,
            },
            {
                "symbol": "QQQ",
                "secType": "OPT",
                "expiry": "20260814",
                "strike": 725,
                "right": "C",
                "position": -1,
                "avgCost": 400,
                "conId": 102,
            },
        ]
        spreads = SpreadMatcher().match(positions)
        self.assertEqual(len(spreads), 1)
        self.assertEqual(spreads[0].expiry, "2026-08-14")
        self.assertEqual(spreads[0].strategy_type, "Bull Call Spread")


if __name__ == "__main__":
    unittest.main()
