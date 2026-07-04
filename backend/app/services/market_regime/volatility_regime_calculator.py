"""Volatility regime calculator — VIX, ATR, Bollinger width."""

from __future__ import annotations

from typing import Any

from app.services.market_regime.indicator_helpers import scale_to_century


class VolatilityRegimeCalculator:
  def compute(
    self,
    *,
    qqq_daily: dict[str, Any],
    vix_level: float | None,
    vix_prev: float | None = None,
  ) -> dict[str, Any]:
    bb_u = qqq_daily.get("bb_upper")
    bb_l = qqq_daily.get("bb_lower")
    bb_m = qqq_daily.get("bb_mid")
    atr = qqq_daily.get("atr14")
    close = qqq_daily.get("close") or 1.0

    bb_width: float | None = None
    if bb_u and bb_l and bb_m and bb_m > 0:
      bb_width = round((bb_u - bb_l) / bb_m * 100, 2)

    atr_trend = "Flat"
    if qqq_daily.get("atr_rising"):
      atr_trend = "Rising"
    elif qqq_daily.get("atr_falling"):
      atr_trend = "Falling"
    elif atr and close and atr / close > 0.025:
      atr_trend = "Elevated"

    regime = "Normal"
    vol_score = 0.0
    if vix_level is not None:
      if vix_level < 14:
        regime, vol_score = "Low", 40.0
      elif vix_level < 20:
        regime, vol_score = "Normal", 15.0
      elif vix_level < 28:
        regime, vol_score = "Elevated", -20.0
      elif vix_level < 35:
        regime, vol_score = "High", -50.0
      else:
        regime, vol_score = "Extreme", -80.0
    elif bb_width is not None:
      if bb_width < 4:
        regime, vol_score = "Low", 30.0
      elif bb_width > 8:
        regime, vol_score = "High", -40.0
      else:
        regime, vol_score = "Normal", 10.0

    vix_change: float | None = None
    if vix_level is not None and vix_prev and vix_prev > 0:
      vix_change = round((vix_level - vix_prev) / vix_prev * 100, 2)

    return {
      "vix_level": vix_level,
      "vix_daily_change_pct": vix_change,
      "atr_trend": atr_trend,
      "bollinger_width_pct": bb_width,
      "iv_rank": qqq_daily.get("iv_rank"),
      "iv_percentile": qqq_daily.get("iv_percentile"),
      "volatility_regime": regime,
      "volatility_score": round(vol_score, 1),
      "risk_level": self._risk_from_regime(regime),
    }

  @staticmethod
  def _risk_from_regime(regime: str) -> str:
    return {
      "Low": "Low",
      "Normal": "Medium",
      "Elevated": "Medium",
      "High": "High",
      "Extreme": "Extreme",
    }.get(regime, "Medium")
