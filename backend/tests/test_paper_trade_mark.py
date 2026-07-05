import json
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from app.config import settings
    from app.main import app
    from app.routes.paper_trading import get_service


FIXTURES = Path(__file__).resolve().parent / "fixtures"


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi not installed in current interpreter")
class PaperTradeMarkTests(unittest.TestCase):
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
        (self._data_dir / "latest_analysis_QQQ.json").write_text(json.dumps(self.analysis), encoding="utf-8")

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        settings.database_url = self._orig_database_url
        self._tmpdir.cleanup()

    def test_mark_to_market_updates_open_trade(self):
        candidate = self.analysis["spread_candidates"][0]
        res = self.client.post(
            "/api/paper-trading/trades",
            json={"analysis": self.analysis, "candidate": candidate, "quantity": 1},
        )
        trade_id = res.json()["id"]

        updated_analysis = json.loads(json.dumps(self.analysis))
        updated_analysis["underlying_price"] = 510.0
        updated_analysis["liquid_options"][0]["mid"] = 9.0
        updated_analysis["liquid_options"][1]["mid"] = 5.0
        (self._data_dir / "latest_analysis_QQQ.json").write_text(json.dumps(updated_analysis), encoding="utf-8")

        count = get_service().mark_to_market_for_symbol("QQQ")
        self.assertEqual(count, 1)

        detail = self.client.get(f"/api/paper-trading/trades/{trade_id}").json()
        self.assertEqual(detail["current_underlying_price"], 510.0)
        self.assertGreater(len(detail["snapshots"]), 1)
        self.assertIsNotNone(detail["unrealized_pnl"])


if __name__ == "__main__":
    unittest.main()
