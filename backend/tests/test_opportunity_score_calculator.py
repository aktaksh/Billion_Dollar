"""Unit tests for opportunity scoring."""

from __future__ import annotations

import unittest

from app.services.opportunity_scanner.opportunity_score_calculator import OpportunityScoreCalculator


class OpportunityScoreCalculatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calc = OpportunityScoreCalculator()

    def test_bullish_direction(self) -> None:
        analysis = {
            "timestamp": "2026-07-03T10:00:00+00:00",
            "underlying_price": 500,
            "bias": "Bullish",
            "bullish_score": 8,
            "bearish_score": 3,
            "daily_indicators": {
                "close": 500,
                "ema20": 490,
                "ema50": 480,
                "rsi14": 58,
                "macd_line": 1.2,
                "macd_signal": 0.8,
                "macd_expanding": True,
            },
            "support_levels": [{"price": 495, "kind": "swing_low"}],
            "resistance_levels": [{"price": 510, "kind": "swing_high"}],
            "spread_candidates": [
                {"status": "Accepted", "liquidity_score": 80, "spread_type": "bull_call_spread"},
            ],
            "liquid_options": [{"option_type": "call", "open_interest": 500, "spread_pct": 0.05}],
        }
        result = self.calc.score_symbol(
            symbol="NVDA",
            watchlist_row={"sector": "Semiconductors", "company": "NVIDIA", "priority": 1},
            analysis=analysis,
            news_signal={"label": "Bullish", "news_score_0_to_100": 75, "last_updated": "2026-07-03T09:00:00+00:00"},
            market_regime={"summary": {"regime_name": "Bull Trend", "risk_level": "Low"}},
            benchmark_analysis={"bullish_score": 6, "bearish_score": 4, "daily_indicators": {"close": 400}},
            paper_trades=[],
            catalyst_events=[],
        )
        self.assertIn(result["direction_candidate"], ("Bullish", "Neutral"))
        self.assertGreater(result["bull_score"], result["bear_score"])
        self.assertGreaterEqual(result["opportunity_score"], 0)
        self.assertLessEqual(result["opportunity_score"], 100)

    def test_neutral_when_mixed(self) -> None:
        result = self.calc.score_symbol(
            symbol="QQQ",
            watchlist_row={"sector": "ETF", "company": "QQQ", "priority": 5},
            analysis=None,
            news_signal={"label": "Neutral", "news_score_0_to_100": 50},
            market_regime={"summary": {"regime_name": "Sideways", "risk_level": "Medium"}},
            benchmark_analysis=None,
            paper_trades=[],
            catalyst_events=[],
        )
        self.assertEqual(result["direction_candidate"], "Neutral")
        self.assertIn("Technical data unavailable", result["reason_json"]["technical_summary"])

    def test_direction_thresholds(self) -> None:
        self.assertEqual(self.calc._direction(75, 50), "Bullish")
        self.assertEqual(self.calc._direction(50, 75), "Bearish")
        self.assertEqual(self.calc._direction(65, 60), "Neutral")


if __name__ == "__main__":
    unittest.main()
