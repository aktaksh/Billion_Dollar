import unittest

from app.db import get_engine, init_db
from app.services.chain_fixture_seed import seed_testing_fixture
from app.services.option_chain_quality import validate_chain_quality
from app.services.runtime_mode import (
    effective_allow_stale_runtime_dev,
    get_runtime_mode,
    is_production_valid_chain,
    set_runtime_mode,
)


def _sample_rows() -> list[dict]:
    return [
        {
            "expiry": "2026-07-18",
            "dte": 30,
            "option_type": "call",
            "strike": 735.0,
            "bid": 8.0,
            "ask": 8.4,
        }
    ]


class RuntimeModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = get_engine()
        init_db(self.engine)
        set_runtime_mode(self.engine, "production")

    def test_default_mode_is_production(self) -> None:
        self.assertEqual(get_runtime_mode(self.engine), "production")

    def test_testing_mode_allows_stale(self) -> None:
        self.assertFalse(effective_allow_stale_runtime_dev("production"))
        self.assertTrue(effective_allow_stale_runtime_dev("testing"))

    def test_production_blocks_seeded_fixture(self) -> None:
        ok, reason, _ = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_sample_rows(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="fresh",
            data_status="live",
            snapshot_age_seconds=10.0,
            max_runtime_age_seconds=900,
            contracts_usable=18,
            allow_stale_runtime_dev=False,
            chain_origin="seeded_fixture",
            runtime_mode="production",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "option_chain_quality_failed_seeded_fixture_in_production")

    def test_testing_allows_seeded_fixture(self) -> None:
        ok, reason, _ = validate_chain_quality(
            symbol="QQQ",
            option_chain_rows=_sample_rows(),
            underlying_price=735.0,
            chain_source="broker",
            scanner_status="fresh",
            data_status="live",
            snapshot_age_seconds=10.0,
            max_runtime_age_seconds=900,
            contracts_usable=18,
            allow_stale_runtime_dev=True,
            chain_origin="seeded_fixture",
            runtime_mode="testing",
        )
        self.assertNotEqual(reason, "option_chain_quality_failed_seeded_fixture_in_production")

    def test_is_production_valid_chain(self) -> None:
        self.assertFalse(is_production_valid_chain(chain_origin="seeded_fixture", runtime_mode="production"))
        self.assertFalse(is_production_valid_chain(chain_origin="seeded_fixture", runtime_mode="testing"))
        self.assertFalse(is_production_valid_chain(chain_origin="none"))
        self.assertFalse(
            is_production_valid_chain(
                chain_origin="broker_live",
                chain_source="none",
                contracts_usable=0,
            )
        )
        self.assertTrue(
            is_production_valid_chain(
                chain_origin="broker_live",
                chain_source="broker",
                contracts_usable=18,
            )
        )
        self.assertFalse(
            is_production_valid_chain(
                chain_origin="broker_live",
                chain_source="broker",
                contracts_usable=0,
            )
        )

    def test_seed_testing_fixture_sets_chain_origin(self) -> None:
        result = seed_testing_fixture(self.engine, symbol="QQQ")
        self.assertEqual(result["chain_origin"], "seeded_fixture")

    def test_set_runtime_mode_persists(self) -> None:
        set_runtime_mode(self.engine, "testing")
        self.assertEqual(get_runtime_mode(self.engine), "testing")
        set_runtime_mode(self.engine, "production")
        self.assertEqual(get_runtime_mode(self.engine), "production")


if __name__ == "__main__":
    unittest.main()
