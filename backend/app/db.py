from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Float, Index, Integer, MetaData, String, Table, create_engine, select
from sqlalchemy.engine import Engine

from app.config import settings

metadata = MetaData()

event_log = Table(
    "event_log",
    metadata,
    Column("seq_id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", String(64), nullable=False, unique=True),
    Column("event_type", String(80), nullable=False),
    Column("event_version", Integer, nullable=False, default=1),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("producer", String(80), nullable=False),
    Column("correlation_id", String(64), nullable=True),
    Column("causation_id", String(64), nullable=True),
    Column("aggregate_type", String(80), nullable=False),
    Column("aggregate_id", String(120), nullable=False),
    Column("idempotency_key", String(200), nullable=True),
    Column("schema_ref", String(120), nullable=True),
    Column("payload", JSON, nullable=False),
)

command_lock = Table(
    "command_lock",
    metadata,
    Column("idempotency_key", String(200), primary_key=True),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("status", String(32), nullable=False),
)

trade_decisions = Table(
    "trade_decisions",
    metadata,
    Column("decision_id", String(64), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("symbol", String(32), nullable=False),
    Column("universe", String(120), nullable=True),
    Column("signal_id", String(120), nullable=True),
    Column("direction", String(16), nullable=False),
    Column("strategy_type", String(80), nullable=False),
    Column("risk_status", String(32), nullable=False),
    Column("confidence", Float, nullable=False, default=0.0),
    Column("score", Float, nullable=False, default=0.0),
    Column("edge", Float, nullable=False, default=0.0),
    Column("market_regime", String(64), nullable=True),
    Column("technical_score", Float, nullable=True),
    Column("catalyst_score", Float, nullable=True),
    Column("liquidity_score", Float, nullable=True),
    Column("risk_score", Float, nullable=True),
    Column("max_loss", Float, nullable=True),
    Column("max_profit", Float, nullable=True),
    Column("breakeven", Float, nullable=True),
    Column("probability_profit", Float, nullable=True),
    Column("expected_value", Float, nullable=True),
    Column("entry_trigger", String(512), nullable=True),
    Column("invalidation_rule", String(512), nullable=True),
    Column("profit_plan", String(512), nullable=True),
    Column("thesis", String(1024), nullable=True),
    Column("rule_reasons", JSON, nullable=False, default=list),
    Column("legs", JSON, nullable=False, default=list),
    Column("data_status", String(32), nullable=False, default="mock"),
    Column("broker_status", String(32), nullable=False, default="disconnected"),
    Column("reconciliation_status", String(32), nullable=False, default="ok"),
    Column("paper_order_id", String(120), nullable=True),
    Column("paper_position_id", String(120), nullable=True),
    Column("paper_pnl", Float, nullable=True),
    Column("paper_pnl_percent", Float, nullable=True),
    Column("max_drawdown", Float, nullable=True),
    Column("current_status", String(48), nullable=False, default="decision_saved"),
    Column("review_status", String(32), nullable=False, default="pending"),
    Column("final_outcome", String(48), nullable=True),
    Column("lesson", String(1024), nullable=True),
    Column("closed_at", DateTime(timezone=True), nullable=True),
    Column("replay_avg_pnl", Float, nullable=True),
    Column("extra", JSON, nullable=False, default=dict),
)

Index("idx_event_log_type_occurred", event_log.c.event_type, event_log.c.occurred_at)
Index("idx_event_log_aggregate_seq", event_log.c.aggregate_type, event_log.c.aggregate_id, event_log.c.seq_id)
Index("idx_event_log_idempotency_key", event_log.c.idempotency_key, unique=True)
Index("idx_trade_decisions_symbol_created", trade_decisions.c.symbol, trade_decisions.c.created_at)
Index("idx_trade_decisions_status", trade_decisions.c.current_status, trade_decisions.c.review_status)


def get_engine() -> Engine:
    return create_engine(settings.database_url, future=True)


def init_db(engine: Engine) -> None:
    metadata.create_all(engine)


def new_decision_id() -> str:
    return f"dec_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
