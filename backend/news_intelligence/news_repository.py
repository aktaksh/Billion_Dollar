"""Persistence layer for news items and fetch logs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, insert, or_, select
from sqlalchemy.engine import Engine

from app.db import news_fetch_log, news_items
from news_intelligence.news_models import FetchLog, NewsItem


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


def _item_to_row(item: NewsItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "provider": item.provider,
        "source": item.source,
        "symbol": item.symbol,
        "symbols": item.symbols,
        "category": item.category,
        "headline": item.headline,
        "summary": item.summary,
        "url": item.url or None,
        "published_at": item.published_at,
        "sentiment_label": item.sentiment_label,
        "sentiment_score": item.sentiment_score,
        "relevance_score": item.relevance_score,
        "impact_score": item.impact_score,
        "event_type": item.event_type,
        "raw_json": item.raw_json,
        "created_at": item.created_at or _now(),
    }


def _row_to_item(row: dict[str, Any]) -> NewsItem:
    return NewsItem(
        id=row["id"],
        provider=row["provider"],
        source=row.get("source") or "",
        symbol=row["symbol"],
        symbols=row.get("symbols") or [],
        category=row.get("category") or "",
        headline=row["headline"],
        summary=row.get("summary") or "",
        url=row.get("url") or "",
        published_at=row.get("published_at"),
        sentiment_label=row.get("sentiment_label") or "neutral",
        sentiment_score=float(row.get("sentiment_score") or 0),
        relevance_score=float(row.get("relevance_score") or 0),
        impact_score=float(row.get("impact_score") or 0),
        event_type=row.get("event_type") or "other",
        raw_json=row.get("raw_json") or {},
        created_at=row.get("created_at") or _now(),
    )


class NewsRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def url_exists(self, url: str) -> bool:
        if not url:
            return False
        with self.engine.connect() as conn:
            row = conn.execute(
                select(news_items.c.id).where(news_items.c.url == url).limit(1)
            ).first()
            return row is not None

    def find_recent_items(self, since: datetime) -> list[NewsItem]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(news_items)
                .where(news_items.c.published_at >= since)
                .order_by(desc(news_items.c.published_at))
            ).fetchall()
            return [_row_to_item(dict(r._mapping)) for r in rows]

    def insert_items(self, items: list[NewsItem]) -> int:
        saved = 0
        with self.engine.begin() as conn:
            for item in items:
                if item.url and self.url_exists(item.url):
                    continue
                conn.execute(insert(news_items).values(**_item_to_row(item)))
                saved += 1
        return saved

    def insert_items_batch(self, items: list[NewsItem], known_urls: set[str]) -> tuple[int, int]:
        """Insert items skipping URLs in known_urls or DB. Returns (saved, skipped)."""
        saved = skipped = 0
        with self.engine.begin() as conn:
            for item in items:
                url = item.url or ""
                if url and (url in known_urls or self._url_exists_conn(conn, url)):
                    skipped += 1
                    continue
                conn.execute(insert(news_items).values(**_item_to_row(item)))
                if url:
                    known_urls.add(url)
                saved += 1
        return saved, skipped

    @staticmethod
    def _url_exists_conn(conn: Any, url: str) -> bool:
        row = conn.execute(
            select(news_items.c.id).where(news_items.c.url == url).limit(1)
        ).first()
        return row is not None

    def insert_fetch_log(self, log: FetchLog) -> str:
        log_id = log.id or _new_id()
        values = {
            "id": log_id,
            "provider": log.provider,
            "status": log.status,
            "request_type": log.request_type,
            "symbols_requested": log.symbols_requested,
            "items_fetched": log.items_fetched,
            "items_saved": log.items_saved,
            "duplicates_removed": log.duplicates_removed,
            "error_message": log.error_message,
            "refresh_mode": log.refresh_mode,
            "created_at": log.created_at or _now(),
        }
        with self.engine.begin() as conn:
            conn.execute(insert(news_fetch_log).values(**values))
        return log_id

    def query_for_symbol(self, symbol: str, since_days: int = 7) -> list[NewsItem]:
        sym = symbol.strip().upper()
        since = _now() - timedelta(days=since_days)
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(news_items)
                .where(
                    news_items.c.published_at >= since,
                    or_(
                        news_items.c.symbol == sym,
                        news_items.c.symbol == "MARKET",
                    ),
                )
                .order_by(desc(news_items.c.impact_score), desc(news_items.c.published_at))
            ).fetchall()
            items = [_row_to_item(dict(r._mapping)) for r in rows]
        # Also include items where sym is in symbols JSON (post-filter)
        return [
            i
            for i in items
            if i.symbol == sym or i.symbol == "MARKET" or sym in (i.symbols or [])
        ]


def get_repository() -> NewsRepository:
    from pathlib import Path

    from app.config import settings
    from app.db import get_engine, init_db

    db_url = settings.database_url
    if db_url.startswith("sqlite:///./"):
        rel = db_url.replace("sqlite:///./", "")
        db_path = Path(__file__).resolve().parent.parent / rel
        db_url = f"sqlite:///{db_path}"
    engine = get_engine(db_url)
    init_db(engine)
    return NewsRepository(engine)
