"""Unit tests for opportunity scoring."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

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
        self.assertIn("Technical Confidence: Not Evaluated", result["reason_json"]["technical_summary"])

    def test_direction_thresholds(self) -> None:
        self.assertEqual(self.calc._direction(75, 50), "Bullish")
        self.assertEqual(self.calc._direction(50, 75), "Bearish")
        self.assertEqual(self.calc._direction(65, 60), "Neutral")

    def test_direction_mixed_when_both_elevated_and_tied(self) -> None:
        # Part 9: two strong-but-conflicting signals should be "Mixed", not "Neutral".
        self.assertEqual(self.calc._direction(68, 66), "Mixed")
        self.assertEqual(self.calc._direction(55, 55), "Neutral")

    def test_market_opportunity_score_uses_part9_weights(self) -> None:
        """Market Opportunity Score = 30% catalyst strength + 25% momentum + 20% regime fit
        + 15% news quality + 5% event timing + 5% paper feedback (Part 9)."""
        result = self.calc.score_symbol(
            symbol="NVDA",
            watchlist_row={"sector": "Semiconductors", "company": "NVIDIA", "priority": 1},
            analysis=None,
            news_signal={
                "label": "Bullish",
                "news_score_0_to_100": 80,
                "last_updated": "2026-07-03T09:00:00+00:00",
                "catalyst_strength_score": 90.0,
                "news_quality_score": 85.0,
                "top_catalyst": "Nvidia files 8-K on new supply agreement",
            },
            market_regime={"summary": {"regime_name": "Bull Trend", "risk_level": "Low"}},
            benchmark_analysis=None,
            paper_trades=[],
            catalyst_events=[],
        )
        self.assertEqual(result["catalyst_strength_score"], 90.0)
        self.assertEqual(result["news_quality_score"], 85.0)
        # High catalyst strength + news quality should push opportunity score well above neutral.
        self.assertGreater(result["market_opportunity_score"], 60)

    def test_top_catalyst_falls_back_to_no_catalyst_message(self) -> None:
        result = self.calc.score_symbol(
            symbol="NVDA",
            watchlist_row={"sector": "Semiconductors", "company": "NVIDIA", "priority": 1},
            analysis=None,
            news_signal={"label": "Neutral", "news_score_0_to_100": 50},
            market_regime=None,
            benchmark_analysis=None,
            paper_trades=[],
            catalyst_events=[],
        )
        self.assertEqual(result["top_catalyst"], "No high-quality ticker-specific catalyst")

    def test_trade_readiness_blocked_when_ibkr_unavailable(self) -> None:
        result = self.calc.score_symbol(
            symbol="NVDA",
            watchlist_row={"sector": "Semiconductors", "company": "NVIDIA", "priority": 1},
            analysis=None,
            news_signal={"label": "Neutral", "news_score_0_to_100": 50},
            market_regime=None,
            benchmark_analysis=None,
            paper_trades=[],
            catalyst_events=[],
            ibkr_available=False,
            has_recent_trade_decision=True,
        )
        self.assertEqual(result["trade_readiness"], "Blocked")

    def test_trade_readiness_ready_when_fresh_and_tde_exists(self) -> None:
        fresh_analysis = {"timestamp": datetime.now(UTC).isoformat(), "underlying_price": 500}
        result = self.calc.score_symbol(
            symbol="NVDA",
            watchlist_row={"sector": "Semiconductors", "company": "NVIDIA", "priority": 1},
            analysis=fresh_analysis,
            news_signal={"label": "Neutral", "news_score_0_to_100": 50},
            market_regime=None,
            benchmark_analysis=None,
            paper_trades=[],
            catalyst_events=[],
            ibkr_available=True,
            has_recent_trade_decision=True,
        )
        self.assertEqual(result["technical_confidence"], "Fresh")
        self.assertEqual(result["trade_readiness"], "Ready")

    def test_trade_readiness_needs_analyze_live_when_stale(self) -> None:
        result = self.calc.score_symbol(
            symbol="NVDA",
            watchlist_row={"sector": "Semiconductors", "company": "NVIDIA", "priority": 1},
            analysis=None,
            news_signal={"label": "Neutral", "news_score_0_to_100": 50},
            market_regime=None,
            benchmark_analysis=None,
            paper_trades=[],
            catalyst_events=[],
            ibkr_available=True,
            has_recent_trade_decision=False,
        )
        self.assertEqual(result["trade_readiness"], "Needs Analyze Live")


if __name__ == "__main__":
    unittest.main()
