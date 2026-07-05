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


FIXTURES = Path(__file__).resolve().parent / "fixtures"


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi not installed in current interpreter")
class PaperTradingApiTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "test_paper.db"
        self._data_dir = Path(self._tmpdir.name) / "data"
        self._data_dir.mkdir()
        self._orig_database_url = settings.database_url
        settings.database_url = f"sqlite:///{self._db_path}"
        settings.qqq_analyzer_data_dir = str(self._data_dir)
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()
        self.analysis = json.loads((FIXTURES / "paper_trade_analysis.json").read_text(encoding="utf-8"))
        self.candidate = self.analysis["spread_candidates"][0]

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        settings.database_url = self._orig_database_url
        self._tmpdir.cleanup()

    def test_create_list_close_trade(self):
        res = self.client.post(
            "/api/paper-trading/trades",
            json={"analysis": self.analysis, "candidate": self.candidate, "notes": "test", "quantity": 1},
        )
        self.assertEqual(res.status_code, 200, res.text)
        trade = res.json()
        self.assertEqual(trade["symbol"], "QQQ")
        self.assertEqual(trade["status"], "OPEN")
        trade_id = trade["id"]

        res = self.client.get("/api/paper-trading/trades", params={"status": "OPEN"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 1)

        res = self.client.post(f"/api/paper-trading/trades/{trade_id}/close", json={"exit_reason": "Test close"})
        self.assertEqual(res.status_code, 200)
        closed = res.json()
        self.assertEqual(closed["status"], "CLOSED")
        self.assertIsNotNone(closed["review"])

    def test_bulk_create(self):
        res = self.client.post("/api/paper-trading/trades/bulk", json={"analysis": self.analysis, "notes": "bulk"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["count"], 1)

    def test_summary_and_export(self):
        self.client.post(
            "/api/paper-trading/trades",
            json={"analysis": self.analysis, "candidate": self.candidate},
        )
        res = self.client.get("/api/paper-trading/summary")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["open_count"], 1)

        res = self.client.get("/api/paper-trading/export", params={"format": "json"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/json", res.headers.get("content-type", ""))


if __name__ == "__main__":
    unittest.main()
