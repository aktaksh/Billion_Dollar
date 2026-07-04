"""HTTP response mapping for News Intelligence — wraps orchestrator without modifying it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from news_intelligence.news_config import ETF_SYMBOLS, load_config
from news_intelligence.news_models import NewsItem
from news_intelligence.news_orchestrator import get_news_signal, run_news_pipeline
from news_intelligence.news_repository import NewsRepository, get_repository


def _label_display(label: str) -> str:
    mapping = {"bullish": "Bullish", "bearish": "Bearish", "neutral": "Neutral"}
    return mapping.get(label.lower(), "Neutral")


def _importance(item: NewsItem) -> str:
    if item.event_type in ("legal_regulatory",) or (
        item.provider == "SEC_EDGAR" and (item.raw_json or {}).get("form_type") == "8-K"
    ):
        return "Critical"
    if item.event_type in ("earnings", "guidance", "macro", "merger_acquisition"):
        return "High"
    if abs(item.impact_score) >= 0.35:
        return "High"
    if abs(item.impact_score) >= 0.15:
        return "Medium"
    return "Low"


def _score_0_to_100(sentiment_score: float, label: str) -> int:
    raw = (sentiment_score + 1.0) * 50.0
    if label == "bullish":
        raw = max(raw, 55.0)
    elif label == "bearish":
        raw = min(raw, 45.0)
    return max(0, min(100, round(raw)))


def _freshness_minutes(last_updated: datetime | None) -> int | None:
    if last_updated is None:
        return None
    lu = last_updated if last_updated.tzinfo else last_updated.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - lu).total_seconds() // 60))


def _provider_status(provider_errors: list[str], has_finnhub: bool) -> str:
    if not has_finnhub:
        return "Error"
    if not provider_errors:
        return "Online"
    if len(provider_errors) >= 3:
        return "Error"
    return "Partial"


def _confidence_from_counts(total: int) -> str:
    if total >= 12:
        return "High"
    if total >= 4:
        return "Medium"
    return "Low"


def _item_to_event(item: NewsItem) -> dict[str, Any]:
    return {
        "symbol": item.symbol,
        "eventType": item.event_type,
        "title": item.headline,
        "source": item.source or item.provider,
        "sentiment": _label_display(item.sentiment_label),
        "importance": _importance(item),
        "impactScore": round(item.impact_score, 4),
        "publishedAt": item.published_at.isoformat() if item.published_at else None,
    }


def _count_by_importance(items: list[NewsItem]) -> tuple[int, int]:
    critical = high = 0
    for item in items:
        imp = _importance(item)
        if imp == "Critical":
            critical += 1
        elif imp == "High":
            high += 1
    return critical, high


def _build_comments(
    *,
    summary_fetched: int,
    summary_saved: int,
    duplicates: int,
    provider_errors: list[str],
    symbol: str,
    items: list[NewsItem],
) -> list[str]:
    comments: list[str] = []
    if summary_fetched == 0:
        comments.append("No new headlines found in the last 24 hours.")
    elif summary_saved == 0 and duplicates > 0:
        comments.append("Fetched articles existed already and were removed as duplicates.")
    elif summary_saved == 0 and summary_fetched > 0:
        comments.append("Fetched articles were ignored due to low relevance.")
    if not items:
        comments.append("No new high-impact news found.")
    for err in provider_errors:
        if "budget" in err.lower():
            comments.append("Finnhub daily budget reached.")
        elif "rate" in err.lower():
            comments.append(err)
    if symbol.upper() in ETF_SYMBOLS:
        comments.append("SEC filings skipped for ETF symbols.")
    return comments


def _planned_calls(symbol: str, has_av: bool) -> int:
    sym = symbol.upper()
    n = 2  # finnhub market + company
    if has_av:
        n += 1
    if sym not in ETF_SYMBOLS:
        n += 1  # sec
    return n


def _signal_payload(
    signal: Any,
    *,
    provider_errors: list[str],
    has_finnhub: bool,
    items: list[NewsItem],
) -> dict[str, Any]:
    total = signal.bullish_count + signal.bearish_count + signal.neutral_count
    freshness = _freshness_minutes(signal.last_updated)
    top_catalyst = signal.top_positive_headline or signal.top_negative_headline
    if not top_catalyst and items:
        top_catalyst = items[0].headline

    unavailable = not has_finnhub
    label = "Unavailable" if unavailable and total == 0 else _label_display(signal.news_sentiment_label)

    return {
        "symbol": signal.symbol,
        "label": label,
        "news_score_0_to_100": 0 if unavailable and total == 0 else _score_0_to_100(signal.news_sentiment_score, signal.news_sentiment_label),
        "sentiment_score": signal.news_sentiment_score,
        "impact_score": signal.news_impact_score,
        "confidence": _confidence_from_counts(total),
        "top_catalyst": top_catalyst,
        "last_updated": signal.last_updated.isoformat() if signal.last_updated else None,
        "data_freshness_minutes": freshness,
        "provider_status": "Error" if unavailable else _provider_status(provider_errors, has_finnhub),
        "bullish_count": signal.bullish_count,
        "bearish_count": signal.bearish_count,
        "neutral_count": signal.neutral_count,
    }


def get_latest_signal(symbol: str = "QQQ", *, repo: NewsRepository | None = None) -> dict[str, Any]:
    repository = repo or get_repository()
    sym = symbol.strip().upper()
    try:
        config = load_config(require_finnhub=False, require_sec=False)
        has_finnhub = bool(config.finnhub_api_key)
    except ValueError:
        has_finnhub = False

    signal = get_news_signal(sym, since_days=1, repo=repository)
    items = repository.query_for_symbol(sym, since_days=1)
    critical, high = _count_by_importance(items)

    news_signal = _signal_payload(signal, provider_errors=[], has_finnhub=has_finnhub, items=items)

    return {
        "status": "ok",
        "refreshMode": "cached",
        "newsSignal": news_signal,
        "bullishCount": signal.bullish_count,
        "bearishCount": signal.bearish_count,
        "neutralCount": signal.neutral_count,
        "criticalEventCount": critical,
        "highEventCount": high,
        "topEvents": [_item_to_event(i) for i in items[:10]],
        "providerErrors": [],
        "comments": _build_comments(
            summary_fetched=0,
            summary_saved=0,
            duplicates=0,
            provider_errors=[],
            symbol=sym,
            items=items,
        ),
    }


def quick_refresh(symbol: str = "QQQ", *, repo: NewsRepository | None = None) -> dict[str, Any]:
    repository = repo or get_repository()
    sym = symbol.strip().upper()
    started_at = datetime.now(UTC)

    try:
        config = load_config()
        has_finnhub = bool(config.finnhub_api_key)
        has_av = config.has_alpha_vantage
    except ValueError as exc:
        completed = datetime.now(UTC)
        empty_signal = {
            "symbol": sym,
            "label": "Unavailable",
            "news_score_0_to_100": 0,
            "sentiment_score": 0.0,
            "impact_score": 0.0,
            "confidence": "Low",
            "top_catalyst": None,
            "last_updated": None,
            "data_freshness_minutes": None,
            "provider_status": "Error",
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
        }
        return {
            "status": "error",
            "refreshMode": "quick",
            "startedAt": started_at.isoformat(),
            "completedAt": completed.isoformat(),
            "plannedCalls": 0,
            "executedCalls": 0,
            "skippedCalls": 0,
            "totalFetched": 0,
            "totalSaved": 0,
            "duplicatesRemoved": 0,
            "lowRelevanceIgnored": 0,
            "eventsCreated": 0,
            "bullishCount": 0,
            "bearishCount": 0,
            "neutralCount": 0,
            "criticalEventCount": 0,
            "highEventCount": 0,
            "topEvents": [],
            "providerErrors": [str(exc)],
            "comments": [str(exc)],
            "newsSignal": empty_signal,
        }

    planned = _planned_calls(sym, has_av)
    skipped = 0 if has_av else 1
    if sym in ETF_SYMBOLS:
        skipped += 1

    to_dt = datetime.now(UTC)
    from_dt = to_dt - timedelta(hours=24)

    summary = run_news_pipeline(symbols=[sym], from_date=from_dt, to_date=to_dt, repo=repository)
    signal = get_news_signal(sym, since_days=1, repo=repository)
    items = repository.query_for_symbol(sym, since_days=1)
    critical, high = _count_by_importance(items)

    low_rel = max(0, summary.total_fetched - summary.total_saved - summary.duplicates_removed)
    executed = planned - skipped - len(summary.provider_errors)
    executed = max(0, min(planned, executed))

    comments = _build_comments(
        summary_fetched=summary.total_fetched,
        summary_saved=summary.total_saved,
        duplicates=summary.duplicates_removed,
        provider_errors=summary.provider_errors,
        symbol=sym,
        items=[i for i in items if _importance(i) in ("Critical", "High")],
    )

    completed_at = datetime.now(UTC)
    news_signal = _signal_payload(
        signal,
        provider_errors=summary.provider_errors,
        has_finnhub=has_finnhub,
        items=items,
    )

    return {
        "status": "ok" if not summary.provider_errors or summary.total_saved > 0 else "partial",
        "refreshMode": "quick",
        "startedAt": started_at.isoformat(),
        "completedAt": completed_at.isoformat(),
        "plannedCalls": planned,
        "executedCalls": executed,
        "skippedCalls": skipped,
        "totalFetched": summary.total_fetched,
        "totalSaved": summary.total_saved,
        "duplicatesRemoved": summary.duplicates_removed,
        "lowRelevanceIgnored": low_rel,
        "eventsCreated": summary.total_saved,
        "bullishCount": summary.bullish_count,
        "bearishCount": summary.bearish_count,
        "neutralCount": summary.neutral_count,
        "criticalEventCount": critical,
        "highEventCount": high,
        "topEvents": [_item_to_event(i) for i in items[:15]],
        "providerErrors": summary.provider_errors,
        "comments": comments,
        "newsSignal": news_signal,
    }
