import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

try:
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from app.config import settings
    from app.main import app
    import app.main as main_module


FIXTURES = Path(__file__).resolve().parent / "fixtures"


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi not installed in current interpreter")
class IbkrSyncQuotesTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "test_paper.db"
        self._orig_database_url = settings.database_url
        settings.database_url = f"sqlite:///{self._db_path}"
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()
        self.analysis = json.loads((FIXTURES / "paper_trade_analysis.json").read_text(encoding="utf-8"))
        self.candidate = self.analysis["spread_candidates"][0]

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        settings.database_url = self._orig_database_url
        self._tmpdir.cleanup()

    def test_refresh_market_prices_updates_manual_trade(self):
        res = self.client.post(
            "/api/paper-trading/trades",
            json={"analysis": self.analysis, "candidate": self.candidate, "quantity": 1},
        )
        trade_id = res.json()["id"]

        mock_broker = MagicMock()
        mock_broker.is_available.return_value = (True, "TWS connected")
        mock_broker.fetch_quotes_for_trades.return_value = {
            trade_id: {
                "long": {"bid": 8.0, "ask": 8.2, "mid": 8.1},
                "short": {"bid": 5.5, "ask": 5.7, "mid": 5.6},
            }
        }
        mock_broker.fetch_underlying_price.return_value = 500.0
        mock_broker.name = "tws"
        assert main_module._ibkr_sync is not None
        main_module._ibkr_sync._broker = mock_broker

        refresh = self.client.post("/api/paper-trading/ibkr/refresh-prices")
        self.assertEqual(refresh.status_code, 200)
        body = refresh.json()
        self.assertEqual(body["records_updated"], 1)

        detail = self.client.get(f"/api/paper-trading/trades/{trade_id}").json()
        self.assertEqual(detail["long_mid"], 8.1)
        self.assertEqual(detail["short_mid"], 5.6)
        self.assertIsNotNone(detail["unrealized_pnl"])


if __name__ == "__main__":
    unittest.main()
