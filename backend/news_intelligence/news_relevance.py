"""Relevance scoring, event classification, and impact calculation."""

from __future__ import annotations

import re

from news_intelligence.news_config import QQQ_WEIGHT_PRIORITY, SOURCE_QUALITY_WEIGHTS
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
    if item.provider == "SEC_EDGAR":
        form = (item.raw_json or {}).get("form_type", "")
        if form == "4":
            return "insider"
        if form == "8-K":
            return "legal_regulatory"
        return "filing"

    text = f"{item.headline} {item.summary}".lower()

    # IBKR-specific rules (higher priority for known patterns)
    if item.provider == "IBKR":
        for event_type, keywords in IBKR_EVENT_RULES:
            if any(k in text for k in keywords):
                return event_type

    if item.category == "market_news" or item.symbol == "MARKET":
        if any(k in text for k in ("fed", "fomc", "cpi", "inflation", "jobs report", "gdp")):
            return "macro"
        return "market_news"

    rules: list[tuple[str, tuple[str, ...]]] = [
        ("earnings", ("earnings", "eps", "quarterly results", "q1 ", "q2 ", "q3 ", "q4 ")),
        ("guidance", ("guidance", "outlook", "forecast")),
        ("analyst_rating", ("upgrade", "downgrade", "price target", "analyst")),
        ("legal_regulatory", ("lawsuit", "investigation", "probe", "sec ", "regulatory")),
        ("merger_acquisition", ("merger", "acquisition", "acquire", "takeover")),
        ("dividend_buyback", ("dividend", "buyback", "repurchase")),
        ("partnership", ("partnership", "collaboration", "contract win")),
        ("product", ("launch", "unveil", "product", "chip")),
        ("insider", ("insider", "form 4")),
    ]
    for event_type, keywords in rules:
        if any(k in text for k in keywords):
            return event_type

    if item.category == "company_news":
        return "company_news"
    return "other"


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
    weight = EVENT_WEIGHTS.get(event_type, EVENT_WEIGHTS["other"])
    return round(sentiment_score * relevance_score * weight, 4)


def enrich_item(item: NewsItem, primary_symbol: str | None = None) -> NewsItem:
    item.event_type = classify_event_type(item)
    item.relevance_score = compute_relevance(item, primary_symbol)
    item.impact_score = compute_impact(item.sentiment_score, item.relevance_score, item.event_type)
    return item
