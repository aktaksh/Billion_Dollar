import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from app.main import app
    from app.routes.spread_analyzer import _qqq_analysis_path
    from app.services.market_regime.market_regime_calculator import MarketRegimeCalculator
    from app.services.market_regime.market_regime_service import MarketRegimeService
    from app.services.market_regime.strategy_matrix_engine import StrategyMatrixEngine
    from app.db import get_engine, init_db


def _qqq_fixture() -> dict:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "symbol": "QQQ",
        "underlying_price": 500.0,
        "confidence": "High",
        "daily_indicators": {
            "close": 500.0,
            "ema20": 495.0,
            "ema50": 490.0,
            "sma200": 480.0,
            "rsi14": 55.0,
            "macd_line": 1.5,
            "macd_signal": 1.0,
            "bb_upper": 510.0,
            "bb_mid": 500.0,
            "bb_lower": 490.0,
            "atr14": 5.0,
        },
        "intraday_indicators": {
            "close": 501.0,
            "ema21": 499.0,
            "rsi14": 52.0,
            "macd_line": 0.5,
            "macd_signal": 0.3,
        },
        "score": {"intraday_timing_bull": 3, "daily_checks": {}, "intraday_checks": {}},
        "support_levels": [],
        "resistance_levels": [],
        "diagnostics": {"intraday_timeframe": "2H"},
    }


class MarketRegimeCalculatorTests(unittest.TestCase):
    def test_strong_bull_classification(self):
        calc = MarketRegimeCalculator()
        daily = _qqq_fixture()["daily_indicators"]
        intraday = _qqq_fixture()["intraday_indicators"]
        result = calc.compute_scores(
            qqq_daily=daily,
            qqq_intraday=intraday,
            breadth_score=60.0,
            volatility_score=15.0,
            macro_score=10.0,
            news_catalyst_score=0.0,
            vix_level=16.0,
        )
        self.assertIn(result["regime_name"], ("Strong Bull Trend", "Bull Trend"))
        self.assertGreater(result["regime_score"], 20)

    def test_strategy_matrix_has_all_regimes(self):
        engine = StrategyMatrixEngine()
        matrix = engine.full_matrix()
        self.assertEqual(len(matrix), 8)
        self.assertEqual(engine.preferred_strategy("Bear Trend"), "Bear Put Spread")


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi not installed")
class MarketRegimeApiTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._data_dir = Path(self._tmpdir.name)
        path = self._data_dir / "latest_analysis_QQQ.json"
        path.write_text(json.dumps(_qqq_fixture()), encoding="utf-8")

        self._db_path = Path(self._tmpdir.name) / "test_regime.db"
        self._engine = get_engine(f"sqlite:///{self._db_path}")
        init_db(self._engine)

        self._orig_analysis_dir = None
        import app.routes.spread_analyzer as sa

        self._orig_fn = sa._qqq_analysis_path

        def _patched(sym: str) -> Path:
            return self._data_dir / f"latest_analysis_{sym.strip().upper()}.json"

        sa._qqq_analysis_path = _patched

        from app.routes import market_regime as mr_route

        self._service = MarketRegimeService(self._engine, analysis_dir_fn=_patched)
        mr_route.set_market_regime_service(self._service)

        class _MockBroker:
            name = "mock"

            def is_available(self):
                return False, "mock"

            def fetch_underlying_price(self, symbol: str) -> float:
                return 0.0

        self._broker_patch = patch(
            "app.services.market_regime.data_adapters.get_broker_provider",
            return_value=_MockBroker(),
        )
        self._broker_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        import app.routes.spread_analyzer as sa

        self._broker_patch.stop()
        sa._qqq_analysis_path = self._orig_fn
        self._tmpdir.cleanup()

    def test_latest_returns_dashboard(self):
        res = self.client.get("/api/market-regime/latest")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("summary", body)
        self.assertIn("regime_name", body["summary"])
        self.assertIn("instruments", body)
        self.assertIn("strategy_matrix", body)

    def test_save_snapshot_daily(self):
        res = self.client.post("/api/market-regime/save-snapshot")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["saved"])
        hist = self.client.get("/api/market-regime/history?days=7")
        self.assertEqual(hist.status_code, 200)
        self.assertGreaterEqual(len(hist.json()), 1)


if __name__ == "__main__":
    unittest.main()
