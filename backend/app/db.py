from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

paper_trades = Table(
    "paper_trades",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("created_date", DateTime(timezone=True), nullable=False),
    Column("symbol", String(16), nullable=False, index=True),
    Column("underlying_price_at_entry", Float, nullable=False),
    Column("strategy_type", String(64), nullable=False),
    Column("expiry_date", String(16), nullable=False),
    Column("days_to_entry_dte", Integer, nullable=False),
    Column("long_strike", Float, nullable=False),
    Column("short_strike", Float, nullable=False),
    Column("long_option_type", String(8), nullable=False),
    Column("short_option_type", String(8), nullable=False),
    Column("entry_debit", Float, nullable=True),
    Column("entry_credit", Float, nullable=True),
    Column("quantity", Integer, nullable=False, default=1),
    Column("max_profit", Float, nullable=False),
    Column("max_loss", Float, nullable=False),
    Column("breakeven", Float, nullable=False),
    Column("entry_delta_long", Float, nullable=True),
    Column("entry_delta_short", Float, nullable=True),
    Column("entry_iv", Float, nullable=True),
    Column("entry_atr", Float, nullable=True),
    Column("entry_rsi", Float, nullable=True),
    Column("entry_macd", Float, nullable=True),
    Column("market_bias", String(32), nullable=True),
    Column("confidence", String(32), nullable=True),
    Column("reason_for_trade", Text, nullable=True),
    Column("notes", Text, nullable=True),
    Column("status", String(16), nullable=False, default="OPEN", index=True),
    Column("exit_date", DateTime(timezone=True), nullable=True),
    Column("exit_reason", String(128), nullable=True),
    Column("current_underlying_price", Float, nullable=True),
    Column("current_spread_value", Float, nullable=True),
    Column("realized_pnl", Float, nullable=True),
    Column("unrealized_pnl", Float, nullable=True),
    Column("percent_return", Float, nullable=True),
    Column("highest_profit_seen", Float, nullable=True),
    Column("largest_drawdown", Float, nullable=True),
    Column("last_marked_at", DateTime(timezone=True), nullable=True),
    Column("entry_snapshot_json", JSON, nullable=True),
    Column("execution_enabled", Boolean, nullable=False, default=False),
    Column("broker_order_id", String(64), nullable=True),
    Column("broker_status", String(32), nullable=True),
    Column("source", String(16), nullable=False, default="manual"),
    Column("ibkr_sync_key", String(128), nullable=True, index=True),
    Column("long_con_id", Integer, nullable=True),
    Column("short_con_id", Integer, nullable=True),
    Column("average_cost", Float, nullable=True),
    Column("market_value", Float, nullable=True),
    Column("today_pnl", Float, nullable=True),
    Column("long_bid", Float, nullable=True),
    Column("long_ask", Float, nullable=True),
    Column("long_mid", Float, nullable=True),
    Column("short_bid", Float, nullable=True),
    Column("short_ask", Float, nullable=True),
    Column("short_mid", Float, nullable=True),
    Column("max_profit_remaining", Float, nullable=True),
    Column("progress_pct", Float, nullable=True),
    Column("breakeven_distance", Float, nullable=True),
    Column("distance_to_long_strike", Float, nullable=True),
    Column("distance_to_short_strike", Float, nullable=True),
    Column("ibkr_position_json", JSON, nullable=True),
)

paper_trade_snapshots = Table(
    "paper_trade_snapshots",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("trade_id", String(36), nullable=False, index=True),
    Column("marked_at", DateTime(timezone=True), nullable=False),
    Column("underlying_price", Float, nullable=True),
    Column("spread_value", Float, nullable=True),
    Column("unrealized_pnl", Float, nullable=True),
    Column("percent_return", Float, nullable=True),
    Column("snapshot_json", JSON, nullable=True),
)

