"""Watchlist persistence for Market Intelligence Center."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Engine

from app.db import market_intelligence_watchlist
from app.services.market_intelligence.watchlist_defaults import DEFAULT_WATCHLIST


def _now() -> datetime:
    return datetime.now(UTC)


class WatchlistRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def seed_defaults_if_empty(self) -> int:
        with self.engine.connect() as conn:
            count = conn.execute(
                select(market_intelligence_watchlist.c.symbol).limit(1)
            ).first()
            if count:
                return 0
        rows = [
            {
                "symbol": sym,
                "enabled": True,
                "priority": pri,
                "company": company,
                "sector": sector,
                "updated_at": _now(),
            }
            for sym, company, sector, pri in DEFAULT_WATCHLIST
        ]
        with self.engine.begin() as conn:
            conn.execute(insert(market_intelligence_watchlist), rows)
        return len(rows)

    def list_all(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(market_intelligence_watchlist).order_by(
                    market_intelligence_watchlist.c.priority
                )
            ).fetchall()
            return [dict(r._mapping) for r in rows]

    def list_enabled_symbols(self) -> list[str]:
        return [r["symbol"] for r in self.list_all() if r.get("enabled")]

    def update_row(self, symbol: str, *, enabled: bool | None = None, priority: int | None = None) -> dict[str, Any] | None:
        sym = symbol.strip().upper()
        values: dict[str, Any] = {"updated_at": _now()}
        if enabled is not None:
            values["enabled"] = enabled
        if priority is not None:
            values["priority"] = priority
        with self.engine.begin() as conn:
            conn.execute(
                update(market_intelligence_watchlist)
                .where(market_intelligence_watchlist.c.symbol == sym)
                .values(**values)
            )
        for row in self.list_all():
            if row["symbol"] == sym:
                return row
        return None

    def reset_defaults(self) -> int:
        with self.engine.begin() as conn:
            conn.execute(delete(market_intelligence_watchlist))
        return self.seed_defaults_if_empty() or len(DEFAULT_WATCHLIST)
