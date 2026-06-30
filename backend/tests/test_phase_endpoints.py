import os
import unittest

os.environ.setdefault("BROKER_BACKEND", "mock")

try:
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from app.config import settings
    from app.services.broker.factory import get_broker_client

    settings.broker_backend = "mock"
    get_broker_client.cache_clear()
    from app.main import app, options_chain_scanner


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi not installed in current interpreter")
class PhaseEndpointsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        get_broker_client().connect()
        settings.options_chain.batch_delay_seconds = 0
        options_chain_scanner.run_quote_scan("QQQ")
        cls.client = TestClient(app)

    def test_ingestion_and_feature_build(self):
        ing = self.client.post(
            "/api/ops/ingestion/run-once",
            json={"tickers": ["QQQ", "SPY"], "include_news": False},
        )
        self.assertEqual(ing.status_code, 200)
        ing_data = ing.json()
        self.assertGreaterEqual(ing_data["processed"], 1)

        feat = self.client.post("/api/ops/features/build", json={"tickers": ["QQQ", "SPY"]})
        self.assertEqual(feat.status_code, 200)
        feat_data = feat.json()
        self.assertGreaterEqual(feat_data["built"], 1)
        self.assertIn("results", feat_data)

    def test_strategy_runtime_replay_and_paper(self):
        runtime = self.client.post(
            "/api/strategy-builder/runtime",
            json={
                "ticker": "QQQ",
                "direction": "bullish",
                "reconciliation_mismatch_active": False,
                "thresholds": {"max_loss_per_trade_usd": 750},
            },
        )
        self.assertEqual(runtime.status_code, 200)
        runtime_data = runtime.json()
        self.assertIn("candidates", runtime_data)
        self.assertIn("top_recommendations", runtime_data)
        self.assertIn("as_of", runtime_data)
        self.assertIn("data_status", runtime_data)
        self.assertIn("runtime_allowed", runtime_data)
        # Mock broker scanner path must block QQQ recommendations.
        self.assertFalse(runtime_data["runtime_allowed"])
        self.assertEqual(runtime_data["candidates"], [])
        self.assertIn("option_chain_quality_failed", runtime_data.get("runtime_block_reason", ""))

        replay = self.client.post(
            "/api/replay/run",
            json={"ticker": "SPY", "direction": "bullish", "scenarios": [-0.03, 0.0, 0.03]},
        )
        self.assertEqual(replay.status_code, 200)
        replay_data = replay.json()
        self.assertIn("results", replay_data)


if __name__ == "__main__":
    unittest.main()
