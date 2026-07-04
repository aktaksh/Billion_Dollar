"""Market data adapters — IBKR, analyzer snapshots, external API stubs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from app.services.broker.broker_provider import get_broker_provider

logger = logging.getLogger(__name__)

INDEX_SYMBOLS = ("QQQ", "SPY", "IWM", "DIA", "SMH", "SOXX")
MACRO_SYMBOLS = ("VIX", "TNX", "DXY", "US2Y")


class MarketDataAdapters:
  """Load market data from existing app sources with graceful fallbacks."""

  def __init__(self, analysis_dir_fn: Callable[[str], Path]) -> None:
    self._analysis_dir_fn = analysis_dir_fn
    self._broker = get_broker_provider()

  def load_analyzer_snapshot(self, symbol: str) -> dict[str, Any] | None:
    path = self._analysis_dir_fn(symbol.strip().upper())
    if not path.is_file():
      return None
    try:
      return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
      logger.warning("Failed to read analyzer snapshot %s: %s", path, exc)
      return None

  def fetch_live_price(self, symbol: str) -> float | None:
    sym = symbol.strip().upper()
    try:
      price = self._broker.fetch_underlying_price(sym)
      return price if price and price > 0 else None
    except Exception as exc:
      logger.debug("Live price unavailable for %s: %s", sym, exc)
      return None

  def instrument_snapshot(self, symbol: str) -> dict[str, Any]:
    sym = symbol.strip().upper()
    analysis = self.load_analyzer_snapshot(sym)
    daily = (analysis or {}).get("daily_indicators") or {}
    intraday = (analysis or {}).get("intraday_indicators") or {}
    price = (analysis or {}).get("underlying_price") or daily.get("close")
    if not price:
      price = self.fetch_live_price(sym)

    prev_close = daily.get("prev_close") or daily.get("close")
    daily_pct: float | None = None
    if price and prev_close and prev_close > 0:
      daily_pct = round((float(price) - float(prev_close)) / float(prev_close) * 100, 2)

    from app.services.market_regime.indicator_helpers import count_trend_checks, trend_label_from_checks

    bull, bear = count_trend_checks(daily) if daily else (0, 0)
    trend = trend_label_from_checks(bull, bear) if daily else "Unavailable"

    return {
      "symbol": sym,
      "price": float(price) if price else None,
      "daily_pct": daily_pct,
      "trend_badge": trend,
      "risk_badge": self._risk_badge(daily),
      "available": price is not None or bool(daily),
      "daily_indicators": daily,
      "intraday_indicators": intraday,
      "analysis": analysis,
    }

  @staticmethod
  def _risk_badge(daily: dict[str, Any]) -> str:
    if not daily:
      return "Unknown"
    bb_u, bb_l, bb_m = daily.get("bb_upper"), daily.get("bb_lower"), daily.get("bb_mid")
    if bb_u and bb_l and bb_m and bb_m > 0:
      width = (bb_u - bb_l) / bb_m
      if width > 0.08:
        return "High"
      if width < 0.04:
        return "Low"
    atr = daily.get("atr14")
    close = daily.get("close")
    if atr and close and close > 0 and atr / close > 0.025:
      return "Elevated"
    return "Normal"

  def macro_stub(self, key: str) -> dict[str, Any]:
    """Placeholder for FRED / Finnhub / CBOE integrations."""
    return {
      "key": key,
      "value": None,
      "daily_pct": None,
      "available": False,
      "source": "unavailable",
    }

  def broker_status(self) -> str:
    try:
      ok, msg = self._broker.is_available()
      return msg if ok else f"Unavailable: {msg}"
    except Exception as exc:
      return f"Unavailable: {exc}"

  def analyzer_status(self) -> str:
    found = [s for s in INDEX_SYMBOLS if self.load_analyzer_snapshot(s)]
    if found:
      return f"Analyzer snapshots: {', '.join(found)}"
    return "No analyzer snapshots found — run QQQ Spread Analyzer"
