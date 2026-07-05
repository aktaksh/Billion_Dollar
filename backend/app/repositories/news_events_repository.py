"""Persistence for `news_events` clusters and `ticker_news_signals` (Part 11)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Engine

from app.db import news_events, ticker_news_signals


def _now() -> datetime:
    return datetime.now(UTC)


class NewsEventsRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def replace_events_for_symbols(self, symbols: list[str], events: list[dict[str, Any]]) -> int:
        """Replace all `news_events` rows for the given symbols with the
        freshly computed cluster set — idempotent per pipeline run."""
        if not symbols:
            return 0
        with self.engine.begin() as conn:
            conn.execute(delete(news_events).where(news_events.c.symbol.in_(symbols)))
            if events:
                conn.execute(insert(news_events), events)
        return len(events)

    def list_events_for_symbol(self, symbol: str, *, limit: int = 50) -> list[dict[str, Any]]:
        sym = symbol.strip().upper()
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(news_events)
                .where(news_events.c.symbol == sym)
                .order_by(news_events.c.latest_time.desc())
                .limit(limit)
            ).fetchall()
            return [dict(r._mapping) for r in rows]

    def upsert_ticker_signals(self, signals: list[dict[str, Any]]) -> int:
        if not signals:
            return 0
        with self.engine.begin() as conn:
            for sig in signals:
                sym = sig["symbol"]
                existing = conn.execute(
                    select(ticker_news_signals.c.symbol).where(ticker_news_signals.c.symbol == sym)
                ).first()
                values = {k: v for k, v in sig.items() if k != "symbol"}
                if existing:
                    conn.execute(
                        update(ticker_news_signals)
                        .where(ticker_news_signals.c.symbol == sym)
                        .values(**values)
                    )
                else:
                    conn.execute(insert(ticker_news_signals).values(**sig))
        return len(signals)

    def get_ticker_signal(self, symbol: str) -> dict[str, Any] | None:
        sym = symbol.strip().upper()
        with self.engine.connect() as conn:
            row = conn.execute(
                select(ticker_news_signals).where(ticker_news_signals.c.symbol == sym)
            ).first()
            return dict(row._mapping) if row else None

    def list_ticker_signals(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(ticker_news_signals).order_by(ticker_news_signals.c.symbol)
            ).fetchall()
            return [dict(r._mapping) for r in rows]


def get_events_repository() -> NewsEventsRepository:
    from pathlib import Path

    from app.config import settings
    from app.db import get_engine, init_db

    db_url = settings.database_url
    if db_url.startswith("sqlite:///./"):
        rel = db_url.replace("sqlite:///./", "")
        db_path = Path(__file__).resolve().parent.parent.parent / rel
        db_url = f"sqlite:///{db_path}"
    engine = get_engine(db_url)
    init_db(engine)
    return NewsEventsRepository(engine)
