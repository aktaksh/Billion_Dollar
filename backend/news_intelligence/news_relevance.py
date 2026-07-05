"""Relevance scoring, event classification, and impact calculation.

Two generations of logic live here side by side:
  - Legacy: `classify_event_type` + `compute_relevance` + `compute_impact`
    populate `news_items` columns exactly as before (small ~[-1, 1] impact
    scale) so existing dashboards/consumers are unaffected.
  - New (Part 5/7): `classify_event_category` (14 canonical categories) +
    `compute_impact_score` (-100..100 scale) feed the new `news_events` /
    `ticker_news_signals` tables consumed by the redesigned ticker-level
    intelligence layer.
"""

from __future__ import annotations

from datetime import UTC, datetime

from news_intelligence.news_categories import (
    IMPORTANCE_SCORES,
    to_legacy_event_type,
)
from news_intelligence.news_config import (
    QQQ_WEIGHT_PRIORITY,
    RECENCY_DECAY_WINDOW_HOURS,
    RECENCY_FULL_WEIGHT_HOURS,
    RECENCY_MIN_WEIGHT,
    SOURCE_QUALITY_WEIGHTS,
)
from news_intelligence.news_models import NewsItem

EVENT_WEIGHTS: dict[str, float] = {
    "earnings": 1.0,
    "guidance": 1.0,
    "legal_regulatory": 0.9,
    "analyst_rating": 0.6,
    "filing": 0.7,
    "insider": 0.7,
    "macro": 0.8,
    "market_news": 0.5,
    "company_news": 0.5,
    "other": 0.3,
    "product": 0.5,
    "partnership": 0.5,
    "merger_acquisition": 0.8,
    "dividend_buyback": 0.6,
    "sec_filing": 0.7,
}

QQQ_TOP_SET = frozenset(QQQ_WEIGHT_PRIORITY)

IBKR_EVENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("sec_filing", ("files 8k", "files 10q", "files 10k", "files 8-k", "files 10-q", "files 10-k")),
    ("analyst_rating", ("upgraded", "downgraded", "reiterated", "target", "initiated", "maintains")),
    ("earnings", ("earnings", "results", "revenue", "eps", "quarterly")),
    ("guidance", ("guidance", "outlook", "raises", "lowers", "forecast")),
    ("partnership", ("partners", "partnership", "collaboration", "contract")),
    ("product", ("launches", "unveils", "announces", "introduces")),
    ("dividend_buyback", ("dividend", "buyback", "repurchase")),
    ("merger_acquisition", ("acquisition", "acquire", "merger", "takeover")),
    ("legal_regulatory", ("lawsuit", "investigation", "sec charges", "regulatory")),
]


def classify_event_type(item: NewsItem) -> str:
    """Legacy lowercase snake_case classifier — now a thin shim over the new
    canonical classifier so `news_items.event_type` / `_importance()` /
    `_critical_events()` keep working unchanged."""
    category = classify_event_category(item)
    return to_legacy_event_type(category)


# --- New canonical classifier (Part 5) ---------------------------------

_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "SEC_FILING",
        (
            "files 8-k", "files 8k", "files 10-q", "files 10q", "files 10-k", "files 10k",
            "sec filing", "files s-1", "files s-3", "form 8-k", "form 10-q", "form 10-k",
        ),
    ),
    (
        "LEGAL_REGULATORY",
        (
            "lawsuit", "sues", "sued", "investigation", "probe", "sec charges", "sec charged",
            "regulatory", "settlement", "fine of", "class action", "subpoena", "antitrust",
        ),
    ),
    (
        "EARNINGS",
        (
            "beats eps", "misses eps", "beats revenue estimates", "misses revenue estimates",
            "beats earnings estimates", "misses earnings estimates", "beats estimates",
            "misses estimates", "quarterly earnings", "reports quarterly", "earnings call",
            "earnings report", "q1 earnings", "q2 earnings", "q3 earnings", "q4 earnings",
            "reports record revenue", "reports revenue of", "eps of $",
        ),
    ),
    (
        "GUIDANCE",
        ("raises guidance", "lowers guidance", "cuts guidance", "guidance", "outlook", "raises forecast", "lowers forecast"),
    ),
    (
        "ANALYST_ACTION",
        (
            "upgraded", "downgraded", "upgrades", "downgrades", "price target", "initiated coverage",
            "initiates coverage", "reiterates", "reiterated", "maintains rating", "analyst",
        ),
    ),
    (
        "PRODUCT",
        ("launches", "unveils", "announces new", "introduces", "new chip", "product launch", "rolls out"),
    ),
    (
        "PARTNERSHIP",
        ("partners with", "partnership", "collaboration", "contract win", "joint venture", "signs deal with"),
    ),
    (
        "M_AND_A",
        ("merger", "acquisition", "acquire", "acquires", "to acquire", "takeover", "buyout"),
    ),
    (
        "INSIDER_ACTIVITY",
        ("insider", "form 4", "director sells", "director buys", "ceo sells", "ceo buys", "insider sells", "insider buys"),
    ),
    (
        "INSTITUTIONAL_OWNERSHIP",
        (
            "stake in", "holds shares", "13f", "ownership stake", "trims stake", "boosts stake",
            "position in", "raises stake", "cuts stake",
        ),
    ),
    (
        "MACRO",
        ("fed ", "fomc", "cpi", "inflation", "jobs report", "gdp", "interest rate", "federal reserve", "treasury yield"),
    ),
    (
        "INDUSTRY_SECTOR",
        ("sector", "industry-wide", "industry wide", "chipmakers", "peers", "semiconductor stocks", "tech stocks"),
    ),
    (
        "GENERAL_MARKET",
        ("dow jones", "s&p 500", "s&p500", "nasdaq futures", "wall street", "stock market today", "futures point"),
    ),
]


