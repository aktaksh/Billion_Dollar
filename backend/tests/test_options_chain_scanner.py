import os
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

os.environ.setdefault("BROKER_BACKEND", "mock")

from app.config import settings
from app.services.broker.factory import get_broker_client
from app.services.market_hours import empty_quotes_reason, is_us_equity_regular_session
from app.services.options_chain_store import get_contracts, get_scan_status

settings.broker_backend = "mock"
get_broker_client.cache_clear()

from app.main import engine, options_chain_scanner  # noqa: E402
from app.services.options_chain_scanner import _classify_row  # noqa: E402


class MarketHoursTests(unittest.TestCase):
    def test_weekend_is_off_session(self):
        saturday = datetime(2026, 6, 6, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertFalse(is_us_equity_regular_session(saturday))

    def test_regular_session_window(self):
        midday = datetime(2026, 6, 4, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertTrue(is_us_equity_regular_session(midday))
        premarket = datetime(2026, 6, 4, 8, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertFalse(is_us_equity_regular_session(premarket))

    def test_empty_quotes_reason_mentions_off_hours(self):
        with patch("app.services.market_hours.is_us_equity_regular_session", return_value=False):
            self.assertIn("off-hours", empty_quotes_reason())


class ClassifyRowTests(unittest.TestCase):
    def test_bid_ask_without_oi_volume_is_usable(self):
        row = _classify_row(
            {
                "bid": 5.0,
                "ask": 5.2,
                "mid": 5.1,
                "volume": 0,
                "open_interest": 0,
            },
            settings.options_chain,
        )
        self.assertEqual(row["status"], "usable")

    def test_last_only_mid_is_usable(self):
        row = _classify_row(
            {"bid": 0.0, "ask": 0.0, "mid": 5.0, "volume": 0, "open_interest": 0},
            settings.options_chain,
        )
        self.assertEqual(row["status"], "usable")

    def test_all_zero_is_reject(self):
        row = _classify_row(
            {"bid": 0.0, "ask": 0.0, "mid": 0.0, "volume": 0, "open_interest": 0},
            settings.options_chain,
        )
        self.assertEqual(row["status"], "reject")


class OptionsChainScannerOffHoursTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        get_broker_client().connect()
        settings.options_chain.batch_delay_seconds = 0
        options_chain_scanner.run_quote_scan("QQQ")
        cls.baseline_count = len(get_contracts(engine, "QQQ"))

    def test_empty_broker_quotes_preserve_cached_chain(self):
        self.assertGreater(self.baseline_count, 0)

        with patch.object(options_chain_scanner._broker, "fetch_expiry_quotes", return_value=[]):
            preserved = options_chain_scanner.run_quote_scan("QQQ")

        self.assertTrue(preserved)
        status = get_scan_status(engine, "QQQ") or {}
        self.assertEqual(status.get("scanner_status"), "stale")
        self.assertIn("quotes", str(status.get("last_error", "")).lower())
        self.assertEqual(len(get_contracts(engine, "QQQ")), self.baseline_count)

    def test_zero_quote_rows_preserve_usable_cache(self):
        prior_count = len(get_contracts(engine, "QQQ"))
        self.assertGreater(prior_count, 0)
        zero_rows = [
            {
                "symbol": "QQQ",
                "expiry": "2026-07-01",
                "dte": 21,
                "option_type": "call",
                "strike": 480.0,
                "bid": 0.0,
                "ask": 0.0,
                "last": None,
                "mid": 0.0,
                "volume": 0,
                "open_interest": 0,
                "delta": 0.0,
                "gamma": 0.0,
                "theta": 0.0,
                "vega": 0.0,
                "iv": 0.0,
            }
        ]

        with patch.object(options_chain_scanner._broker, "fetch_expiry_quotes", return_value=zero_rows):
            preserved = options_chain_scanner.run_quote_scan("QQQ")

        self.assertTrue(preserved)
        status = get_scan_status(engine, "QQQ") or {}
        self.assertEqual(status.get("scanner_status"), "stale")
        self.assertGreater(int(status.get("contracts_usable") or 0), 0)
        self.assertEqual(len(get_contracts(engine, "QQQ")), prior_count)

    def test_priced_rows_with_zero_oi_persist_not_preserve(self):
        settings.options_chain.max_expiries = 1
        settings.options_chain.batch_delay_seconds = 0
        priced_rows = [
            {
                "symbol": "QQQ",
                "expiry": "2026-07-01",
                "dte": 21,
                "option_type": "call",
                "strike": 480.0,
                "bid": 12.0,
                "ask": 12.4,
                "last": 12.2,
                "mid": 12.2,
                "volume": 0,
                "open_interest": 0,
                "delta": 0.5,
                "gamma": 0.02,
                "theta": -0.1,
                "vega": 0.2,
                "iv": 0.25,
            }
        ]

        with patch.object(options_chain_scanner._broker, "fetch_expiry_quotes", return_value=priced_rows):
            ok = options_chain_scanner.run_quote_scan("QQQ")

        settings.options_chain.max_expiries = 4
        self.assertTrue(ok)
        status = get_scan_status(engine, "QQQ") or {}
        self.assertIn(status.get("scanner_status"), {"fresh", "partial"})
        contracts = get_contracts(engine, "QQQ")
        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0].get("status"), "usable")

    def test_disconnected_scan_sets_stale_not_scanning(self):
        settings.options_chain.batch_delay_seconds = 0
        options_chain_scanner.run_quote_scan("QQQ")
        status_before = get_scan_status(engine, "QQQ") or {}
        self.assertGreater(len(get_contracts(engine, "QQQ")), 0)

        with patch.object(options_chain_scanner, "_broker_connected", return_value=False):
            options_chain_scanner.run_quote_scan("QQQ")

        status_after = get_scan_status(engine, "QQQ") or {}
        self.assertEqual(status_after.get("scanner_status"), "stale")
        self.assertNotEqual(status_after.get("scanner_status"), "scanning")
        self.assertIn("disconnected", str(status_after.get("last_error", "")).lower())

    def test_disconnected_metadata_preserves_broker_fresh_status(self):
        from app.services.options_chain_store import update_scan_status

        update_scan_status(
            engine,
            "QQQ",
            scanner_status="fresh",
            chain_source="broker",
            contracts_usable=18,
        )
        with patch.object(options_chain_scanner, "_broker_connected", return_value=False):
            options_chain_scanner.refresh_metadata("QQQ")

        status = get_scan_status(engine, "QQQ") or {}
        self.assertEqual(status.get("scanner_status"), "fresh")
        self.assertEqual(status.get("chain_source"), "broker")
        self.assertIn("disconnected", str(status.get("last_error", "")).lower())

    def test_disconnected_metadata_sets_failed_when_no_broker_cache(self):
        from app.services.options_chain_store import clear_scanner_contracts, update_scan_status

        clear_scanner_contracts(engine, "QQQ")
        update_scan_status(
            engine,
            "QQQ",
            scanner_status="idle",
            chain_source="none",
            contracts_usable=0,
            last_error=None,
        )
        with patch.object(options_chain_scanner, "_broker_connected", return_value=False):
            options_chain_scanner.refresh_metadata("QQQ")

        status = get_scan_status(engine, "QQQ") or {}
        self.assertEqual(status.get("scanner_status"), "failed")
        self.assertEqual(status.get("last_error"), "broker disconnected")

    def test_mock_scan_respects_contract_cap_and_five_dollar_strikes(self):
        settings.options_chain.batch_delay_seconds = 0
        options_chain_scanner.run_quote_scan("QQQ")
        contracts = get_contracts(engine, "QQQ")
        status = get_scan_status(engine, "QQQ") or {}
        self.assertLessEqual(len(contracts), settings.options_chain.max_contracts_per_scan)
        self.assertLessEqual(int(status.get("contracts_planned") or 0), settings.options_chain.max_contracts_per_scan)
        strikes = {float(c["strike"]) for c in contracts}
        for strike in strikes:
            self.assertAlmostEqual(strike % 5, 0.0, delta=0.01, msg=f"strike {strike} not on $5 grid")
        self.assertLessEqual(len(status.get("expiries_selected") or []), settings.options_chain.max_expiries)


if __name__ == "__main__":
    unittest.main()
