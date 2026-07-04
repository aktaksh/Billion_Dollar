"""Headline deduplication by URL and fuzzy headline similarity."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher

from news_intelligence.news_config import DEDUP_WINDOW_HOURS, HEADLINE_SIMILARITY_THRESHOLD
from news_intelligence.news_models import NewsItem
from news_intelligence.news_repository import NewsRepository

PUBLISHER_SUFFIXES = re.compile(
    r"\s*[-|–]\s*(reuters|bloomberg|cnbc|marketwatch|yahoo finance|seeking alpha|the wall street journal|wsj|ap news|associated press)\s*$",
    re.IGNORECASE,
)
PUNCTUATION_RE = re.compile(r"[^\w\s]")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_headline(headline: str) -> str:
    text = headline.lower().strip()
    text = PUBLISHER_SUFFIXES.sub("", text)
    text = PUNCTUATION_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def is_similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return SequenceMatcher(None, a, b).ratio() > HEADLINE_SIMILARITY_THRESHOLD


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def deduplicate_items(
    items: list[NewsItem],
    repo: NewsRepository,
) -> tuple[list[NewsItem], int]:
    unique: list[NewsItem] = []
    removed = 0
    seen_urls: set[str] = set()
    seen_headlines: list[tuple[str, object]] = []  # (normalized, published_at)

    window_start = datetime.now(UTC) - timedelta(hours=DEDUP_WINDOW_HOURS)
    db_recent = repo.find_recent_items(window_start)
    for db_item in db_recent:
        if db_item.url:
            seen_urls.add(db_item.url)
        norm = normalize_headline(db_item.headline)
        if norm:
            seen_headlines.append((norm, _ensure_utc(db_item.published_at)))

    for item in items:
        url = item.url or ""
        if url:
            if url in seen_urls or repo.url_exists(url):
                removed += 1
                continue
            seen_urls.add(url)

        norm = normalize_headline(item.headline)
        if norm:
            pub = _ensure_utc(item.published_at)
            is_dup = False
            for prev_norm, prev_pub in seen_headlines:
                if pub and prev_pub:
                    delta = abs((pub - prev_pub).total_seconds())
                    if delta > DEDUP_WINDOW_HOURS * 3600:
                        continue
                if is_similar(norm, prev_norm):
                    is_dup = True
                    break
            if is_dup:
                removed += 1
                continue
            seen_headlines.append((norm, pub))

        unique.append(item)

    return unique, removed
