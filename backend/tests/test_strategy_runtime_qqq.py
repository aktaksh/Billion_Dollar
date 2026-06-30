import os
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

os.environ.setdefault("BROKER_BACKEND", "mock")

from app.engines.strategy_runtime_engine import run_strategy_runtime
from app.main import (
    _build_chain_diagnostics,
    _resolve_scanner_underlying_price,
    _run_strategy_runtime_once,
)


def base_feature() -> dict:
    return {
        "trend_score": 72.0,
        "news_score": 0.2,
        "sector_strength_score": 65.0,
        "overextended_penalty": 0.0,
        "iv_percentile": 45.0,
        "atr_14": 8.0,
        "beta_to_spy": 1.1,
        "beta_to_qqq": 1.15,
    }


def qqq_chain_near_spot(underlying: float = 735.0) -> list[dict]:
    rows = []
    for strike in (underlying - 10, underlying - 5, underlying, underlying + 5, underlying + 10):
        rows.append(
            {
                "expiry": "2026-07-18",
                "dte": 30,
                "option_type": "call",
                "strike": strike,
                "bid": 8.0,
                "ask": 8.4,
                "volume": 600,
                "open_interest": 2200,
                "delta": 0.55,
                "gamma": 0.02,
                "iv": 0.25,
            }
        )
        rows.append(
            {
                "expiry": "2026-07-18",
                "dte": 30,
                "option_type": "put",
                "strike": strike,
                "bid": 7.8,
                "ask": 8.2,
                "volume": 560,
                "open_interest": 2100,
                "delta": -0.52,
                "gamma": 0.02,
                "iv": 0.26,
            }
        )
    return rows


def _scanner_contracts(underlying: float = 735.0) -> list[dict]:
    rows = []
    for strike in (underlying - 10, underlying - 5, underlying, underlying + 5, underlying + 10):
        for option_type in ("call", "put"):
            rows.append(
                {
                    "symbol": "QQQ",
                    "expiry": "2026-07-18",
                    "dte": 30,
                    "option_type": option_type,
                    "strike": strike,
                    "bid": 8.0,
                    "ask": 8.4,
                    "volume": 600,
                    "open_interest": 2200,
                    "delta": 0.55 if option_type == "call" else -0.52,
                    "gamma": 0.02,
                    "iv": 0.25,
                }
            )
    return rows


def _fresh_broker_snapshot(underlying: float = 735.0) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "symbol": "QQQ",
        "contracts": _scanner_contracts(underlying),
        "scan_status": {
            "scanner_status": "fresh",
            "underlying_price": underlying,
            "contracts_usable": 50,
            "last_scan_completed_at": now,
            "chain_source": "broker",
        },
        "data_status": "live",
        "chain_source": "broker",
    }


class StrategyRuntimeQqqTests(unittest.TestCase):
    def test_resolve_scanner_underlying_price_prefers_scanner(self):
        price, source = _resolve_scanner_underlying_price(
            {"underlying_price": 735.0},
            {"last": 480.0},
            {"last_price": 480.0},
        )
        self.assertEqual(price, 735.0)
        self.assertEqual(source, "scanner")

    def test_build_chain_diagnostics_warns_on_feature_divergence(self):
        diag = _build_chain_diagnostics(
            data_status="live",
            chain_source="broker",
            scanner_status="fresh",
            underlying_price=735.0,
            underlying_price_source="scanner",
            snapshot_age_seconds=60.0,
            quality_diag={"raw_contracts": 10},
            feature_last_price=480.0,
        )
        self.assertEqual(diag["underlying_price_source"], "scanner")
        self.assertIn("underlying_price_warning", diag)
        self.assertGreater(diag["feature_price_divergence_pct"], 0.01)

    def test_run_strategy_runtime_uses_scanner_underlying_not_stale_feature(self):
        chain = qqq_chain_near_spot(735.0)
        stale_feature = {**base_feature(), "last_price": 480.0}
        without_scanner, leg_diag_without = run_strategy_runtime(
            ticker="QQQ",
            direction="bullish",
            market_snapshot={"last": 480.0},
            feature_snapshot=stale_feature,
            option_chain_snapshot=chain,
            reconciliation_mismatch_active=False,
        )
        with_scanner, leg_diag_with = run_strategy_runtime(
            ticker="QQQ",
            direction="bullish",
            market_snapshot={"last": 480.0},
            feature_snapshot=stale_feature,
            option_chain_snapshot=chain,
            reconciliation_mismatch_active=False,
            underlying_price=735.0,
        )
        self.assertEqual(leg_diag_without["usable_contracts"], 0)
        self.assertGreater(leg_diag_with["usable_contracts"], 0)
        self.assertTrue(with_scanner)

    @patch("app.main._latest_payload_by_event_ticker")
    @patch("app.main.get_latest_snapshot")
    @patch("app.main._broker_state")
    def test_mock_scanner_snapshot_blocks_runtime(self, mock_broker, mock_snapshot, mock_latest):
        mock_broker.return_value = {"connected": True}
        mock_snapshot.return_value = {
            **_fresh_broker_snapshot(),
            "data_status": "mock",
            "chain_source": "mock",
            "scan_status": {
                **_fresh_broker_snapshot()["scan_status"],
                "chain_source": "mock",
            },
        }
        mock_latest.return_value = None

        result = _run_strategy_runtime_once(
            ticker="QQQ",
            direction="bullish",
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0},
        )
        self.assertFalse(result.runtime_allowed)
        self.assertEqual(result.runtime_block_reason, "option_chain_quality_failed_mock_data")
        self.assertEqual(len(result.top_recommendations), 0)
        self.assertEqual(len(result.candidates), 0)

    @patch("app.main._latest_payload_by_event_ticker")
    @patch("app.main.get_latest_snapshot")
    @patch("app.main._broker_state")
    def test_fresh_broker_scanner_allows_runtime_with_candidates(self, mock_broker, mock_snapshot, mock_latest):
        mock_broker.return_value = {"connected": True}
        mock_snapshot.return_value = _fresh_broker_snapshot()
        feature = {**base_feature(), "last_price": 735.0, "ticker": "QQQ"}

        def _latest(event_type: str, ticker: str):
            if event_type == "SymbolFeatureSnapshotBuilt":
                return feature
            if event_type == "MarketSnapshotCaptured":
                return {"last": 735.0, "ticker": "QQQ", "captured_at": datetime.now(UTC).isoformat()}
            return None

        mock_latest.side_effect = _latest

        result = _run_strategy_runtime_once(
            ticker="QQQ",
            direction="bullish",
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0},
        )
        self.assertTrue(result.runtime_allowed)
        self.assertIsNone(result.runtime_block_reason)
        self.assertEqual(result.chain_diagnostics.get("underlying_price_source"), "scanner")
        self.assertGreater(len(result.allowed_candidates), 0)
        for top in result.top_recommendations:
            self.assertEqual(top.risk_status, "allow")
            if top.strategy_type in {"bull_call_debit_spread", "bear_put_debit_spread", "long_call", "long_put"}:
                for leg in top.legs:
                    dist = abs(float(leg["strike"]) - 735.0) / 735.0
                    self.assertLessEqual(dist, 0.12)


if __name__ == "__main__":
    unittest.main()
