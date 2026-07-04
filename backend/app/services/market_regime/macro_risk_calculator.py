"""Macro risk calculator — yields, DXY, Fed (stub adapters for FRED/BLS)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


class MacroRiskCalculator:
  """Uses live data when available; otherwise returns structured unavailable placeholders."""

  def compute(self, macro_quotes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ten_y = macro_quotes.get("TNX", {})
    two_y = macro_quotes.get("US2Y", {})
    dxy = macro_quotes.get("DXY", {})

    ten_val = ten_y.get("value")
    two_val = two_y.get("value")
    dxy_val = dxy.get("value")
    curve = round(ten_val - two_val, 2) if ten_val is not None and two_val is not None else None

    macro_score = 0.0
    if curve is not None:
      if curve < 0:
        macro_score = -30.0
      elif curve > 0.5:
        macro_score = 20.0
      else:
        macro_score = 5.0
    if dxy_val is not None:
      chg = dxy.get("daily_pct")
      if chg is not None and chg > 0.5:
        macro_score -= 10.0

    now = datetime.now(UTC)
    return {
      "ten_year_yield": ten_val,
      "two_year_yield": two_val,
      "yield_curve_10y_minus_2y": curve,
      "dxy": dxy_val,
      "fed_funds_rate": None,
      "next_cpi_date": self._next_weekday(now, 12),
      "next_fomc_date": self._next_weekday(now, 35),
      "next_jobs_report_date": self._first_friday_next_month(now),
      "macro_score": round(macro_score, 1),
      "available": any(v.get("available") for v in macro_quotes.values()),
      "source": "stub" if not any(v.get("available") for v in macro_quotes.values()) else "partial",
    }

  @staticmethod
  def _next_weekday(start: datetime, days_ahead: int) -> str:
    target = start + timedelta(days=days_ahead)
    return target.date().isoformat()

  @staticmethod
  def _first_friday_next_month(start: datetime) -> str:
    year, month = start.year, start.month + 1
    if month > 12:
      month, year = 1, year + 1
    d = datetime(year, month, 1, tzinfo=UTC)
    while d.weekday() != 4:
      d += timedelta(days=1)
    return d.date().isoformat()
