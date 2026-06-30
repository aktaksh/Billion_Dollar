import unittest
from datetime import UTC, datetime, timedelta

from app.services.option_chain_quality import validate_chain_quality


def _broker_chain_near_spot(underlying: float = 735.0) -> list[dict]:
    strikes = [underlying - 10, underlying - 5, underlying, underlying + 5, underlying + 10]
    return [
        {
            "expiry": "2026-07-18",
            "dte": 30,
            "option_type": "call",
            "strike": strike,
            "bid": 8.0,
            "ask": 8.4,
            "volume": 600,
            "open_interest": 2200,
        }
        for strike in strikes
    ]


def _far_strike_chain() -> list[dict]:
    return [
        {
            "expiry": "2026-07-18",
            "dte": 30,
            "option_type": "call",
            "strike": 485.0,
            "bid": 8.0,
            "ask": 8.4,
            "volume": 600,
            "open_interest": 2200,
        },
        {
            "expiry": "2026-07-18",
            "dte": 30,
            "option_type": "call",
            "strike": 510.0,
            "bid": 6.0,
            "ask": 6.4,
            "volume": 500,
            "open_interest": 1800,
        },
    ]


class OptionChainQualityTests(unittest.TestCase):
    def test_blocks_mock_data(self):
        ok, reason, _diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_broker_chain_near_spot(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="fresh",
            data_status="mock",
            snapshot_age_seconds=60.0,
            max_runtime_age_seconds=900,
            contracts_usable=50,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "option_chain_quality_failed_mock_data")

    def test_blocks_non_broker_source(self):
        ok, reason, _diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_broker_chain_near_spot(),
            underlying_price=735.0,
            chain_source="mock",
            scanner_status="fresh",
            data_status="live",
            snapshot_age_seconds=60.0,
            max_runtime_age_seconds=900,
            contracts_usable=50,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "option_chain_quality_failed_non_broker")

    def test_blocks_far_strikes(self):
        ok, reason, diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_far_strike_chain(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="fresh",
            data_status="live",
            snapshot_age_seconds=60.0,
            max_runtime_age_seconds=900,
            contracts_usable=50,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "option_chain_quality_failed_far_strikes")
        self.assertGreater(diag["nearest_strike_distance_pct"], 0.10)

    def test_blocks_stale_snapshot(self):
        ok, reason, _diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_broker_chain_near_spot(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="fresh",
            data_status="live",
            snapshot_age_seconds=1200.0,
            max_runtime_age_seconds=900,
            contracts_usable=50,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "option_chain_quality_failed_stale")

    def test_allows_fresh_broker_chain_near_spot(self):
        ok, reason, diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_broker_chain_near_spot(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="fresh",
            data_status="live",
            snapshot_age_seconds=120.0,
            max_runtime_age_seconds=900,
            contracts_usable=50,
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)
        self.assertLessEqual(diag["nearest_strike_distance_pct"], 0.10)

    def test_allows_partial_with_enough_usable(self):
        ok, reason, _diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_broker_chain_near_spot(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="partial",
            data_status="live",
            snapshot_age_seconds=120.0,
            max_runtime_age_seconds=900,
            contracts_usable=20,
            min_usable_contracts=10,
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_blocks_partial_without_enough_usable(self):
        ok, reason, _diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_broker_chain_near_spot(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="partial",
            data_status="live",
            snapshot_age_seconds=120.0,
            max_runtime_age_seconds=900,
            contracts_usable=5,
            min_usable_contracts=10,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "option_chain_quality_failed_scanner_status")

    def test_blocks_scanner_status_stale(self):
        ok, reason, _diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_broker_chain_near_spot(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="stale",
            data_status="live",
            snapshot_age_seconds=120.0,
            max_runtime_age_seconds=900,
            contracts_usable=50,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "option_chain_quality_failed_scanner_status")

    def test_blocks_scanner_status_failed(self):
        ok, reason, _diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_broker_chain_near_spot(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="failed",
            data_status="live",
            snapshot_age_seconds=120.0,
            max_runtime_age_seconds=900,
            contracts_usable=50,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "option_chain_quality_failed_scanner_status")

    def test_dev_stale_mode_allows_stale_broker_cache(self):
        ok, reason, diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_broker_chain_near_spot(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="stale",
            data_status="stale",
            snapshot_age_seconds=3600.0,
            max_runtime_age_seconds=900,
            contracts_usable=50,
            allow_stale_runtime_dev=True,
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)
        self.assertEqual(diag["effective_scanner_status"], "partial_with_enough_usable")

    def test_dev_stale_mode_still_blocks_mock(self):
        ok, reason, _diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_broker_chain_near_spot(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="stale",
            data_status="mock",
            snapshot_age_seconds=3600.0,
            max_runtime_age_seconds=900,
            contracts_usable=50,
            allow_stale_runtime_dev=True,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "option_chain_quality_failed_mock_data")

    def test_production_blocks_seeded_fixture_origin(self):
        ok, reason, _diag = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_broker_chain_near_spot(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="fresh",
            data_status="live",
            snapshot_age_seconds=120.0,
            max_runtime_age_seconds=900,
            contracts_usable=50,
            chain_origin="seeded_fixture",
            runtime_mode="production",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "option_chain_quality_failed_seeded_fixture_in_production")


if __name__ == "__main__":
    unittest.main()
