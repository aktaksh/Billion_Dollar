"""Daily API budget tracking from news_fetch_log."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from app.db import news_fetch_log


def _today_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class ApiBudgetManager:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.finnhub_limit = int(os.environ.get("FINNHUB_DAILY_LIMIT", "1000"))
        self.av_limit = int(os.environ.get("ALPHA_VANTAGE_DAILY_LIMIT", "25"))
        self.sec_limit = int(os.environ.get("SEC_DAILY_LIMIT", "10000"))

    def _count_provider(self, provider: str) -> int:
        since = _today_start()
        with self.engine.connect() as conn:
            row = conn.execute(
                select(func.count())
                .select_from(news_fetch_log)
                .where(
                    news_fetch_log.c.provider == provider,
                    news_fetch_log.c.created_at >= since,
                )
            ).scalar()
            return int(row or 0)

    def snapshot(self, *, planned: int = 0, skipped: int = 0, skip_reasons: list[str] | None = None) -> dict[str, Any]:
        finnhub_used = self._count_provider("FINNHUB")
        av_used = self._count_provider("ALPHA_VANTAGE")
        sec_used = self._count_provider("SEC_EDGAR")
        return {
            "finnhub": {"used": finnhub_used, "limit": self.finnhub_limit},
            "alpha_vantage": {"used": av_used, "limit": self.av_limit},
            "sec": {"used": sec_used, "limit": self.sec_limit},
            "planned_calls": planned,
            "skipped_calls": skipped,
            "skip_reasons": skip_reasons or [],
        }

    def activity_log(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(news_fetch_log)
                .order_by(news_fetch_log.c.created_at.desc())
                .limit(limit)
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            m = dict(r._mapping)
            out.append({
                "timestamp": m["created_at"].isoformat() if m.get("created_at") else None,
                "mode": m.get("refresh_mode") or "—",
                "provider": m["provider"],
                "calls_planned": None,
                "calls_executed": 1 if m["status"] == "ok" else 0,
                "calls_skipped": 0,
                "items_saved": m.get("items_saved", 0),
                "errors": m.get("error_message"),
                "status": m["status"],
                "request_type": m.get("request_type"),
                "items_fetched": m.get("items_fetched", 0),
            })
        return out
