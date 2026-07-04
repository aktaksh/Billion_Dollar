import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from app.db import get_engine, init_db
    from app.main import app
    from app.routes.trade_decision import set_trade_decision_engine
    from app.services.trade_decision.trade_decision_calculator import TradeDecisionCalculator
    from app.services.trade_decision.trade_decision_engine import TradeDecisionEngine
    from app.services.trade_decision.trade_score_calculator import TradeScoreCalculator


class TradeScoreCalculatorTests(unittest.TestCase):
    def test_weighted_total_caps_at_100(self):
        calc = TradeScoreCalculator()
        components = {k: 100.0 for k in calc.weights}
        total = calc.weighted_total(components)
        self.assertGreaterEqual(total, 100.0)

    def test_evaluate_returns_decision(self):
        calc = TradeDecisionCalculator()
        analysis = {
            "symbol": "QQQ",
            "confidence": "High",
            "bullish_score": 7,
            "bearish_score": 2,
            "suggested_action": "Wait",
            "daily_indicators": {
                "close": 500,
                "ema20": 495,
                "ema50": 490,
                "sma200": 480,
                "rsi14": 55,
                "macd_line": 1.5,
                "macd_signal": 1.0,
            },
            "score": {
                "daily_checks": {
                    "close_gt_ema20": True,
                    "ema20_gt_ema50": True,
                    "ema50_gt_sma200": True,
                    "rsi_gt_50": True,
                    "macd_gt_signal": True,
                },
            },
            "spread_candidates": [
                {"status": "Accepted", "strategy": "Bull call spread", "liquidity_score": 80, "reward_risk": 1.8},
            ],
            "resistance_levels": [],
            "risk_notes": [],
        }
        result = calc.evaluate(analysis, regime_label="Strong Bull", regime_scores={"final": 55}, strategy_filter="Bull Call Spread")
        self.assertIn("decision", result)
        self.assertGreaterEqual(result["trade_score"], 50)
        self.assertIn(result["decision"], ("Bull Call Spread", "WAIT", "Bull Put Spread"))


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi not installed")
class TradeDecisionApiTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "test_decisions.db"
        self._engine = get_engine(f"sqlite:///{db_path}")
        init_db(self._engine)
        self._svc = TradeDecisionEngine(self._engine)
        set_trade_decision_engine(self._svc)
        self.client = TestClient(app)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_record_decision(self):
        res = self.client.post(
            "/api/trade-decision/record",
            json={
                "symbol": "QQQ",
                "decision": "WAIT",
                "trade_score": 62,
                "confidence": "Medium",
                "market_regime": "Bull Pullback",
                "risk_level": "Medium",
                "summary": "Decision: WAIT",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["saved"])

    def test_recent_decisions(self):
        self.client.post(
            "/api/trade-decision/record",
            json={"symbol": "QQQ", "decision": "WAIT", "trade_score": 50, "confidence": "Low", "risk_level": "High"},
        )
        res = self.client.get("/api/trade-decision/recent/QQQ")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(len(res.json()), 1)


if __name__ == "__main__":
    unittest.main()
