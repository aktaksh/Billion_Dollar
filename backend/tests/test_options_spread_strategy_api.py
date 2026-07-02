import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from app.config import settings
    from app.main import app


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi not installed in current interpreter")
class OptionsSpreadStrategyApiTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._data_dir = Path(self._tmpdir.name)
        settings.qqq_analyzer_data_dir = str(self._data_dir)
        self.client = TestClient(app)
        self.fixture = {
            "timestamp": datetime.now(UTC).isoformat(),
            "symbol": "SPY",
            "underlying_price": 580.0,
            "bias": "Bullish",
            "confidence": "Medium",
            "suggested_action": "Bull call spread",
            "bullish_score": 7,
            "bearish_score": 2,
            "spread_candidates": [],
            "diagnostics": {"raw_quotes": 120},
        }

    def tearDown(self):
        self._tmpdir.cleanup()
        settings.qqq_analyzer_data_dir = ""

    def test_latest_missing_returns_404(self):
        res = self.client.get("/api/options-spread-strategy/latest", params={"symbol": "SPY"})
        self.assertEqual(res.status_code, 404)

    def test_latest_returns_json_fixture(self):
        path = self._data_dir / "latest_analysis_SPY.json"
        path.write_text(json.dumps(self.fixture), encoding="utf-8")
        res = self.client.get("/api/options-spread-strategy/latest", params={"symbol": "SPY"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["symbol"], "SPY")
        self.assertEqual(body["bias"], "Bullish")

    def test_run_status_not_found(self):
        res = self.client.get("/api/options-spread-strategy/run/does-not-exist")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
