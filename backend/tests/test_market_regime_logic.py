"""Mirror of frontend/lib/marketRegime.ts rules for CI coverage."""

from __future__ import annotations

import unittest
from typing import Any


def _macd_bullish(ind: dict[str, Any]) -> bool:
    line = ind.get("macd_line")
    signal = ind.get("macd_signal")
    return line is not None and signal is not None and line > signal


def _count_trend_checks(daily: dict[str, Any]) -> tuple[int, int]:
    bull = bear = 0
    close = daily["close"]
    if daily.get("ema20") is not None:
        if close > daily["ema20"]:
            bull += 1
        elif close < daily["ema20"]:
            bear += 1
    if daily.get("ema20") is not None and daily.get("ema50") is not None:
        if daily["ema20"] > daily["ema50"]:
            bull += 1
        elif daily["ema20"] < daily["ema50"]:
            bear += 1
    if daily.get("ema50") is not None and daily.get("sma200") is not None:
        if daily["ema50"] > daily["sma200"]:
            bull += 1
        elif daily["ema50"] < daily["sma200"]:
            bear += 1
    if daily.get("rsi14") is not None:
        if daily["rsi14"] > 50:
            bull += 1
        elif daily["rsi14"] < 50:
            bear += 1
    return bull, bear


def _trend_score(bull: int, bear: int) -> int:
    if bull >= bear:
        return bull * 10
    return -bear * 10


def _momentum_score(daily: dict[str, Any], intraday: dict[str, Any]) -> int:
    score = 0
    if _macd_bullish(daily):
        score += 15
    elif daily.get("macd_line") is not None and daily.get("macd_signal") is not None:
        score -= 15
    if daily.get("macd_expanding"):
        score += 5
    if daily.get("macd_weakening"):
        score -= 5
    if _macd_bullish(intraday):
        score += 5
    elif intraday.get("macd_line") is not None and intraday.get("macd_signal") is not None:
        score -= 5
    return max(-25, min(25, score))


def _intraday_timing_score(data: dict[str, Any], intraday: dict[str, Any]) -> int:
    score = (data["score"].get("intraday_timing_bull") or 0) * 5
    if intraday.get("ema21") is not None and intraday["close"] < intraday["ema21"]:
        score = max(0, score - 8)
    return max(0, min(20, score))


def _support_break(data: dict[str, Any], daily: dict[str, Any]) -> bool:
    if data["score"]["daily_checks"].get("reject_res_or_break_support"):
        return True
    supports = [s["price"] for s in data.get("support_levels", []) if s.get("price", 0) > 0]
    if not supports:
        return False
    nearest = min(supports, key=lambda p: abs(p - daily["close"]))
    return daily["close"] < nearest


def _strategy_filter(
    data: dict[str, Any],
    daily: dict[str, Any],
    intraday: dict[str, Any],
    trend_bull: int,
) -> str:
    daily_macd_bull = _macd_bullish(daily)
    intra_macd_bull = _macd_bullish(intraday)
    bull_allowed = (
        trend_bull >= 3
        and (daily.get("rsi14") or 0) > 50
        and intraday.get("ema21") is not None
        and intraday["close"] > intraday["ema21"]
        and intra_macd_bull
    )
    bear_allowed = (
        daily.get("ema20") is not None
        and daily["close"] < daily["ema20"]
        and (daily.get("rsi14") or 100) < 50
        and not daily_macd_bull
        and _support_break(data, daily)
    )
    if bull_allowed:
        return "Bull Call Spread"
    if bear_allowed:
        return "Bear Put Spread"
    return "WAIT"


def _classify_regime(
    trend_bull: int,
    trend_bear: int,
    daily: dict[str, Any],
    intraday: dict[str, Any],
    final_score: int,
    it_bull: int,
) -> str:
    daily_macd_bull = _macd_bullish(daily)
    intra_macd_bull = _macd_bullish(intraday)
    if trend_bull >= 3:
        if daily_macd_bull and final_score >= 50:
            return "Strong Bull"
        if not daily_macd_bull:
            return "Bull Trend with Momentum Warning" if intra_macd_bull else "Bull Pullback"
        if final_score >= 35:
            return "Strong Bull"
        return "Bull Pullback"
    if trend_bear >= 3:
        if not daily_macd_bull and final_score <= -40:
            return "Bear Trend"
        if it_bull >= 2:
            return "Bear Pullback"
        return "Bear Trend"
    return "Sideways"


def compute_market_regime(data: dict[str, Any]) -> dict[str, Any]:
    daily = data["daily_indicators"]
    intraday = data["intraday_indicators"]
    trend_bull, trend_bear = _count_trend_checks(daily)
    trend = _trend_score(trend_bull, trend_bear)
    momentum = _momentum_score(daily, intraday)
    intraday_timing = _intraday_timing_score(data, intraday)
    final = trend + momentum + intraday_timing
    it_bull = data["score"].get("intraday_timing_bull") or 0
    label = _classify_regime(trend_bull, trend_bear, daily, intraday, final, it_bull)
    strategy_filter = _strategy_filter(data, daily, intraday, trend_bull)
    return {
        "label": label,
        "strategyFilter": strategy_filter,
        "scores": {"trend": trend, "momentum": momentum, "intradayTiming": intraday_timing, "final": final},
        "trendBullCount": trend_bull,
        "trendBearCount": trend_bear,
    }


