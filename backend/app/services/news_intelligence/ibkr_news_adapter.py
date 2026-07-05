"""IBKR News Adapter — normalizes IBKR headlines into NewsItem schema."""

from __future__ import annotations

from datetime import UTC, datetime

from news_intelligence.news_models import NewsItem
from app.services.news_intelligence.ibkr_news_client import IbkrHeadline, IbkrNewsResult

SOURCE_QUALITY_WEIGHTS: dict[str, float] = {
    "SEC_EDGAR": 1.00,
    "DJ-N": 0.95,
    "DJ-RT": 0.90,
    "DJNL": 0.90,
    "BRFUPDN": 0.90,
    "BRFG": 0.85,
}


def clean_headline(headline: str) -> str:
    """Remove IBKR metadata tags like {A:800015:L:en} from headlines.

    Delegates to the shared `news_deduplicator.clean_headline` (which also
    strips wire-continuation markers and publisher suffixes) so all
    providers go through one headline-cleaning implementation.
    """
    from news_intelligence.news_deduplicator import clean_headline as _shared_clean_headline

    return _shared_clean_headline(headline)


def _parse_ibkr_timestamp(ts_str: str) -> datetime | None:
    """Parse IBKR timestamp formats: '2026-07-01 14:30:00' or '20260701 14:30:00'."""
    if not ts_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M:%S", "%Y%m%d-%H:%M:%S"):
        try:
            return datetime.strptime(ts_str.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def classify_ibkr_event(headline: str) -> str:
    """Classify event type from IBKR headline text.

    Delegates to the canonical 14-category classifier (`classify_event_category`)
    and maps down to the legacy lowercase value so `news_items.event_type`
    keeps its existing shape. This avoids maintaining a second, drifting
    keyword table alongside `news_relevance._CATEGORY_RULES`.
    """
    from news_intelligence.news_categories import to_legacy_event_type
    from news_intelligence.news_models import NewsItem
    from news_intelligence.news_relevance import classify_event_category

    stub = NewsItem(
        provider="IBKR",
        source="",
        symbol="",
        category="company_news",
        headline=headline,
        summary="",
        url="",
        published_at=None,
    )
    category = classify_event_category(stub)
    legacy = to_legacy_event_type(category)
    return legacy if legacy != "market_news" else "company_news"


def source_quality_weight(provider_code: str) -> float:
    """Return quality weight for an IBKR news provider."""
    return SOURCE_QUALITY_WEIGHTS.get(provider_code, 0.80)


def normalize_ibkr_headline(
    headline_obj: IbkrHeadline,
    symbol: str,
) -> NewsItem:
    """Convert a single IBKR headline into a normalized NewsItem."""
    clean_text = clean_headline(headline_obj.headline)
    published = _parse_ibkr_timestamp(headline_obj.timestamp)
    provider_code = headline_obj.provider_code

    return NewsItem(
        provider="IBKR",
        source=provider_code,
        symbol=symbol.upper(),
        symbols=[symbol.upper()],
        category="company_news",
        headline=clean_text,
        summary="",
        url="",
        published_at=published,
        event_type=classify_ibkr_event(clean_text),
        raw_json={
            "article_id": headline_obj.article_id,
            "provider_code": provider_code,
            "original_headline": headline_obj.headline,
            "timestamp_raw": headline_obj.timestamp,
            "source_quality_weight": source_quality_weight(provider_code),
        },
    )


def normalize_ibkr_result(result: IbkrNewsResult) -> list[NewsItem]:
    """Convert all headlines from an IbkrNewsResult into NewsItem list."""
    items: list[NewsItem] = []
    for h in result.headlines:
        if not h.headline.strip():
            continue
        items.append(normalize_ibkr_headline(h, result.symbol))
    return items


def deduplicate_ibkr_items(items: list[NewsItem]) -> list[NewsItem]:
    """Remove intra-batch duplicates by provider_code + article_id."""
    seen: set[str] = set()
    unique: list[NewsItem] = []
    for item in items:
        raw = item.raw_json or {}
        key = f"{raw.get('provider_code', '')}|{raw.get('article_id', '')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def apply_source_quality(items: list[NewsItem]) -> list[NewsItem]:
    """Boost relevance_score by source quality weight for IBKR items."""
    for item in items:
        if item.provider != "IBKR":
            continue
        raw = item.raw_json or {}
        weight = raw.get("source_quality_weight", 0.80)
        item.relevance_score = max(item.relevance_score, weight * 0.8)
    return items
