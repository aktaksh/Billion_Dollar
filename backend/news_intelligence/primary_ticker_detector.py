"""Primary ticker detection — how strongly is `target_symbol` the real subject
of a given news item? Score 0-100, per architecture Part 4."""

from __future__ import annotations

import re

from news_intelligence.news_config import BROAD_MARKET_KEYWORDS, SECTOR_KEYWORDS
from news_intelligence.news_models import NewsItem
from news_intelligence.ticker_registry import TickerRegistry, get_default_registry


def _word_in(text: str, needle: str) -> bool:
    if not text or not needle:
        return False
    return re.search(rf"\b{re.escape(needle)}\b", text, re.IGNORECASE) is not None


def _name_in(text: str, name: str | None) -> bool:
    if not text or not name or len(name) < 2:
        return False
    return name.lower() in text.lower()


def compute_primary_ticker_score(
    item: NewsItem,
    target_symbol: str,
    company_name: str | None = None,
    registry: TickerRegistry | None = None,
) -> int:
    """Additive-then-capped score (0-100) of how confidently `item` is
    primarily about `target_symbol`."""
    target = target_symbol.strip().upper()
    reg = registry or get_default_registry()
    company = company_name or reg.short_name(target) or reg.company_name(target)

    headline = item.headline or ""
    summary = item.summary or ""
    combined = f"{headline} {summary}"
    first_150 = combined[:150]

    ticker_in_headline = _word_in(headline, target)
    company_in_headline = _name_in(headline, company)
    ticker_in_150 = _word_in(first_150, target)
    company_in_150 = _name_in(first_150, company)

    score = 0

    if ticker_in_headline or company_in_headline:
        score += 50
    elif ticker_in_150 or company_in_150:
        score += 30

    # Exact provider metadata primary symbol: the item was fetched/normalized
    # specifically for this symbol (Finnhub company-news request symbol,
    # IBKR-resolved conId lookup, SEC filing symbol) rather than merely
    # mentioning it in a broader feed.
    is_primary_fetch = (item.symbol or "").strip().upper() == target
    if is_primary_fetch:
        score += 40

    symbols_list = [s.strip().upper() for s in (item.symbols or [])]
    ticker_only_in_related = (
        target in symbols_list
        and not is_primary_fetch
        and not ticker_in_headline
        and not company_in_headline
    )
    if ticker_only_in_related:
        score += 10

    score = min(100, score)

    text_lower = combined.lower()
    if any(kw in text_lower for kw in BROAD_MARKET_KEYWORDS):
        score = min(score, 25)
    elif any(kw in text_lower for kw in SECTOR_KEYWORDS):
        score = min(score, 60)

    if not (ticker_in_headline or company_in_headline):
        other = reg.find_company_mentioned(headline, exclude=target)
        if other:
            score = min(score, 30)

    return max(0, min(100, score))


def resolve_primary_symbol(
    item: NewsItem,
    registry: TickerRegistry | None = None,
) -> tuple[str, int]:
    """Pick whichever candidate symbol (`item.symbol` plus `item.symbols`)
    this item is most likely primarily about, e.g. a Finnhub/AV item fetched
    under NVDA's query but whose headline is really "Palantir upgraded to
    Buy" should resolve to PLTR, not NVDA. Returns (symbol, score)."""
    reg = registry or get_default_registry()
    candidates: list[str] = []
    seen: set[str] = set()
    for cand in [item.symbol, *(item.symbols or [])]:
        c = (cand or "").strip().upper()
        if c and c != "MARKET" and c not in seen:
            seen.add(c)
            candidates.append(c)

    if not candidates:
        return (item.symbol or "MARKET"), 0

    best_symbol = candidates[0]
    best_score = -1
    for cand in candidates:
        score = compute_primary_ticker_score(item, cand, registry=reg)
        if score > best_score:
            best_score = score
            best_symbol = cand
    return best_symbol, best_score