def _base_fixture(**overrides: Any) -> dict[str, Any]:
    daily = {
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
        "macd_expanding": False,
        "macd_weakening": False,
    }
    intraday = {
        "close": 501.0,
        "ema9": 500.5,
        "ema21": 499.0,
        "rsi14": 52.0,
        "macd_line": 0.5,
        "macd_signal": 0.3,
    }
    score = {
        "intraday_timing_bull": 3,
        "intraday_timing_bear": 1,
        "daily_checks": {"reject_res_or_break_support": False},
        "intraday_checks": {},
        "bullish_score": 8,
        "bearish_score": 2,
        "bias": "Bullish",
        "confidence": "High",
        "action": "Bull call spread",
        "invalid_conditions": [],
    }
    fixture: dict[str, Any] = {
        "symbol": "QQQ",
        "confidence": "High",
        "daily_indicators": daily,
        "intraday_indicators": intraday,
        "score": score,
        "support_levels": [{"price": 495.0, "kind": "pivot", "side": "support", "distance_abs": 5, "distance_pct": 1}],
        "resistance_levels": [],
        "diagnostics": {"intraday_timeframe": "2H"},
    }
    for key, val in overrides.items():
        if key in ("daily_indicators", "intraday_indicators", "score"):
            fixture[key].update(val)
        else:
            fixture[key] = val
    return fixture


class MarketRegimeLogicTests(unittest.TestCase):
    def test_bull_pullback_momentum_warning(self):
        data = _base_fixture(
            daily_indicators={
                "macd_line": 0.8,
                "macd_signal": 1.2,
                "macd_weakening": True,
            },
            intraday_indicators={
                "close": 498.0,
                "ema21": 499.0,
                "macd_line": 0.6,
                "macd_signal": 0.4,
            },
            score={"intraday_timing_bull": 2},
        )
        result = compute_market_regime(data)
        self.assertEqual(result["label"], "Bull Trend with Momentum Warning")
        self.assertEqual(result["strategyFilter"], "WAIT")
        self.assertGreaterEqual(result["trendBullCount"], 3)
        self.assertLess(result["scores"]["momentum"], 0)

    def test_strong_bull(self):
        data = _base_fixture(
            score={"intraday_timing_bull": 4},
            intraday_indicators={
                "close": 502.0,
                "ema21": 499.0,
                "macd_line": 0.8,
                "macd_signal": 0.4,
                "rsi14": 58.0,
            },
        )
        result = compute_market_regime(data)
        self.assertEqual(result["label"], "Strong Bull")
        self.assertEqual(result["strategyFilter"], "Bull Call Spread")
        self.assertGreaterEqual(result["scores"]["final"], 50)

    def test_bear_put_filter(self):
        data = _base_fixture(
            daily_indicators={
                "close": 488.0,
                "ema20": 495.0,
                "ema50": 492.0,
                "sma200": 485.0,
                "rsi14": 42.0,
                "macd_line": -0.5,
                "macd_signal": 0.2,
            },
            intraday_indicators={
                "close": 487.0,
                "ema21": 490.0,
                "macd_line": -0.2,
                "macd_signal": 0.1,
                "rsi14": 40.0,
            },
            score={
                "intraday_timing_bull": 1,
                "daily_checks": {"reject_res_or_break_support": True},
            },
            support_levels=[{"price": 492.0, "kind": "pivot", "side": "support", "distance_abs": 4, "distance_pct": 0.8}],
        )
        result = compute_market_regime(data)
        self.assertEqual(result["strategyFilter"], "Bear Put Spread")
        self.assertIn(result["label"], ("Bear Trend", "Bear Pullback", "Sideways"))

    def test_wait_mixed_daily_intraday(self):
        data = _base_fixture(
            daily_indicators={
                "close": 500.0,
                "ema20": 495.0,
                "ema50": 490.0,
                "sma200": 480.0,
                "rsi14": 55.0,
                "macd_line": 0.8,
                "macd_signal": 1.2,
            },
            intraday_indicators={
                "close": 497.0,
                "ema21": 499.0,
                "macd_line": -0.1,
                "macd_signal": 0.2,
                "rsi14": 48.0,
            },
            score={"intraday_timing_bull": 1},
        )
        result = compute_market_regime(data)
        self.assertEqual(result["strategyFilter"], "WAIT")
        self.assertIn(result["label"], ("Bull Pullback", "Bull Trend with Momentum Warning", "Sideways"))


if __name__ == "__main__":
    unittest.main()
