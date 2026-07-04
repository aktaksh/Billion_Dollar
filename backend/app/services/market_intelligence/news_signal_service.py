"""Per-symbol news signal aggregation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from news_intelligence.news_orchestrator import get_news_signal
from news_intelligence.news_repository import NewsRepository

from app.services.news_intelligence_api_service import _importance, _label_display, _score_0_to_100


class NewsSignalService:
    def __init__(self, repo: NewsRepository) -> None:
        self.repo = repo

    def signal_for_symbol(self, symbol: str, *, since_days: int = 7) -> dict[str, Any]:
        sym = symbol.strip().upper()
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

    def signals_for_watchlist(self, symbols: list[str]) -> list[dict[str, Any]]:
        return [self.signal_for_symbol(s) for s in symbols if s]
