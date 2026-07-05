"""Canonical event categories for ticker-level news intelligence.

14 categories checked in this exact priority order by ``classify_event_category``.
Earlier categories win when multiple keyword sets match the same headline.
"""

from __future__ import annotations

CANONICAL_CATEGORIES: tuple[str, ...] = (
    "SEC_FILING",
    "LEGAL_REGULATORY",
    "EARNINGS",
    "GUIDANCE",
    "ANALYST_ACTION",
    "PRODUCT",
    "PARTNERSHIP",
    "M_AND_A",
    "INSIDER_ACTIVITY",
    "INSTITUTIONAL_OWNERSHIP",
    "MACRO",
    "INDUSTRY_SECTOR",
    "GENERAL_MARKET",
    "OTHER",
)

# Priority order == declaration order above; kept as an explicit tuple too so
# callers don't have to assume list ordering semantics of CANONICAL_CATEGORIES.
PRIORITY_ORDER: tuple[str, ...] = CANONICAL_CATEGORIES

IMPORTANCE_SCORES: dict[str, float] = {
    "SEC_FILING": 90,
    "GUIDANCE": 90,
    "LEGAL_REGULATORY": 85,
    "EARNINGS": 80,
    "M_AND_A": 80,
    "ANALYST_ACTION": 70,
    "PRODUCT": 65,
    "PARTNERSHIP": 65,
    "MACRO": 60,
    "INSIDER_ACTIVITY": 60,
    "INSTITUTIONAL_OWNERSHIP": 45,
    "INDUSTRY_SECTOR": 45,
    "GENERAL_MARKET": 20,
    "OTHER": 10,
}

# Maps each new canonical category down to the legacy lowercase snake_case
# `news_items.event_type` values so `_importance()`/`_critical_events()` and
# other legacy consumers keep working unchanged.
CANONICAL_TO_LEGACY: dict[str, str] = {
    "SEC_FILING": "sec_filing",
    "LEGAL_REGULATORY": "legal_regulatory",
    "EARNINGS": "earnings",
    "GUIDANCE": "guidance",
    "ANALYST_ACTION": "analyst_rating",
    "PRODUCT": "product",
    "PARTNERSHIP": "partnership",
    "M_AND_A": "merger_acquisition",
    "INSIDER_ACTIVITY": "insider",
    "INSTITUTIONAL_OWNERSHIP": "company_news",
    "MACRO": "macro",
    "INDUSTRY_SECTOR": "company_news",
    "GENERAL_MARKET": "market_news",
    "OTHER": "other",
}


def importance_score(category: str) -> float:
    return IMPORTANCE_SCORES.get(category, IMPORTANCE_SCORES["OTHER"])


def importance_label(score: float) -> str:
    """Bucket a 0-100 importance_score into Critical/High/Medium/Low (Part 8 filtering)."""
    if score >= 80:
        return "Critical"
    if score >= 60:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def to_legacy_event_type(category: str) -> str:
    return CANONICAL_TO_LEGACY.get(category, "other")