def classify_event_category(item: NewsItem) -> str:
    """Classify `item` into one of the 14 canonical categories, checked in
    the exact spec priority order. Does NOT rely on the mere presence of the
    word "earnings" alone — EARNINGS requires a stronger contextual phrase
    (see `_CATEGORY_RULES`)."""
    if item.provider == "SEC_EDGAR":
        form = (item.raw_json or {}).get("form_type", "")
        if form == "4":
            return "INSIDER_ACTIVITY"
        return "SEC_FILING"

    text = f"{item.headline} {item.summary}".lower()

    for category, keywords in _CATEGORY_RULES:
        if any(kw in text for kw in keywords):
            return category

    if item.category == "market_news" or item.symbol == "MARKET":
        return "GENERAL_MARKET"

    return "OTHER"


def compute_relevance(item: NewsItem, primary_symbol: str | None = None) -> float:
    if item.provider == "SEC_EDGAR":
        return 1.0

    score = 0.0
    sym = (primary_symbol or item.symbol or "").upper()
    text_h = item.headline.lower()
    text_s = item.summary.lower()

    if sym and sym in (item.symbols or [item.symbol]):
        score += 0.6
    elif sym and sym != "MARKET":
        if sym.lower() in text_h or sym in item.headline.upper():
            score += 0.3
        if sym.lower() in text_s:
            score += 0.2

    if item.symbol in QQQ_TOP_SET or sym in QQQ_TOP_SET:
        score += 0.1

    if item.category == "market_news" or item.symbol == "MARKET":
        score += 0.2

    # Apply source quality weight for IBKR providers
    if item.provider == "IBKR":
        provider_code = (item.raw_json or {}).get("provider_code", "")
        quality = SOURCE_QUALITY_WEIGHTS.get(f"IBKR_{provider_code}", 0.80)
        score = max(score, quality * 0.75)

    if item.relevance_score > 0:
        score = max(score, item.relevance_score)

    return min(1.0, round(score, 3))


def compute_impact(sentiment_score: float, relevance_score: float, event_type: str) -> float:
    """Legacy impact score (~[-1, 1] scale). Unchanged — still populates
    `news_items.impact_score` for backward compatibility."""
    weight = EVENT_WEIGHTS.get(event_type, EVENT_WEIGHTS["other"])
    return round(sentiment_score * relevance_score * weight, 4)


def enrich_item(item: NewsItem, primary_symbol: str | None = None) -> NewsItem:
    item.event_type = classify_event_type(item)
    item.relevance_score = compute_relevance(item, primary_symbol)
    item.impact_score = compute_impact(item.sentiment_score, item.relevance_score, item.event_type)
    return item


# --- New impact-score formula (Part 7) ---------------------------------


def source_quality_weight(item: NewsItem) -> float:
    """Resolve the source-quality weight for `item` per the provider weight
    table (SEC=1.00, IBKR DJ-N=0.95 etc, Finnhub=0.70, AV=0.65)."""
    if item.provider == "SEC_EDGAR":
        return SOURCE_QUALITY_WEIGHTS.get("SEC_EDGAR", 1.00)
    if item.provider == "IBKR":
        provider_code = (item.raw_json or {}).get("provider_code", "")
        return SOURCE_QUALITY_WEIGHTS.get(f"IBKR_{provider_code}", 0.80)
    if item.provider == "FINNHUB":
        return SOURCE_QUALITY_WEIGHTS.get("FINNHUB", 0.70)
    if item.provider == "ALPHA_VANTAGE":
        return SOURCE_QUALITY_WEIGHTS.get("ALPHA_VANTAGE", 0.65)
    return 0.60


def recency_weight(published_at: datetime | None, *, now: datetime | None = None) -> float:
    """Linear decay from 1.0 (<=24h old) to a 0.3 floor at 7 days."""
    if published_at is None:
        return RECENCY_MIN_WEIGHT
    ref = now or datetime.now(UTC)
    pub = published_at if published_at.tzinfo else published_at.replace(tzinfo=UTC)
    hours_old = max(0.0, (ref - pub).total_seconds() / 3600.0)
    if hours_old <= RECENCY_FULL_WEIGHT_HOURS:
        return 1.0
    decay_span = RECENCY_DECAY_WINDOW_HOURS - RECENCY_FULL_WEIGHT_HOURS
    if decay_span <= 0:
        return RECENCY_MIN_WEIGHT
    fraction = min(1.0, (hours_old - RECENCY_FULL_WEIGHT_HOURS) / decay_span)
    weight = 1.0 - fraction * (1.0 - RECENCY_MIN_WEIGHT)
    return max(RECENCY_MIN_WEIGHT, weight)


def compute_impact_score(
    *,
    sentiment_score: float,
    primary_ticker_score: float,
    category: str,
    source_quality: float,
    published_at: datetime | None,
    now: datetime | None = None,
) -> float:
    """impact_score = sentiment * (primary_ticker/100) * (importance/100)
    * source_quality * recency, scaled to [-100, 100]."""
    importance = IMPORTANCE_SCORES.get(category, IMPORTANCE_SCORES["OTHER"])
    recency = recency_weight(published_at, now=now)
    raw = (
        sentiment_score
        * (primary_ticker_score / 100.0)
        * (importance / 100.0)
        * source_quality
        * recency
    )
    return round(max(-100.0, min(100.0, raw * 100.0)), 2)
