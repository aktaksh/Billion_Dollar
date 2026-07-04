import unittest

from app.services.pnl_calculator import (
    is_expired,
    mark_debit_spread,
    percent_return,
    spread_entry_value,
    unrealized_pnl,
)


class PnlCalculatorTests(unittest.TestCase):
    def test_spread_entry_value(self):
        self.assertEqual(spread_entry_value(2.5, 1), 250.0)
        self.assertEqual(spread_entry_value(2.5, 2), 500.0)

    def test_mark_debit_spread(self):
        self.assertEqual(mark_debit_spread(8.1, 5.6, 1), 250.0)

    def test_unrealized_pnl(self):
        self.assertEqual(unrealized_pnl(250.0, 300.0), 50.0)
        self.assertEqual(unrealized_pnl(250.0, 200.0), -50.0)

    def test_percent_return(self):
        self.assertEqual(percent_return(50.0, 250.0), 20.0)
        self.assertEqual(percent_return(0.0, 0.0), 0.0)

    def test_is_expired(self):
        self.assertFalse(is_expired("20991231", as_of=__import__("datetime").date(2026, 7, 2)))


if __name__ == "__main__":
    unittest.main()
