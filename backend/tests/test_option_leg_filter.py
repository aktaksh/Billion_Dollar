import unittest

from app.engines.option_leg_filter import filter_usable_legs


class OptionLegFilterTests(unittest.TestCase):
    def test_filters_far_strikes_and_bad_quotes(self):
        underlying = 735.0
        chain = [
            {
                "expiry": "2026-07-18",
                "dte": 30,
                "option_type": "call",
                "strike": 485.0,
                "bid": 8.0,
                "ask": 8.4,
            },
            {
                "expiry": "2026-07-18",
                "dte": 30,
                "option_type": "call",
                "strike": 730.0,
                "bid": 0.0,
                "ask": 8.4,
            },
            {
                "expiry": "2026-07-18",
                "dte": 30,
                "option_type": "call",
                "strike": 735.0,
                "bid": 8.0,
                "ask": 8.4,
            },
            {
                "expiry": "2026-07-18",
                "dte": 30,
                "option_type": "call",
                "strike": 740.0,
                "bid": 8.0,
                "ask": 20.0,
            },
        ]
        usable, diag = filter_usable_legs(
            chain,
            underlying_price=underlying,
            max_spread_pct=0.08,
            strikes_below=8,
            strikes_above=12,
            strike_interval=5.0,
        )
        self.assertEqual(diag.raw_contracts, 4)
        self.assertEqual(diag.rejected_for_far_strike, 1)
        self.assertEqual(diag.rejected_for_bad_bid_ask, 1)
        self.assertEqual(diag.rejected_for_spread, 1)
        self.assertEqual(diag.usable_contracts, 1)
        self.assertEqual(usable[0]["strike"], 735.0)


if __name__ == "__main__":
    unittest.main()
