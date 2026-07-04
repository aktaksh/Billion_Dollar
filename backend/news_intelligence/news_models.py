"""Normalized news data models and provider-specific normalizers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_unix_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        ts = int(value)
        if ts > 1_000_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) == 8 and value.isdigit():
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class NewsItem:
    provider: str
    source: str
    symbol: str
    category: str
    headline: str
    summary: str
    url: str
    published_at: datetime | None
    sentiment_label: str = "neutral"
    sentiment_score: float = 0.0
    relevance_score: float = 0.0
    impact_score: float = 0.0
    event_type: str = "other"
    symbols: list[str] = field(default_factory=list)
    raw_json: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=_new_id)
    created_at: datetime = field(default_factory=_now)
    av_sentiment_score: float | None = None


@dataclass
class FetchLog:
    provider: str
    status: str
    request_type: str
    symbols_requested: list[str] = field(default_factory=list)
    items_fetched: int = 0
    items_saved: int = 0
    duplicates_removed: int = 0
    error_message: str | None = None
    refresh_mode: str | None = None
    id: str = field(default_factory=_new_id)
    created_at: datetime = field(default_factory=_now)


@dataclass
class NewsPipelineSummary:
    total_fetched: int = 0
    total_saved: int = 0
    duplicates_removed: int = 0
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    top_positive_items: list[str] = field(default_factory=list)
    top_negative_items: list[str] = field(default_factory=list)
    top_symbols: list[str] = field(default_factory=list)
    provider_errors: list[str] = field(default_factory=list)


@dataclass
class NewsSignal:
    symbol: str
    news_sentiment_label: str
    news_sentiment_score: float
    news_impact_score: float
    bullish_count: int
    bearish_count: int
    neutral_count: int
    top_positive_headline: str | None
    top_negative_headline: str | None
    major_risk_events: list[str]
    last_updated: datetime | None


def normalize_finnhub_market(raw: dict[str, Any]) -> NewsItem:
    related = raw.get("related") or ""
    symbols = [s.strip().upper() for s in related.split(",") if s.strip()] if related else []
    return NewsItem(
        provider="FINNHUB",
        source=raw.get("source") or "Finnhub",
        symbol=symbols[0] if symbols else "MARKET",
        symbols=symbols,
        category="market_news",
        headline=raw.get("headline") or "",
        summary=raw.get("summary") or "",
        url=raw.get("url") or "",
        published_at=_parse_unix_ts(raw.get("datetime")),
        event_type="market_news",
        raw_json=raw,
    )


def normalize_finnhub_company(raw: dict[str, Any], symbol: str) -> NewsItem:
    sym = symbol.strip().upper()
    related = raw.get("related") or sym
    symbols = [s.strip().upper() for s in related.split(",") if s.strip()] if related else [sym]
    if sym not in symbols:
        symbols.insert(0, sym)
    return NewsItem(
        provider="FINNHUB",
        source=raw.get("source") or "Finnhub",
        symbol=sym,
        symbols=symbols,
        category="company_news",
        headline=raw.get("headline") or "",
        summary=raw.get("summary") or "",
        url=raw.get("url") or "",
        published_at=_parse_unix_ts(raw.get("datetime")),
        event_type="company_news",
        raw_json=raw,
    )


def normalize_alpha_vantage(raw: dict[str, Any]) -> NewsItem:
    tickers = raw.get("ticker_sentiment") or []
    symbols = [str(t.get("ticker", "")).upper() for t in tickers if t.get("ticker")]
    primary = symbols[0] if symbols else "MARKET"
    av_score = raw.get("overall_sentiment_score")
    try:
        av_score_f = float(av_score) if av_score is not None else None
    except (TypeError, ValueError):
        av_score_f = None

    relevance = 0.0
    if tickers:
        try:
            relevance = max(float(t.get("relevance_score", 0) or 0) for t in tickers)
        except (TypeError, ValueError):
            relevance = 0.0

    return NewsItem(
        provider="ALPHA_VANTAGE",
        source=raw.get("source") or "Alpha Vantage",
        symbol=primary,
        symbols=symbols,
        category="company_news",
        headline=raw.get("title") or "",
        summary=raw.get("summary") or "",
        url=raw.get("url") or "",
        published_at=_parse_iso_date(raw.get("time_published")),
        event_type="company_news",
        relevance_score=min(1.0, relevance),
        av_sentiment_score=av_score_f,
        raw_json=raw,
    )


def normalize_sec_filing(
    *,
    symbol: str,
    form_type: str,
    filing_date: str,
    accession: str,
    primary_document: str,
    cik: str,
    description: str = "",
) -> NewsItem:
    sym = symbol.strip().upper()
    cik_int = str(int(cik))  # strip leading zeros for URL path
    accession_clean = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_clean}/{primary_document}"

    event_type = "filing"
    if form_type == "4":
        event_type = "insider"
    elif form_type == "8-K":
        event_type = "legal_regulatory"

    return NewsItem(
        provider="SEC_EDGAR",
        source="SEC",
        symbol=sym,
        symbols=[sym],
        category="filing",
        headline=f"{sym} filed {form_type}",
        summary=description or f"SEC {form_type} filing for {sym}",
        url=url,
        published_at=_parse_iso_date(filing_date),
        sentiment_label="neutral",
        sentiment_score=0.0,
        relevance_score=1.0,
        event_type=event_type,
        raw_json={
            "form_type": form_type,
            "filing_date": filing_date,
            "accession": accession,
            "primary_document": primary_document,
            "cik": cik,
        },
    )
