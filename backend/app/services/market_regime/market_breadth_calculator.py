"""Market breadth calculator — index participation above key EMAs."""

from __future__ import annotations

from typing import Any

from app.services.market_regime.indicator_helpers import count_trend_checks, scale_to_century


class MarketBreadthCalculator:
  INDEX_KEYS = ("QQQ", "SPY", "IWM", "DIA")
  SEMI_KEYS = ("SMH", "SOXX")

  def compute(self, instruments: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    bullish = bearish = 0

    for sym in self.INDEX_KEYS:
      snap = instruments.get(sym, {})
      daily = snap.get("daily_indicators") or {}
      close = daily.get("close") or snap.get("price")
      ema20 = daily.get("ema20")
      above = None
      if close is not None and ema20 is not None:
        above = float(close) > float(ema20)
        if above:
          bullish += 1
        else:
          bearish += 1
      rows.append({
        "symbol": sym,
        "above_ema20": above,
        "close": close,
        "ema20": ema20,
      })

    smh = instruments.get("SMH", {})
    soxx = instruments.get("SOXX", {})
    smh_bull, _ = count_trend_checks(smh.get("daily_indicators") or {})
    soxx_bull, _ = count_trend_checks(soxx.get("daily_indicators") or {})
    semi_confirming = smh_bull >= 3 or soxx_bull >= 3
    semi_bearish = smh_bull < 2 and soxx_bull < 2 and (smh.get("daily_indicators") or soxx.get("daily_indicators"))

    total = bullish + bearish
    breadth_ratio = (bullish - bearish) / total if total else 0.0
    breadth_score = round(scale_to_century(breadth_ratio, -1.0, 1.0), 1)

    return {
      "rows": rows,
      "qqq_above_ema20": next((r["above_ema20"] for r in rows if r["symbol"] == "QQQ"), None),
      "spy_above_ema20": next((r["above_ema20"] for r in rows if r["symbol"] == "SPY"), None),
      "iwm_above_ema20": next((r["above_ema20"] for r in rows if r["symbol"] == "IWM"), None),
      "dia_above_ema20": next((r["above_ema20"] for r in rows if r["symbol"] == "DIA"), None),
      "smh_soxx_confirming": semi_confirming,
      "smh_soxx_bearish": bool(semi_bearish),
      "bullish_count": bullish,
      "bearish_count": bearish,
      "breadth_score": breadth_score,
      "heatmap": [
        {"symbol": r["symbol"], "state": "bull" if r["above_ema20"] else "bear" if r["above_ema20"] is False else "na"}
        for r in rows
      ],
    }
