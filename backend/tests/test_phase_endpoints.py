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
    from app.main import app


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi not installed in current interpreter")
class PhaseEndpointsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        get_broker_client().connect()
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
        self.assertIn("as_of", runtime_data)
        self.assertIn("data_status", runtime_data)
        self.assertIn("runtime_allowed", runtime_data)
        self.assertTrue(runtime_data["candidates"])
        for candidate in runtime_data["candidates"]:
            self.assertIn("risk_status", candidate)
            self.assertIn("rule_reasons", candidate)

        replay = self.client.post(
            "/api/replay/run",
            json={"ticker": "QQQ", "direction": "bullish", "scenarios": [-0.03, 0.0, 0.03]},
        )
        self.assertEqual(replay.status_code, 200)
        replay_data = replay.json()
        self.assertIn("results", replay_data)
        self.assertTrue(replay_data["results"])

        paper = self.client.post(
            "/api/paper/run",
            json={"mode": "quick", "ticker": "QQQ", "direction": "bullish", "scenario_return": 0.02},
        )
        self.assertEqual(paper.status_code, 200)
        paper_data = paper.json()
        self.assertIn("signal_id", paper_data)
        self.assertIn("realized_pnl_after_costs_usd", paper_data)


if __name__ == "__main__":
    unittest.main()
