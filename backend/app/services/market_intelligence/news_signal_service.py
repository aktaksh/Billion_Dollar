"""Per-symbol news signal aggregation.

`signal_for_symbol` reads from the new `ticker_news_signals` table first
(ticker-level intelligence, Parts 6/7/11); if no row exists yet for the
symbol it falls back to the legacy per-item aggregation exactly as before.
The returned dict shape is unchanged either way so downstream consumers
(Opportunity Scanner, Market Intelligence watchlist, TDE) never need to
know which path produced it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from news_intelligence.news_orchestrator import get_news_signal
from news_intelligence.news_repository import NewsRepository

from app.services.news_intelligence_api_service import _importance, _label_display, _score_0_to_100

NO_CATALYST_MESSAGE = "No high-quality ticker-specific catalyst"


class NewsSignalService:
    def __init__(self, repo: NewsRepository) -> None:
        self.repo = repo

    def _ticker_signal_row(self, symbol: str) -> dict[str, Any] | None:
        try:
            from app.repositories.news_events_repository import NewsEventsRepository

            return NewsEventsRepository(self.repo.engine).get_ticker_signal(symbol)
        except Exception:
            return None

    def _from_ticker_signal(self, row: dict[str, Any]) -> dict[str, Any]:
        sym = row["symbol"]
        net = float(row.get("net_impact_score") or 0.0)
        news_score = max(0.0, min(100.0, 50.0 + net / 2.0))
        total = int(row.get("bullish_count") or 0) + int(row.get("bearish_count") or 0) + int(row.get("neutral_count") or 0)

        last_updated = row.get("last_updated")
        last = last_updated.isoformat() if hasattr(last_updated, "isoformat") else last_updated
        freshness = None
        if last_updated is not None and hasattr(last_updated, "tzinfo"):
            lu = last_updated if last_updated.tzinfo else last_updated.replace(tzinfo=UTC)
            freshness = max(0, int((datetime.now(UTC) - lu).total_seconds() // 60))

        top_catalyst = row.get("top_catalyst")
        top_risk = row.get("top_risk")

        return {
            "symbol": sym,
            "label": row.get("news_bias") or "Neutral",
            "news_score_0_to_100": round(news_score),
            "sentiment_score": round(net / 100.0, 4),
            "impact_score": row.get("catalyst_strength_score", 0.0),
            "confidence": row.get("confidence") or ("High" if total >= 12 else "Medium" if total >= 4 else "Low"),
            "top_catalyst": top_catalyst,
            "top_risk_event": top_risk,
            "critical_event_count": 0,
            "bullish_count": row.get("bullish_count", 0),
            "bearish_count": row.get("bearish_count", 0),
            "neutral_count": row.get("neutral_count", 0),
            "last_updated": last,
            "data_freshness_minutes": freshness,
            "news_quality_score": row.get("news_quality_score", 0.0),
            "catalyst_strength_score": row.get("catalyst_strength_score", 0.0),
            "llm_summary": row.get("llm_summary") or (NO_CATALYST_MESSAGE if not top_catalyst else None),
        }

    def _legacy_signal_for_symbol(self, sym: str, *, since_days: int) -> dict[str, Any]:
        sig = get_news_signal(sym, since_days=since_days, repo=self.repo)
        items = self.repo.query_for_symbol(sym, since_days=since_days)
        critical = sum(1 for i in items if _importance(i) == "Critical")
        top_risk = next(
            (i.headline for i in items if i.sentiment_label == "bearish" and _importance(i) in ("Critical", "High")),
            None,
        )
        if not top_risk and sig.major_risk_events:
            top_risk = sig.major_risk_events[0]

        last = sig.last_updated.isoformat() if sig.last_updated else None
        freshness = None
        if sig.last_updated:
            lu = sig.last_updated if sig.last_updated.tzinfo else sig.last_updated.replace(tzinfo=UTC)
            freshness = max(0, int((datetime.now(UTC) - lu).total_seconds() // 60))

        return {
            "symbol": sym,
            "label": _label_display(sig.news_sentiment_label),
            "news_score_0_to_100": _score_0_to_100(sig.news_sentiment_score, sig.news_sentiment_label),
            "sentiment_score": sig.news_sentiment_score,
            "impact_score": sig.news_impact_score,
            "confidence": "High" if sig.bullish_count + sig.bearish_count + sig.neutral_count >= 12 else (
                "Medium" if sig.bullish_count + sig.bearish_count + sig.neutral_count >= 4 else "Low"
            ),
            "top_catalyst": sig.top_positive_headline or sig.top_negative_headline,
            "top_risk_event": top_risk,
            "critical_event_count": critical,
            "bullish_count": sig.bullish_count,
            "bearish_count": sig.bearish_count,
            "neutral_count": sig.neutral_count,
            "last_updated": last,
            "data_freshness_minutes": freshness,
        }

    def signal_for_symbol(self, symbol: str, *, since_days: int = 7) -> dict[str, Any]:
        sym = symbol.strip().upper()
        row = self._ticker_signal_row(sym)
        if row:
            return self._from_ticker_signal(row)
        return self._legacy_signal_for_symbol(sym, since_days=since_days)

    def signals_for_watchlist(self, symbols: list[str]) -> list[dict[str, Any]]:
        return [self.signal_for_symbol(s) for s in symbols if s]
