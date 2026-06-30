from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Float, Index, Integer, MetaData, String, Table, create_engine, inspect, select, text
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

options_chain_metadata = Table(
    "options_chain_metadata",
    metadata,
    Column("symbol", String(32), primary_key=True),
    Column("exchange", String(32), nullable=False, default="SMART"),
    Column("trading_class", String(64), nullable=True),
    Column("expiries", JSON, nullable=False, default=list),
    Column("strikes", JSON, nullable=False, default=list),
    Column("refreshed_at", DateTime(timezone=True), nullable=False),
)

options_chain_scan_status = Table(
    "options_chain_scan_status",
    metadata,
    Column("symbol", String(32), primary_key=True),
    Column("scanner_status", String(32), nullable=False, default="idle"),
    Column("chain_source", String(16), nullable=False, default="none"),
    Column("last_scan_started_at", DateTime(timezone=True), nullable=True),
    Column("last_scan_completed_at", DateTime(timezone=True), nullable=True),
    Column("last_error", String(512), nullable=True),
    Column("expiries_selected", JSON, nullable=False, default=list),
    Column("strike_low", Float, nullable=True),
    Column("strike_high", Float, nullable=True),
    Column("underlying_price", Float, nullable=True),
    Column("contracts_scanned", Integer, nullable=False, default=0),
    Column("contracts_rejected", Integer, nullable=False, default=0),
    Column("contracts_usable", Integer, nullable=False, default=0),
    Column("contracts_planned", Integer, nullable=False, default=0),
    Column("scan_notes", JSON, nullable=False, default=list),
    Column("scan_run_id", String(64), nullable=True),
    Column("chain_origin", String(32), nullable=False, default="none"),
)

app_runtime_settings = Table(
    "app_runtime_settings",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value", String(256), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

option_chain_contracts = Table(
    "option_chain_contracts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("symbol", String(32), nullable=False),
    Column("scan_run_id", String(64), nullable=False),
    Column("expiry", String(16), nullable=False),
    Column("dte", Integer, nullable=False),
    Column("option_type", String(8), nullable=False),
    Column("strike", Float, nullable=False),
    Column("bid", Float, nullable=False, default=0.0),
    Column("ask", Float, nullable=False, default=0.0),
    Column("last", Float, nullable=True),
    Column("mid", Float, nullable=False, default=0.0),
    Column("spread_pct", Float, nullable=False, default=0.0),
    Column("volume", Integer, nullable=False, default=0),
    Column("open_interest", Integer, nullable=False, default=0),
    Column("iv", Float, nullable=False, default=0.0),
    Column("delta", Float, nullable=False, default=0.0),
    Column("gamma", Float, nullable=False, default=0.0),
    Column("theta", Float, nullable=False, default=0.0),
    Column("vega", Float, nullable=False, default=0.0),
    Column("status", String(16), nullable=False, default="reject"),
    Column("rejection_reason", String(256), nullable=True),
    Column("captured_at", DateTime(timezone=True), nullable=False),
)

Index("idx_option_chain_contracts_symbol", option_chain_contracts.c.symbol, option_chain_contracts.c.captured_at)
Index(
    "idx_option_chain_contracts_key",
    option_chain_contracts.c.symbol,
    option_chain_contracts.c.expiry,
    option_chain_contracts.c.strike,
    option_chain_contracts.c.option_type,
)


def get_engine() -> Engine:
    return create_engine(settings.database_url, future=True)


def init_db(engine: Engine) -> None:
    metadata.create_all(engine)
    _ensure_scan_status_columns(engine)


def _ensure_scan_status_columns(engine: Engine) -> None:
    insp = inspect(engine)
    if insp.has_table("options_chain_scan_status"):
        cols = {c["name"] for c in insp.get_columns("options_chain_scan_status")}
        alters: list[str] = []
        if "contracts_planned" not in cols:
            alters.append("ALTER TABLE options_chain_scan_status ADD COLUMN contracts_planned INTEGER DEFAULT 0")
        if "scan_notes" not in cols:
            alters.append("ALTER TABLE options_chain_scan_status ADD COLUMN scan_notes TEXT DEFAULT '[]'")
        if "chain_origin" not in cols:
            alters.append("ALTER TABLE options_chain_scan_status ADD COLUMN chain_origin TEXT DEFAULT 'none'")
        if alters:
            with engine.begin() as conn:
                for stmt in alters:
                    conn.execute(text(stmt))


def new_decision_id() -> str:
    return f"dec_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
