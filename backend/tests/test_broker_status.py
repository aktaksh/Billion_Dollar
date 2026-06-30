import unittest
from datetime import UTC, datetime, timedelta

from app.services.broker_status import chain_runtime_gate_status, runtime_gate_status
from app.services.options_chain_store import chain_data_status


class ChainRuntimeGateTests(unittest.TestCase):
    def test_allows_degraded_broker_cache_within_15_min(self):
        completed = datetime.now(UTC) - timedelta(minutes=8)
        ok, reason, warning = chain_runtime_gate_status(
            scanner_status="idle",
            data_status="degraded",
            chain_source="broker",
            allow_mock_option_chain=False,
            last_scan_completed_at=completed,
            contracts_usable=105,
            max_runtime_age_seconds=900,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertIsNotNone(warning)

    def test_blocks_cache_older_than_max_age(self):
        completed = datetime.now(UTC) - timedelta(minutes=20)
        ok, reason, warning = chain_runtime_gate_status(
            scanner_status="stale",
            data_status="stale",
            chain_source="broker",
            allow_mock_option_chain=False,
            last_scan_completed_at=completed,
            contracts_usable=50,
            max_runtime_age_seconds=900,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "chain_stale")
        self.assertIsNone(warning)

    def test_dev_stale_mode_allows_stale_broker_cache(self):
        completed = datetime.now(UTC) - timedelta(minutes=20)
        ok, reason, warning = chain_runtime_gate_status(
            scanner_status="stale",
            data_status="stale",
            chain_source="broker",
            allow_mock_option_chain=False,
            last_scan_completed_at=completed,
            contracts_usable=50,
            max_runtime_age_seconds=900,
            allow_stale_runtime_dev=True,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertEqual(warning, "Dev mode: using stale broker cache from last session")

    def test_blocks_no_usable_contracts(self):
        completed = datetime.now(UTC) - timedelta(minutes=2)
        ok, reason, _warning = chain_runtime_gate_status(
            scanner_status="fresh",
            data_status="degraded",
            chain_source="broker",
            allow_mock_option_chain=False,
            last_scan_completed_at=completed,
            contracts_usable=0,
            max_runtime_age_seconds=900,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "chain_degraded")

    def test_runtime_gate_allows_stale_when_cached_chain_flag(self):
        allowed, reason = runtime_gate_status(
            broker_connected=True,
            data_status="stale",
            reconciliation_mismatch_active=False,
            allow_mock_option_chain=False,
            allow_cached_chain=True,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "ok")


class ChainDataStatusTests(unittest.TestCase):
    def test_idle_with_cache_maps_to_stale(self):
        completed = datetime.now(UTC) - timedelta(minutes=5)
        status = chain_data_status("idle", completed, has_contracts=True)
        self.assertEqual(status, "stale")

    def test_scanning_maps_to_degraded(self):
        completed = datetime.now(UTC) - timedelta(minutes=1)
        status = chain_data_status("scanning", completed, has_contracts=True)
        self.assertEqual(status, "degraded")


if __name__ == "__main__":
    unittest.main()
