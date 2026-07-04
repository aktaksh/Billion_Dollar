from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, insert, select
from sqlalchemy.engine import Engine

from app.db import trade_decisions


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class DecisionRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        snap_id = row.get("id") or _new_id()
        values = {
            "id": snap_id,
            "timestamp": row.get("timestamp") or _now(),
            "symbol": row["symbol"],
            "decision": row["decision"],
            "trade_score": row["trade_score"],
            "confidence": row["confidence"],
            "market_regime": row.get("market_regime"),
            "strategy": row.get("strategy"),
            "reason": row.get("reason"),
            "entry_price": row.get("entry_price"),
            "entry_trigger": row.get("entry_trigger"),
            "target": row.get("target"),
            "stop": row.get("stop"),
            "risk_level": row["risk_level"],
            "probability": row.get("probability"),
            "summary": row.get("summary"),
            "analysis_timestamp": row.get("analysis_timestamp"),
            "summary_json": row.get("summary_json"),
        }
        with self.engine.begin() as conn:
            conn.execute(insert(trade_decisions).values(**values))
        return values

    def list_recent(self, symbol: str, *, limit: int = 20) -> list[dict[str, Any]]:
        sym = symbol.strip().upper()
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(trade_decisions)
                .where(trade_decisions.c.symbol == sym)
                .order_by(desc(trade_decisions.c.timestamp))
                .limit(limit)
            ).fetchall()
            return [dict(r._mapping) for r in rows]
