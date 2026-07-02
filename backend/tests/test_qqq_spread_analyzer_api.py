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
    from app.routes.spread_analyzer import _qqq_analyzer_data_dir


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi not installed in current interpreter")
class QqqSpreadAnalyzerApiTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._data_dir = Path(self._tmpdir.name)
        settings.qqq_analyzer_data_dir = str(self._data_dir)
        self.client = TestClient(app)
        self.fixture = {
            "timestamp": datetime.now(UTC).isoformat(),
            "symbol": "QQQ",
            "underlying_price": 725.14,
            "bias": "Neutral",
            "confidence": "Medium",
            "suggested_action": "No trade / wait",
            "bullish_score": 6,
            "bearish_score": 1,
            "spread_candidates": [],
            "diagnostics": {"raw_quotes": 136},
        }

    def tearDown(self):
        self._tmpdir.cleanup()
        settings.qqq_analyzer_data_dir = ""

    def test_latest_missing_returns_404(self):
        res = self.client.get("/api/qqq-spread-analyzer/latest", params={"symbol": "QQQ"})
        self.assertEqual(res.status_code, 404)

    def test_latest_returns_json_fixture(self):
        path = self._data_dir / "latest_analysis_QQQ.json"
        path.write_text(json.dumps(self.fixture), encoding="utf-8")
        res = self.client.get("/api/qqq-spread-analyzer/latest", params={"symbol": "QQQ"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["symbol"], "QQQ")
        self.assertEqual(body["bias"], "Neutral")
        self.assertEqual(body["diagnostics"]["raw_quotes"], 136)

    def test_run_status_not_found(self):
        res = self.client.get("/api/qqq-spread-analyzer/run/does-not-exist")
        self.assertEqual(res.status_code, 404)

    def test_data_dir_helper_uses_override(self):
        self.assertEqual(_qqq_analyzer_data_dir(), self._data_dir)


if __name__ == "__main__":
    unittest.main()
