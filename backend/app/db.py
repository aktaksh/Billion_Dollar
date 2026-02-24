from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
)
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

Index("idx_event_log_type_occurred", event_log.c.event_type, event_log.c.occurred_at)
Index("idx_event_log_aggregate_seq", event_log.c.aggregate_type, event_log.c.aggregate_id, event_log.c.seq_id)
Index("idx_event_log_idempotency_key", event_log.c.idempotency_key, unique=True)


def get_engine() -> Engine:
    return create_engine(settings.database_url, future=True)


def init_db(engine: Engine) -> None:
    metadata.create_all(engine)


