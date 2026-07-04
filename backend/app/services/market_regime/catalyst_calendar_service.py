"""Catalyst calendar — economic events and earnings watch."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


class CatalystCalendarService:
  def upcoming(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
    base = now or datetime.now(UTC)
    events = [
      ("CPI", 12, "08:30 ET", "High", "High"),
      ("PPI", 18, "08:30 ET", "Medium", "Medium"),
      ("FOMC", 35, "14:00 ET", "High", "High"),
      ("FOMC Minutes", 42, "14:00 ET", "Medium", "Medium"),
      ("Jobs Report", 8, "08:30 ET", "High", "High"),
      ("Unemployment Claims", 4, "08:30 ET", "Low", "Low"),
      ("PCE", 28, "08:30 ET", "High", "Medium"),
      ("Treasury Auction (10Y)", 15, "13:00 ET", "Medium", "Medium"),
      ("NVDA Earnings (QQQ holding)", 22, "16:20 ET", "High", "High"),
      ("AAPL Earnings (QQQ holding)", 25, "16:30 ET", "High", "Medium"),
    ]
    out: list[dict[str, Any]] = []
    for name, days, time_str, impact, risk in events:
      event_dt = base + timedelta(days=days)
      out.append({
        "event": name,
        "date": event_dt.date().isoformat(),
        "time": time_str,
        "expected_impact": impact,
        "risk_level": risk,
        "countdown_days": days,
      })
    return sorted(out, key=lambda e: e["countdown_days"])

  def news_catalyst_score(self, events: list[dict[str, Any]]) -> float:
    if not events:
      return 0.0
    penalty = 0.0
    for ev in events:
      if ev.get("countdown_days", 99) <= 3:
        if ev.get("expected_impact") == "High":
          penalty -= 25.0
        elif ev.get("expected_impact") == "Medium":
          penalty -= 10.0
    return max(-100.0, min(100.0, penalty))
