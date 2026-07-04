"""Strategy matrix — regime-to-strategy permissions."""

from __future__ import annotations

from typing import Any


class StrategyMatrixEngine:
  REGIMES = (
    "Strong Bull Trend",
    "Bull Trend",
    "Bull Pullback",
    "Sideways Range",
    "High Volatility Range",
    "Bear Rally",
    "Bear Trend",
    "Strong Bear Trend",
  )

  STRATEGIES = ("Bull Call", "Bear Put", "Bull Put", "Bear Call", "Iron Condor", "Wait")

  def build(self, regime_name: str) -> list[dict[str, Any]]:
    matrix = {
      "Strong Bull Trend": ("Preferred", "Avoid", "Avoid", "Avoid", "Avoid", "Avoid", "Bull Call preferred"),
      "Bull Trend": ("Preferred", "Avoid", "OK", "Avoid", "Avoid", "Avoid", "Bull Call / Bull Put"),
      "Bull Pullback": ("Wait", "Avoid", "Avoid", "Avoid", "Avoid", "Preferred", "Wait for support confirmation"),
      "Sideways Range": ("Avoid", "Avoid", "OK", "OK", "Preferred", "OK", "Iron Condor or Wait"),
      "High Volatility Range": ("Avoid", "Caution", "Avoid", "Caution", "Caution", "Preferred", "Wait or defined-risk credit spreads"),
      "Bear Rally": ("Avoid", "Caution", "Avoid", "OK", "Avoid", "Preferred", "Wait or Bear Put on rejection"),
      "Bear Trend": ("Avoid", "Preferred", "Avoid", "Avoid", "Avoid", "Avoid", "Bear Put"),
      "Strong Bear Trend": ("Avoid", "Preferred", "Avoid", "Preferred", "Avoid", "Avoid", "Bear Put / Bear Call"),
    }
    row = matrix.get(regime_name, ("Avoid", "Avoid", "Avoid", "Avoid", "Avoid", "Preferred", "No clean setup"))
    return [
      {
        "regime": regime_name,
        "bull_call": row[0],
        "bear_put": row[1],
        "bull_put": row[2],
        "bear_call": row[3],
        "iron_condor": row[4],
        "wait": row[5],
        "notes": row[6],
      }
    ]

  def full_matrix(self) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for regime in self.REGIMES:
      out.extend(self.build(regime))
    return out

  def preferred_strategy(self, regime_name: str) -> str:
    prefs = {
      "Strong Bull Trend": "Bull Call Spread",
      "Bull Trend": "Bull Call Spread",
      "Bull Pullback": "Wait",
      "Sideways Range": "Iron Condor",
      "High Volatility Range": "Wait",
      "Bear Rally": "Wait",
      "Bear Trend": "Bear Put Spread",
      "Strong Bear Trend": "Bear Put Spread",
    }
    return prefs.get(regime_name, "Wait")
