"""News pipeline orchestration and signal aggregation."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from news_intelligence.alpha_vantage_client import (
    AlphaVantageClient,
    AlphaVantageError,
    AlphaVantageRateLimitError,
)
from news_intelligence.finnhub_client import (
    FinnhubClient,
    FinnhubError,
)
from news_intelligence.news_config import (
    ALPHA_VANTAGE_MAX_TICKERS,
    DEFAULT_PIPELINE_SYMBOLS,
    ETF_SYMBOLS,
    QQQ_WEIGHT_PRIORITY,
    NewsConfig,
    load_config,
)
from news_intelligence.news_deduplicator import deduplicate_items
from news_intelligence.news_models import (
    FetchLog,
    NewsItem,
    NewsPipelineSummary,
    NewsSignal,
    normalize_alpha_vantage,
    normalize_finnhub_company,
    normalize_finnhub_market,
    normalize_sec_filing,
)
from news_intelligence.news_relevance import enrich_item
from news_intelligence.news_repository import NewsRepository, get_repository
from news_intelligence.news_sentiment_rules import score_sentiment
from news_intelligence.sec_edgar_client import SecEdgarClient, SecEdgarError

logger = logging.getLogger(__name__)


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _av_priority_symbols(symbols: list[str]) -> list[str]:
    sym_set = {s.upper() for s in symbols}
    ordered = [s for s in QQQ_WEIGHT_PRIORITY if s in sym_set]
    for s in symbols:
        su = s.upper()
        if su not in ordered and su not in ETF_SYMBOLS:
            ordered.append(su)
    return ordered[:ALPHA_VANTAGE_MAX_TICKERS]


def _process_items(items: list[NewsItem]) -> list[NewsItem]:
    out: list[NewsItem] = []
    for item in items:
        score_sentiment(item)
        enrich_item(item, item.symbol if item.symbol != "MARKET" else None)
        out.append(item)
    return out


def run_news_pipeline(
    symbols: list[str] | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    *,
    config: NewsConfig | None = None,
    repo: NewsRepository | None = None,
    ibkr_news_client: Any | None = None,
    max_ibkr_symbols: int = 5,
) -> NewsPipelineSummary:
    cfg = config or load_config()
    repository = repo or get_repository()
    syms = [s.upper() for s in (symbols or DEFAULT_PIPELINE_SYMBOLS)]
    to_dt = to_date or datetime.now(UTC)
    from_dt = from_date or (to_dt - timedelta(days=7))
    from_s, to_s = _date_str(from_dt), _date_str(to_dt)

    summary = NewsPipelineSummary()
    all_items: list[NewsItem] = []

    # Step 0: IBKR News (optional, highest priority)
    if ibkr_news_client is not None:
        try:
            from app.services.news_intelligence.ibkr_news_adapter import (
                deduplicate_ibkr_items,
                normalize_ibkr_result,
            )

            ibkr_available, ibkr_msg = ibkr_news_client.is_available()
            if ibkr_available:
                stock_syms = [s for s in syms if s not in ETF_SYMBOLS]
                ibkr_results = ibkr_news_client.fetch_for_symbols(
                    stock_syms,
                    max_symbols=max_ibkr_symbols,
                    lookback_days=10,
                    max_headlines=20,
                )
                ibkr_items: list[NewsItem] = []
                ibkr_errors: list[str] = []
                for res in ibkr_results:
                    if res.error:
                        ibkr_errors.append(f"IBKR {res.symbol}: {res.error}")
                    else:
                        ibkr_items.extend(normalize_ibkr_result(res))

                ibkr_items = deduplicate_ibkr_items(ibkr_items)
                all_items.extend(ibkr_items)
                summary.total_fetched += len(ibkr_items)

                repository.insert_fetch_log(FetchLog(
                    provider="IBKR",
                    status="ok" if not ibkr_errors else "partial",
                    request_type="historical_news",
                    symbols_requested=stock_syms[:max_ibkr_symbols],
                    items_fetched=len(ibkr_items),
                    error_message="; ".join(ibkr_errors) if ibkr_errors else None,
                ))
                if ibkr_errors:
                    summary.provider_errors.extend(ibkr_errors)
                logger.info("IBKR News: %d items fetched for %d symbols", len(ibkr_items), min(len(stock_syms), max_ibkr_symbols))
            else:
                logger.info("IBKR News unavailable: %s — falling back to other providers", ibkr_msg)
                repository.insert_fetch_log(FetchLog(
                    provider="IBKR",
                    status="unavailable",
                    request_type="historical_news",
                    error_message=ibkr_msg,
                ))
        except Exception as exc:
            logger.warning("IBKR News pipeline error: %s — continuing without IBKR", exc)
            summary.provider_errors.append(f"IBKR: {exc}")
            repository.insert_fetch_log(FetchLog(
                provider="IBKR",
                status="error",
                request_type="historical_news",
                error_message=str(exc),
            ))

    finnhub = FinnhubClient(cfg)
    sec = SecEdgarClient(cfg)
    av: AlphaVantageClient | None = None
    if cfg.has_alpha_vantage:
        try:
            av = AlphaVantageClient(cfg)
        except AlphaVantageError as exc:
            summary.provider_errors.append(f"Alpha Vantage init: {exc}")

    try:
        # Step 1: Finnhub market news
        try:
            raw_market = finnhub.fetch_market_news("general")
            market_items = [normalize_finnhub_market(r) for r in raw_market]
            all_items.extend(market_items)
            repository.insert_fetch_log(FetchLog(
                provider="FINNHUB",
                status="ok",
                request_type="market_news",
                items_fetched=len(market_items),
            ))
            summary.total_fetched += len(market_items)
        except FinnhubError as exc:
            summary.provider_errors.append(f"Finnhub market: {exc}")
            repository.insert_fetch_log(FetchLog(
                provider="FINNHUB",
                status="error",
                request_type="market_news",
                error_message=str(exc),
            ))

        # Step 2: Finnhub company news
        company_fetched = 0
        for sym in syms:
            try:
                raw = finnhub.fetch_company_news(sym, from_s, to_s)
                items = [normalize_finnhub_company(r, sym) for r in raw]
                all_items.extend(items)
                company_fetched += len(items)
            except FinnhubError as exc:
                summary.provider_errors.append(f"Finnhub {sym}: {exc}")
        summary.total_fetched += company_fetched
        repository.insert_fetch_log(FetchLog(
            provider="FINNHUB",
            status="ok" if company_fetched else "partial",
            request_type="company_news",
            symbols_requested=syms,
            items_fetched=company_fetched,
        ))

        # Step 3: Alpha Vantage (max 3 tickers)
        if av:
            av_syms = _av_priority_symbols(syms)
            try:
                raw_av = av.fetch_news_sentiment(av_syms)
                av_items = [normalize_alpha_vantage(r) for r in raw_av]
                all_items.extend(av_items)
                summary.total_fetched += len(av_items)
                repository.insert_fetch_log(FetchLog(
                    provider="ALPHA_VANTAGE",
                    status="ok",
                    request_type="news_sentiment",
                    symbols_requested=av_syms,
                    items_fetched=len(av_items),
                ))
            except AlphaVantageRateLimitError as exc:
                summary.provider_errors.append(f"Alpha Vantage rate limit: {exc}")
                repository.insert_fetch_log(FetchLog(
                    provider="ALPHA_VANTAGE",
                    status="rate_limited",
                    request_type="news_sentiment",
                    symbols_requested=av_syms,
                    error_message=str(exc),
                ))
            except AlphaVantageError as exc:
                summary.provider_errors.append(f"Alpha Vantage: {exc}")
                repository.insert_fetch_log(FetchLog(
                    provider="ALPHA_VANTAGE",
                    status="error",
                    request_type="news_sentiment",
                    error_message=str(exc),
                ))

        # Step 4: SEC filings (stocks only)
        sec_fetched = 0
        stock_syms = [s for s in syms if s not in ETF_SYMBOLS]
        for sym in stock_syms:
            try:
                filings = sec.fetch_recent_filings(sym)
                for f in filings:
                    all_items.append(normalize_sec_filing(
                        symbol=f["symbol"],
                        form_type=f["form_type"],
                        filing_date=f["filing_date"],
                        accession=f["accession"],
                        primary_document=f["primary_document"],
                        cik=f["cik"],
                        description=f.get("description") or "",
                    ))
                sec_fetched += len(filings)
            except SecEdgarError as exc:
                summary.provider_errors.append(f"SEC {sym}: {exc}")
        summary.total_fetched += sec_fetched
        repository.insert_fetch_log(FetchLog(
            provider="SEC_EDGAR",
            status="ok" if sec_fetched else "partial",
            request_type="recent_filings",
            symbols_requested=stock_syms,
            items_fetched=sec_fetched,
        ))

    finally:
        finnhub.close()
        sec.close()
        if av:
            av.close()

    # Steps 5-10: process, dedupe, score
    processed = _process_items(all_items)
    unique, dupes = deduplicate_items(processed, repository)
    summary.duplicates_removed = dupes

    # Step 11: persist
    known_urls: set[str] = set()
    saved, skipped = repository.insert_items_batch(unique, known_urls)
    summary.total_saved = saved
    summary.duplicates_removed += skipped

    # Sentiment counts on unique items processed
    for item in unique:
        if item.sentiment_label == "bullish":
            summary.bullish_count += 1
        elif item.sentiment_label == "bearish":
            summary.bearish_count += 1
        else:
            summary.neutral_count += 1

    # Top headlines by impact
    by_impact = sorted(unique, key=lambda i: i.impact_score, reverse=True)
    summary.top_positive_items = [
        i.headline for i in by_impact if i.sentiment_label == "bullish"
    ][:5]
    summary.top_negative_items = [
        i.headline for i in by_impact if i.sentiment_label == "bearish"
    ][:5]

    sym_counter = Counter(i.symbol for i in unique if i.symbol != "MARKET")
    summary.top_symbols = [s for s, _ in sym_counter.most_common(5)]

    repository.insert_fetch_log(FetchLog(
        provider="PIPELINE",
        status="ok",
        request_type="run_news_pipeline",
        symbols_requested=syms,
        items_fetched=summary.total_fetched,
        items_saved=summary.total_saved,
        duplicates_removed=summary.duplicates_removed,
    ))

    return summary


def get_news_signal(
    symbol: str,
    *,
    since_days: int = 7,
    repo: NewsRepository | None = None,
) -> NewsSignal:
    repository = repo or get_repository()
    sym = symbol.strip().upper()
    items = repository.query_for_symbol(sym, since_days=since_days)

    if not items:
        return NewsSignal(
            symbol=sym,
            news_sentiment_label="neutral",
            news_sentiment_score=0.0,
            news_impact_score=0.0,
            bullish_count=0,
            bearish_count=0,
            neutral_count=0,
            top_positive_headline=None,
            top_negative_headline=None,
            major_risk_events=[],
            last_updated=None,
        )

    bullish = bearish = neutral = 0
    weighted_sentiment = 0.0
    weight_sum = 0.0
    max_impact = 0.0
    top_pos: NewsItem | None = None
    top_neg: NewsItem | None = None
    risks: list[str] = []
    last_updated: datetime | None = None

    for item in items:
        if item.sentiment_label == "bullish":
            bullish += 1
        elif item.sentiment_label == "bearish":
            bearish += 1
        else:
            neutral += 1

        w = max(item.relevance_score, 0.1)
        weighted_sentiment += item.sentiment_score * w
        weight_sum += w
        max_impact = max(max_impact, item.impact_score)

        if item.sentiment_label == "bullish":
            if top_pos is None or item.impact_score > top_pos.impact_score:
                top_pos = item
        if item.sentiment_label == "bearish":
            if top_neg is None or item.impact_score < top_neg.impact_score:
                top_neg = item

        if item.event_type in ("legal_regulatory",) or (
            item.sentiment_label == "bearish" and item.impact_score < -0.3
        ):
            risks.append(item.headline)

        if item.published_at and (last_updated is None or item.published_at > last_updated):
            last_updated = item.published_at

    avg_sentiment = weighted_sentiment / weight_sum if weight_sum else 0.0
    if avg_sentiment > 0.2:
        label = "bullish"
    elif avg_sentiment < -0.2:
        label = "bearish"
    else:
        label = "neutral"

    return NewsSignal(
        symbol=sym,
        news_sentiment_label=label,
        news_sentiment_score=round(avg_sentiment, 4),
        news_impact_score=round(max_impact, 4),
        bullish_count=bullish,
        bearish_count=bearish,
        neutral_count=neutral,
        top_positive_headline=top_pos.headline if top_pos else None,
        top_negative_headline=top_neg.headline if top_neg else None,
        major_risk_events=risks[:5],
        last_updated=last_updated,
    )
