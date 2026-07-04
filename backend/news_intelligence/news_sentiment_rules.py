"""Rule-based sentiment scoring with Alpha Vantage override."""

from __future__ import annotations

from news_intelligence.news_models import NewsItem

POSITIVE_KEYWORDS = (
    "beat",
    "beats",
    "raise guidance",
    "raises guidance",
    "upgrade",
    "upgraded",
    "approval",
    "buyback",
    "record revenue",
    "strong demand",
    "partnership",
    "contract win",
    "accelerates",
    "outperform",
)

NEGATIVE_KEYWORDS = (
    "miss",
    "misses",
    "cut guidance",
    "cuts guidance",
    "downgrade",
    "downgraded",
    "investigation",
    "lawsuit",
    "probe",
    "weak demand",
    "layoffs",
    "margin pressure",
    "slows",
    "underperform",
    "regulatory risk",
)


def _count_keyword_hits(text: str, keywords: tuple[str, ...]) -> int:
    lower = text.lower()
    return sum(1 for kw in keywords if kw in lower)


def apply_av_sentiment(item: NewsItem) -> tuple[str, float]:
    score = item.av_sentiment_score
    if score is None:
        return "", 0.0
    if score > 0.15:
        return "bullish", 1.0
    if score < -0.15:
        return "bearish", -1.0
    return "neutral", 0.0


def apply_rule_sentiment(item: NewsItem) -> tuple[str, float]:
    text = f"{item.headline} {item.summary}"
    pos = _count_keyword_hits(text, POSITIVE_KEYWORDS)
    neg = _count_keyword_hits(text, NEGATIVE_KEYWORDS)

    if pos > neg and pos > 0:
        return "bullish", 1.0
    if neg > pos and neg > 0:
        return "bearish", -1.0
    if neg > 0 and neg == pos:
        return "bearish", -1.0
    return "neutral", 0.0


def score_sentiment(item: NewsItem) -> NewsItem:
    if item.provider == "SEC_EDGAR":
        item.sentiment_label = "neutral"
        item.sentiment_score = 0.0
        return item

    if item.av_sentiment_score is not None:
        label, score = apply_av_sentiment(item)
        if label:
            item.sentiment_label = label
            item.sentiment_score = score
            return item

    label, score = apply_rule_sentiment(item)
    item.sentiment_label = label
    item.sentiment_score = score
    return item
