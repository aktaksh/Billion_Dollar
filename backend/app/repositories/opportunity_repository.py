"""Persistence for Opportunity Scanner results."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Engine

from app.db import opportunity_scan_results


def _now() -> datetime:
    return datetime.now(UTC)


class OpportunityRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def save_batch(self, rows: list[dict[str, Any]], *, timestamp: datetime | None = None) -> datetime:
        ts = timestamp or _now()
        if not rows:
            return ts
        payload = []
        for row in rows:
            payload.append({
                "id": str(uuid4()),
                "timestamp": ts,
                "symbol": row["symbol"],
                "direction_candidate": row["direction_candidate"],
                "opportunity_score": row["opportunity_score"],
                "bull_score": row["bull_score"],
                "bear_score": row["bear_score"],
                "confidence_score": row["confidence_score"],
                "risk_score": row["risk_score"],
                "news_score": row["news_score"],
                "technical_score": row["technical_score"],
                "liquidity_score": row["liquidity_score"],
                "market_regime_score": row["market_regime_score"],
                "relative_strength_score": row["relative_strength_score"],
                "paper_feedback_score": row["paper_feedback_score"],
                "next_earnings": row.get("next_earnings"),
                "top_catalyst": row.get("top_catalyst"),
                "market_context": row.get("market_context"),
                "reason_json": row.get("reason_json"),
                "data_quality": row.get("data_quality", "partial"),
                "created_at": _now(),
            })
        with self.engine.begin() as conn:
            conn.execute(insert(opportunity_scan_results), payload)
        return ts

    def latest_timestamp(self) -> datetime | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(opportunity_scan_results.c.timestamp)
                .order_by(opportunity_scan_results.c.timestamp.desc())
                .limit(1)
            ).first()
        return row[0] if row else None

    def list_latest(self) -> list[dict[str, Any]]:
        ts = self.latest_timestamp()
        if not ts:
            return []
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(opportunity_scan_results)
                .where(opportunity_scan_results.c.timestamp == ts)
                .order_by(opportunity_scan_results.c.opportunity_score.desc())
            ).mappings().all()
        return [dict(r) for r in rows]

    def get_symbol_latest(self, symbol: str) -> dict[str, Any] | None:
        sym = symbol.strip().upper()
        with self.engine.connect() as conn:
            row = conn.execute(
                select(opportunity_scan_results)
                .where(opportunity_scan_results.c.symbol == sym)
                .order_by(opportunity_scan_results.c.timestamp.desc())
                .limit(1)
            ).mappings().first()
        return dict(row) if row else None

    def purge_older_than(self, keep_batches: int = 20) -> int:
        """Keep only the most recent N scan timestamps."""
        with self.engine.connect() as conn:
            ts_rows = conn.execute(
                select(opportunity_scan_results.c.timestamp)
                .distinct()
                .order_by(opportunity_scan_results.c.timestamp.desc())
            ).all()
        if len(ts_rows) <= keep_batches:
            return 0
        cutoff = ts_rows[keep_batches][0]
        with self.engine.begin() as conn:
            result = conn.execute(
                delete(opportunity_scan_results).where(opportunity_scan_results.c.timestamp < cutoff)
            )
        return result.rowcount or 0