paper_trade_reviews = Table(
    "paper_trade_reviews",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("trade_id", String(36), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("what_went_right", Text, nullable=True),
    Column("what_went_wrong", Text, nullable=True),
    Column("indicators_agreed", Text, nullable=True),
    Column("regime_change", Text, nullable=True),
    Column("would_recommend_again", Text, nullable=True),
    Column("review_json", JSON, nullable=True),
)

paper_trade_sync_logs = Table(
    "paper_trade_sync_logs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("synced_at", DateTime(timezone=True), nullable=False),
    Column("action", String(32), nullable=False),
    Column("records_updated", Integer, nullable=False, default=0),
    Column("new_trades", Integer, nullable=False, default=0),
    Column("closed_trades", Integer, nullable=False, default=0),
    Column("failed_requests", Integer, nullable=False, default=0),
    Column("message", Text, nullable=True),
    Column("details_json", JSON, nullable=True),
)

market_regime_snapshots = Table(
    "market_regime_snapshots",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("timestamp", DateTime(timezone=True), nullable=False, index=True),
    Column("snapshot_date", String(10), nullable=False, index=True),
    Column("symbol", String(16), nullable=False, default="MARKET"),
    Column("regime_name", String(64), nullable=False),
    Column("regime_score", Float, nullable=False),
    Column("confidence", String(16), nullable=False),
    Column("risk_level", String(16), nullable=False),
    Column("preferred_strategy", String(64), nullable=False),
    Column("trend_score", Float, nullable=False),
    Column("momentum_score", Float, nullable=False),
    Column("volatility_score", Float, nullable=False),
    Column("breadth_score", Float, nullable=False),
    Column("macro_score", Float, nullable=False),
    Column("news_catalyst_score", Float, nullable=False),
    Column("qqq_price", Float, nullable=True),
    Column("spy_price", Float, nullable=True),
    Column("iwm_price", Float, nullable=True),
    Column("dia_price", Float, nullable=True),
    Column("vix_level", Float, nullable=True),
    Column("ten_year_yield", Float, nullable=True),
    Column("dxy_value", Float, nullable=True),
    Column("summary_json", JSON, nullable=True),
)

trade_decisions = Table(
    "trade_decisions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("timestamp", DateTime(timezone=True), nullable=False, index=True),
    Column("symbol", String(16), nullable=False, index=True),
    Column("decision", String(64), nullable=False),
    Column("trade_score", Float, nullable=False),
    Column("confidence", String(16), nullable=False),
    Column("market_regime", String(64), nullable=True),
    Column("strategy", String(64), nullable=True),
    Column("reason", Text, nullable=True),
    Column("entry_price", Float, nullable=True),
    Column("entry_trigger", Text, nullable=True),
    Column("target", String(64), nullable=True),
    Column("stop", String(64), nullable=True),
    Column("risk_level", String(16), nullable=False),
    Column("probability", Float, nullable=True),
    Column("summary", Text, nullable=True),
    Column("analysis_timestamp", String(64), nullable=True),
    Column("summary_json", JSON, nullable=True),
)

news_items = Table(
    "news_items",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("provider", String(32), nullable=False, index=True),
    Column("source", String(64), nullable=True),
    Column("symbol", String(16), nullable=False, index=True),
    Column("symbols", JSON, nullable=True),
    Column("category", String(32), nullable=True),
    Column("headline", Text, nullable=False),
    Column("summary", Text, nullable=True),
    Column("url", Text, nullable=True, index=True),
    Column("published_at", DateTime(timezone=True), nullable=True, index=True),
    Column("sentiment_label", String(16), nullable=True, index=True),
    Column("sentiment_score", Float, nullable=True),
    Column("relevance_score", Float, nullable=True),
    Column("impact_score", Float, nullable=True),
    Column("event_type", String(32), nullable=True, index=True),
    Column("raw_json", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

news_fetch_log = Table(
    "news_fetch_log",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("provider", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column("request_type", String(32), nullable=False),
    Column("symbols_requested", JSON, nullable=True),
    Column("items_fetched", Integer, nullable=False, default=0),
    Column("items_saved", Integer, nullable=False, default=0),
    Column("duplicates_removed", Integer, nullable=False, default=0),
    Column("error_message", Text, nullable=True),
    Column("refresh_mode", String(16), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

news_events = Table(
    "news_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("cluster_id", String(64), nullable=False, index=True),
    Column("symbol", String(16), nullable=False, index=True),
    Column("primary_category", String(32), nullable=False, index=True),
    Column("subtype", String(64), nullable=True),
    Column("title", Text, nullable=False),
    Column("summary", Text, nullable=True),
    Column("source_count", Integer, nullable=False, default=1),
    Column("sources_json", JSON, nullable=True),
    Column("article_ids_json", JSON, nullable=True),
    Column("earliest_time", DateTime(timezone=True), nullable=True),
    Column("latest_time", DateTime(timezone=True), nullable=True, index=True),
    Column("sentiment_score", Float, nullable=False, default=0.0),
    Column("importance_score", Float, nullable=False, default=0.0),
    Column("primary_ticker_score", Float, nullable=False, default=0.0),
    Column("source_quality_score", Float, nullable=False, default=0.0),
    Column("impact_score", Float, nullable=False, default=0.0),
    Column("confidence", String(16), nullable=False, default="Low"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

ticker_news_signals = Table(
    "ticker_news_signals",
    metadata,
    Column("symbol", String(16), primary_key=True),
    Column("news_bias", String(16), nullable=False, default="Neutral"),
    Column("news_quality_score", Float, nullable=False, default=0.0),
    Column("catalyst_strength_score", Float, nullable=False, default=0.0),
    Column("net_impact_score", Float, nullable=False, default=0.0),
    Column("bullish_count", Integer, nullable=False, default=0),
    Column("bearish_count", Integer, nullable=False, default=0),
    Column("neutral_count", Integer, nullable=False, default=0),
    Column("top_catalyst", Text, nullable=True),
    Column("top_risk", Text, nullable=True),
    Column("llm_summary", Text, nullable=True),
    Column("llm_summary_json", JSON, nullable=True),
    Column("llm_cluster_hash", String(64), nullable=True),
    Column("confidence", String(16), nullable=False, default="Low"),
    Column("last_updated", DateTime(timezone=True), nullable=True),
)

market_intelligence_watchlist = Table(
    "market_intelligence_watchlist",
    metadata,
    Column("symbol", String(16), primary_key=True),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("priority", Integer, nullable=False, default=99),
    Column("company", String(128), nullable=True),
    Column("sector", String(64), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

opportunity_scan_results = Table(
    "opportunity_scan_results",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("timestamp", DateTime(timezone=True), nullable=False, index=True),
    Column("symbol", String(16), nullable=False, index=True),
    Column("direction_candidate", String(16), nullable=False),
    Column("opportunity_score", Float, nullable=False),
    Column("bull_score", Float, nullable=False),
    Column("bear_score", Float, nullable=False),
    Column("confidence_score", Float, nullable=False),
    Column("risk_score", Float, nullable=False),
    Column("news_score", Float, nullable=False),
    Column("technical_score", Float, nullable=False),
    Column("liquidity_score", Float, nullable=False),
    Column("market_regime_score", Float, nullable=False),
    Column("relative_strength_score", Float, nullable=False),
    Column("paper_feedback_score", Float, nullable=False),
    Column("next_earnings", String(32), nullable=True),
    Column("top_catalyst", Text, nullable=True),
    Column("market_context", String(128), nullable=True),
    Column("reason_json", JSON, nullable=True),
    Column("data_quality", String(32), nullable=False, default="partial"),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

_IBKR_MIGRATION_COLUMNS = {
    "source": "VARCHAR DEFAULT 'manual'",
    "ibkr_sync_key": "VARCHAR",
    "long_con_id": "INTEGER",
    "short_con_id": "INTEGER",
    "average_cost": "FLOAT",
    "market_value": "FLOAT",
    "today_pnl": "FLOAT",
    "long_bid": "FLOAT",
    "long_ask": "FLOAT",
    "long_mid": "FLOAT",
    "short_bid": "FLOAT",
    "short_ask": "FLOAT",
    "short_mid": "FLOAT",
    "max_profit_remaining": "FLOAT",
    "progress_pct": "FLOAT",
    "breakeven_distance": "FLOAT",
    "distance_to_long_strike": "FLOAT",
    "distance_to_short_strike": "FLOAT",
    "ibkr_position_json": "JSON",
}


def _migrate_schema(engine: Engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    with engine.begin() as conn:
        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(paper_trades)")}
        for col, ddl in _IBKR_MIGRATION_COLUMNS.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE paper_trades ADD COLUMN {col} {ddl}")
        nfl_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(news_fetch_log)")}
        if "refresh_mode" not in nfl_cols:
            conn.exec_driver_sql("ALTER TABLE news_fetch_log ADD COLUMN refresh_mode VARCHAR(16)")
        tns_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(ticker_news_signals)")}
        if "llm_summary_json" not in tns_cols:
            conn.exec_driver_sql("ALTER TABLE ticker_news_signals ADD COLUMN llm_summary_json JSON")
        if "llm_cluster_hash" not in tns_cols:
            conn.exec_driver_sql("ALTER TABLE ticker_news_signals ADD COLUMN llm_cluster_hash VARCHAR(64)")


def get_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, future=True)


def init_db(engine: Engine) -> None:
    metadata.create_all(engine)
    _migrate_schema(engine)
