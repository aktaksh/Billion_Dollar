from __future__ import annotations

from typing import Literal

from app.services.broker_session import evaluate_broker_connection

DataStatus = Literal["live", "stale", "mock", "degraded", "disconnected"]

STALE_AFTER_SECONDS = 300

__all__ = [
    "DataStatus",
    "STALE_AFTER_SECONDS",
    "evaluate_broker_connection",
    "snapshot_data_status",
    "runtime_gate_status",
]


def snapshot_data_status(*, captured_at: str | None, broker_connected: bool, chain_source: str) -> DataStatus:
    if not broker_connected:
        return "disconnected" if chain_source != "mock" else "mock"
    if chain_source == "mock":
        return "mock" if broker_connected else "degraded"
    from datetime import UTC, datetime

    if not captured_at:
        return "degraded"
    try:
        normalized = captured_at.replace("Z", "+00:00")
        captured = datetime.fromisoformat(normalized)
    except ValueError:
        return "degraded"
    age = (datetime.now(UTC) - captured.astimezone(UTC)).total_seconds()
    if age > STALE_AFTER_SECONDS:
        return "stale"
    return "live"


def runtime_gate_status(
    *,
    broker_connected: bool,
    data_status: DataStatus,
    reconciliation_mismatch_active: bool,
    allow_mock_option_chain: bool,
) -> tuple[bool, str]:
    if reconciliation_mismatch_active:
        return False, "reconcile_mismatch_active"
    if data_status == "disconnected":
        return False, "broker_disconnected"
    if data_status == "stale":
        return False, "market_data_stale"
    if data_status == "mock" and not allow_mock_option_chain:
        return False, "mock_chain_not_allowed"
    return True, "ok"
