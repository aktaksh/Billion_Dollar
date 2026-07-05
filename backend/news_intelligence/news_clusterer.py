"""Clusters deduped, enriched NewsItems into `news_events` rows (Part 6).

Grouping key is (symbol, canonical event_category); within a group, items are
merged into the same cluster when their headlines are similar enough. The
default similarity threshold is stricter (0.70); the looser 0.55 threshold is
only used when the two headlines also share the same source family (e.g.
both IBKR, both SEC) — never as a general default.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from news_intelligence.news_categories import importance_score
from news_intelligence.news_config import (
    CLUSTER_SIMILARITY_THRESHOLD,
    CLUSTER_SIMILARITY_THRESHOLD_SAME_FAMILY,
    PRIMARY_TICKER_MIN_FOR_INCLUSION,
    SOURCE_FAMILY,
)
from news_intelligence.news_deduplicator import normalize_headline
from news_intelligence.news_models import NewsItem

_EPOCH = datetime.fromtimestamp(0, tz=UTC)


def _source_family(item: NewsItem) -> str:
    return SOURCE_FAMILY.get(item.provider, item.provider)


def is_general_market_finnhub(item: NewsItem) -> bool:
    """Finnhub general market news is market-context only (Part 1 refinement)
    — excluded from clustering/ticker signals entirely so it can never
    become a top catalyst for any specific symbol."""
    return item.provider == "FINNHUB" and item.category == "market_news"


def target_symbol(item: NewsItem) -> str:
    """The symbol this item is clustered under — the resolved primary ticker
    if set, otherwise the item's originally-assigned symbol."""
    return item.resolved_symbol or item.symbol


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_headline(a), normalize_headline(b)).ratio()


class _ClusterBuilder:
    def __init__(self, symbol: str, category: str) -> None:
        self.symbol = symbol
        self.category = category
        self.items: list[NewsItem] = []

    def add(self, item: NewsItem) -> None:
        self.items.append(item)

    def matches(self, item: NewsItem) -> bool:
        for existing in self.items:
            same_family = _source_family(existing) == _source_family(item)
            threshold = (
                CLUSTER_SIMILARITY_THRESHOLD_SAME_FAMILY
                if same_family
                else CLUSTER_SIMILARITY_THRESHOLD
            )
            if _similarity(existing.headline, item.headline) >= threshold:
                return True
        return False

    def to_event_dict(self) -> dict[str, Any]:
        items = self.items
        best = max(items, key=lambda i: (i.primary_ticker_score, i.published_at or _EPOCH))
        times = [i.published_at for i in items if i.published_at]
        earliest = min(times) if times else None
        latest = max(times) if times else None
        sources = sorted({i.source or i.provider for i in items})
        article_ids = [i.id for i in items]

        weight_sum = sum(max(i.primary_ticker_score, 1) for i in items)
        sentiment_score = (
            sum(i.sentiment_score * max(i.primary_ticker_score, 1) for i in items) / weight_sum
            if weight_sum
            else 0.0
        )
        primary_ticker_score = max(i.primary_ticker_score for i in items)
        source_quality_score = max(i.source_quality for i in items)
        impact_score = max(items, key=lambda i: abs(i.impact_score_v2)).impact_score_v2

        n_sources = len(sources)
        if n_sources >= 3 or (n_sources >= 2 and primary_ticker_score >= 60):
            confidence = "High"
        elif n_sources >= 2 or primary_ticker_score >= 60:
            confidence = "Medium"
        else:
            confidence = "Low"

        now = datetime.now(UTC)
        return {
            "id": str(uuid.uuid4()),
            "cluster_id": f"{self.symbol}:{self.category}:{best.id[:8]}",
            "symbol": self.symbol,
            "primary_category": self.category,
            "subtype": None,
            "title": best.headline,
            "summary": best.summary or None,
            "source_count": n_sources,
            "sources_json": sources,
            "article_ids_json": article_ids,
            "earliest_time": earliest,
            "latest_time": latest,
            "sentiment_score": round(sentiment_score, 4),
            "importance_score": importance_score(self.category),
            "primary_ticker_score": primary_ticker_score,
            "source_quality_score": source_quality_score,
            "impact_score": impact_score,
            "confidence": confidence,
            "created_at": now,
            "updated_at": now,
        }


def cluster_events(items: list[NewsItem]) -> list[dict[str, Any]]:
    """Group enriched, deduped items into `news_events` cluster rows.

    Excludes Finnhub general-market items (context-only) and items below the
    Part 4 inclusion floor (`primary_ticker_score < 40`).
    """
    eligible = [
        i
        for i in items
        if not is_general_market_finnhub(i)
        and i.primary_ticker_score >= PRIMARY_TICKER_MIN_FOR_INCLUSION
        and target_symbol(i)
        and target_symbol(i) != "MARKET"
    ]

    groups: dict[tuple[str, str], list[_ClusterBuilder]] = {}
    for item in sorted(eligible, key=lambda i: i.primary_ticker_score, reverse=True):
        key = (target_symbol(item), item.event_category)
        builders = groups.setdefault(key, [])
        placed = False
        for builder in builders:
            if builder.matches(item):
                builder.add(item)
                placed = True
                break
        if not placed:
            new_builder = _ClusterBuilder(key[0], item.event_category)
            new_builder.add(item)
            builders.append(new_builder)

    events: list[dict[str, Any]] = []
    for builders in groups.values():
        for builder in builders:
            events.append(builder.to_event_dict())
    return events
