"""Watchlist CRUD for Market Intelligence Center."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine

from app.repositories.watchlist_repository import WatchlistRepository
from app.services.market_intelligence.news_signal_service import NewsSignalService
from news_intelligence.news_repository import NewsRepository


class WatchlistService:
    def __init__(self, engine: Engine, repo: NewsRepository) -> None:
        self._repo = WatchlistRepository(engine)
        self._news_repo = repo
        self._signals = NewsSignalService(repo)

    def ensure_seeded(self) -> None:
        self._repo.seed_defaults_if_empty()

    def list_with_signals(self) -> list[dict[str, Any]]:
        self.ensure_seeded()
        rows = self._repo.list_all()
        out: list[dict[str, Any]] = []
        for row in rows:
            sym = row["symbol"]
            sig = self._signals.signal_for_symbol(sym, since_days=7)
            out.append({
                "enabled": bool(row.get("enabled")),
                "priority": row.get("priority", 99),
                "symbol": sym,
                "company": row.get("company") or "—",
                "sector": row.get("sector") or "—",
                "last_news_time": sig.get("last_updated"),
                "news_score": sig.get("news_score_0_to_100", 0),
                "sentiment": sig.get("label", "Neutral"),
                "next_earnings": None,
                "refresh_status": "Cached" if sig.get("last_updated") else "No data",
            })
        return out

    def update(self, symbol: str, *, enabled: bool | None = None, priority: int | None = None) -> dict[str, Any] | None:
        return self._repo.update_row(symbol, enabled=enabled, priority=priority)

    def reset(self) -> int:
        return self._repo.reset_defaults()

    def enabled_symbols(self) -> list[str]:
        self.ensure_seeded()
        return self._repo.list_enabled_symbols()
