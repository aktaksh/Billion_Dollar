"""Market regime calculator — weighted composite score and classification."""

from __future__ import annotations

from typing import Any

from app.services.market_regime.indicator_helpers import (
  count_trend_checks,
  momentum_score_signed,
  scale_to_century,
  trend_score_signed,
)

WEIGHTS = {
  "trend": 0.30,
  "momentum": 0.20,
  "volatility": 0.20,
  "breadth": 0.15,
  "macro": 0.10,
  "news_catalyst": 0.05,
}


class MarketRegimeCalculator:
  def compute_scores(
    self,
    *,
    qqq_daily: dict[str, Any],
    qqq_intraday: dict[str, Any],
    breadth_score: float,
    volatility_score: float,
    macro_score: float,
    news_catalyst_score: float,
    vix_level: float | None,
  ) -> dict[str, Any]:
    bull, bear = count_trend_checks(qqq_daily)
    raw_trend = trend_score_signed(bull, bear)
    raw_momentum = momentum_score_signed(qqq_daily, qqq_intraday)

    trend = round(scale_to_century(raw_trend, -40, 40), 1)
    momentum = round(scale_to_century(raw_momentum, -25, 25), 1)

    final = round(
      trend * WEIGHTS["trend"]
      + momentum * WEIGHTS["momentum"]
      + volatility_score * WEIGHTS["volatility"]
      + breadth_score * WEIGHTS["breadth"]
      + macro_score * WEIGHTS["macro"]
      + news_catalyst_score * WEIGHTS["news_catalyst"],
      1,
    )

    regime_name = self.classify_regime(
      final_score=final,
      trend_bull=bull,
      trend_bear=bear,
      qqq_daily=qqq_daily,
      qqq_intraday=qqq_intraday,
      volatility_regime=self._vol_regime_label(vix_level, qqq_daily),
    )
    confidence = self._confidence(final, bull, bear, qqq_intraday)
    risk_level = self._risk_level(final, volatility_score, vix_level)

    return {
      "regime_name": regime_name,
      "regime_score": final,
      "confidence": confidence,
      "risk_level": risk_level,
      "trend_score": trend,
      "momentum_score": momentum,
      "volatility_score": volatility_score,
      "breadth_score": breadth_score,
      "macro_score": macro_score,
      "news_catalyst_score": news_catalyst_score,
      "weights": WEIGHTS,
      "trend_bull_count": bull,
      "trend_bear_count": bear,
    }

  def classify_regime(
    self,
    *,
    final_score: float,
    trend_bull: int,
    trend_bear: int,
    qqq_daily: dict[str, Any],
    qqq_intraday: dict[str, Any],
    volatility_regime: str,
  ) -> str:
    line = qqq_daily.get("macd_line")
    signal = qqq_daily.get("macd_signal")
    daily_macd_bull = line is not None and signal is not None and line > signal
    intra_line = qqq_intraday.get("macd_line")
    intra_signal = qqq_intraday.get("macd_signal")
    intra_macd_bull = intra_line is not None and intra_signal is not None and intra_line > intra_signal

    if volatility_regime in ("High", "Extreme") and abs(final_score) < 40:
      return "High Volatility Range"

    if trend_bull >= 3:
      if final_score >= 60 and daily_macd_bull:
        return "Strong Bull Trend"
      if final_score >= 20:
        return "Bull Trend" if daily_macd_bull else "Bull Pullback"
      if not daily_macd_bull and intra_macd_bull:
        return "Bull Pullback"
      return "Bull Pullback" if final_score < 20 else "Bull Trend"

    if trend_bear >= 3:
      if final_score <= -60 and not daily_macd_bull:
        return "Strong Bear Trend"
      if final_score <= -20:
        return "Bear Trend" if not daily_macd_bull else "Bear Rally"
      if intra_macd_bull:
        return "Bear Rally"
      return "Bear Trend"

    if abs(final_score) <= 19:
      return "Sideways Range"
    if final_score > 0:
      return "Bull Trend"
    return "Bear Trend"

  @staticmethod
  def _vol_regime_label(vix: float | None, daily: dict[str, Any]) -> str:
    if vix is not None:
      if vix >= 35:
        return "Extreme"
      if vix >= 28:
        return "High"
      if vix >= 20:
        return "Elevated"
      if vix < 14:
        return "Low"
      return "Normal"
    bb_u, bb_l, bb_m = daily.get("bb_upper"), daily.get("bb_lower"), daily.get("bb_mid")
    if bb_u and bb_l and bb_m and bb_m > 0:
      w = (bb_u - bb_l) / bb_m
      if w > 0.08:
        return "High"
      if w < 0.04:
        return "Low"
    return "Normal"

  @staticmethod
  def _confidence(final: float, bull: int, bear: int, intraday: dict[str, Any]) -> str:
    spread = abs(bull - bear)
    below_ema = intraday.get("ema21") and intraday.get("close", 0) < intraday["ema21"]
    if spread >= 3 and abs(final) >= 50 and not below_ema:
      return "High"
    if spread >= 2 and abs(final) >= 25:
      return "Medium"
    return "Low"

  @staticmethod
  def _risk_level(final: float, vol_score: float, vix: float | None) -> str:
    if vix is not None and vix >= 35:
      return "Extreme"
    if vix is not None and vix >= 28:
      return "High"
    if vol_score <= -50 or abs(final) < 15:
      return "High"
    if vol_score <= -20:
      return "Medium"
    return "Low"

  def multi_timeframe(self, instruments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    qqq = instruments.get("QQQ", {})
    daily = qqq.get("daily_indicators") or {}
    intraday = qqq.get("intraday_indicators") or {}
    tf_label = (qqq.get("analysis") or {}).get("diagnostics", {}).get("intraday_timeframe", "2H")

    frames = [
      ("Daily", daily),
      (str(tf_label), intraday),
    ]
    out: list[dict[str, Any]] = []
    for label, ind in frames:
      if not ind:
        out.append({"timeframe": label, "available": False})
        continue
      bull, bear = count_trend_checks(ind)
      from app.services.market_regime.indicator_helpers import signal_label, trend_label_from_checks

      out.append({
        "timeframe": label,
        "available": True,
        "close": ind.get("close"),
        "ema20": ind.get("ema20") or ind.get("ema21"),
        "ema50": ind.get("ema50"),
        "sma200": ind.get("sma200"),
        "rsi14": ind.get("rsi14"),
        "macd_line": ind.get("macd_line"),
        "macd_signal": ind.get("macd_signal"),
        "macd_hist": ind.get("macd_hist"),
        "atr14": ind.get("atr14"),
        "trend_label": trend_label_from_checks(bull, bear),
        "signal_label": signal_label(ind),
      })

    for stub_tf in ("15m", "1H", "Weekly"):
      if not any(r["timeframe"] == stub_tf for r in out):
        out.append({"timeframe": stub_tf, "available": False, "note": "Data unavailable — future adapter"})
    return out

  def ai_summary(
    self,
    *,
    regime_name: str,
    regime_score: float,
    preferred_strategy: str,
    scores: dict[str, Any],
    breadth: dict[str, Any],
    volatility: dict[str, Any],
    catalysts: list[dict[str, Any]],
  ) -> dict[str, Any]:
    confirms: list[str] = []
    contradicts: list[str] = []

    if scores.get("trend_score", 0) > 30:
      confirms.append("Trend score supports bullish structure")
    elif scores.get("trend_score", 0) < -30:
      confirms.append("Trend score supports bearish structure")
    else:
      contradicts.append("Trend score is mixed")

    if breadth.get("bullish_count", 0) >= 3:
      confirms.append(f"{breadth['bullish_count']} major indexes above EMA20")
    elif breadth.get("bearish_count", 0) >= 3:
      confirms.append(f"{breadth['bearish_count']} major indexes below EMA20")

    if volatility.get("volatility_regime") in ("High", "Extreme"):
      contradicts.append(f"VIX/volatility regime is {volatility['volatility_regime']}")

    near_events = [e for e in catalysts if e.get("countdown_days", 99) <= 5]
    watch = [e["event"] for e in near_events[:3]]

    avoid = []
    if regime_name in ("Bear Trend", "Strong Bear Trend"):
      avoid.append("Bull Call Spread")
    if regime_name in ("Strong Bull Trend", "Bull Trend"):
      avoid.append("Bear Put Spread unless support breaks")
    if volatility.get("volatility_regime") in ("High", "Extreme"):
      avoid.append("Naked short premium")

    return {
      "current_regime": regime_name,
      "why_changed": f"Composite regime score is {regime_score:+.0f} with weighted trend/momentum/breadth inputs.",
      "confirms": confirms or ["Insufficient data for strong confirmation"],
      "contradicts": contradicts or ["No major contradictions detected"],
      "preferred_strategies": [preferred_strategy],
      "avoid_strategies": avoid or ["Aggressive directional spreads without confirmation"],
      "key_levels_events": watch or ["Monitor QQQ daily EMA20 and nearest support"],
      "narrative": (
        f"Market regime is **{regime_name}** (score {regime_score:+.0f}). "
        f"Preferred approach: {preferred_strategy}. "
        f"Risk context: {volatility.get('volatility_regime', 'Normal')} volatility."
      ),
    }
