from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, insert, select
from sqlalchemy.engine import Engine

from app.db import market_regime_snapshots


def _now() -> datetime:
  return datetime.now(UTC)


def _new_id() -> str:
  return str(uuid.uuid4())


class RegimeHistoryRepository:
  def __init__(self, engine: Engine) -> None:
    self.engine = engine

  def insert_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
    snap_id = row.get("id") or _new_id()
    values = {
      "id": snap_id,
      "timestamp": row.get("timestamp") or _now(),
      "snapshot_date": row["snapshot_date"],
      "symbol": row.get("symbol", "MARKET"),
      "regime_name": row["regime_name"],
      "regime_score": row["regime_score"],
      "confidence": row["confidence"],
      "risk_level": row["risk_level"],
      "preferred_strategy": row["preferred_strategy"],
      "trend_score": row["trend_score"],
      "momentum_score": row["momentum_score"],
      "volatility_score": row["volatility_score"],
      "breadth_score": row["breadth_score"],
      "macro_score": row["macro_score"],
      "news_catalyst_score": row["news_catalyst_score"],
      "qqq_price": row.get("qqq_price"),
      "spy_price": row.get("spy_price"),
      "iwm_price": row.get("iwm_price"),
      "dia_price": row.get("dia_price"),
      "vix_level": row.get("vix_level"),
      "ten_year_yield": row.get("ten_year_yield"),
      "dxy_value": row.get("dxy_value"),
      "summary_json": row.get("summary_json"),
    }
    with self.engine.begin() as conn:
      conn.execute(insert(market_regime_snapshots).values(**values))
    return values

  def upsert_daily_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
    snap_date = row["snapshot_date"]
    with self.engine.begin() as conn:
      existing = conn.execute(
        select(market_regime_snapshots).where(market_regime_snapshots.c.snapshot_date == snap_date)
      ).first()
      if existing:
        from sqlalchemy import update

        values = {k: v for k, v in row.items() if k != "id"}
        conn.execute(
          update(market_regime_snapshots)
          .where(market_regime_snapshots.c.snapshot_date == snap_date)
          .values(**values)
        )
        return {**dict(existing._mapping), **values}
    return self.insert_snapshot(row)

  def list_history(self, *, days: int = 30) -> list[dict[str, Any]]:
    cutoff = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta

    since = cutoff - timedelta(days=days)
    with self.engine.connect() as conn:
      rows = conn.execute(
        select(market_regime_snapshots)
        .where(market_regime_snapshots.c.timestamp >= since)
        .order_by(desc(market_regime_snapshots.c.timestamp))
      ).fetchall()
      return [dict(r._mapping) for r in rows]

  def latest(self) -> dict[str, Any] | None:
    with self.engine.connect() as conn:
      row = conn.execute(
        select(market_regime_snapshots).order_by(desc(market_regime_snapshots.c.timestamp)).limit(1)
      ).first()
      return dict(row._mapping) if row else None
