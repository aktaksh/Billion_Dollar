from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from app.services.broker_session import evaluate_broker_connection

DataStatus = Literal["live", "stale", "mock", "degraded", "disconnected"]

STALE_AFTER_SECONDS = 300

__all__ = [
    "DataStatus",
    "STALE_AFTER_SECONDS",
    "evaluate_broker_connection",
    "normalize_chain_data_status",
    "snapshot_data_status",
    "runtime_gate_status",
    "chain_runtime_gate_status",
    "scan_age_seconds",
]


def scan_age_seconds(last_scan_completed_at: datetime | str | None) -> float | None:
    if last_scan_completed_at is None:
        return None
    if isinstance(last_scan_completed_at, str):
        try:
            completed = datetime.fromisoformat(last_scan_completed_at.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        completed = last_scan_completed_at
    if completed.tzinfo is None:
        completed = completed.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - completed.astimezone(UTC)).total_seconds())


def normalize_chain_data_status(status: str) -> DataStatus:
    normalized = status.strip().lower()
    if normalized in {"live", "stale", "mock", "degraded", "disconnected"}:
        return normalized  # type: ignore[return-value]
    if normalized == "unavailable":
        return "disconnected"
    if normalized == "partial":
        return "degraded"
    return "degraded"


def snapshot_data_status(*, captured_at: str | None, broker_connected: bool, chain_source: str) -> DataStatus:
    if not broker_connected:
        return "disconnected" if chain_source != "mock" else "mock"
    if chain_source == "mock":
        return "mock" if broker_connected else "degraded"
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
    allow_cached_chain: bool = False,
) -> tuple[bool, str]:
    if reconciliation_mismatch_active:
        return False, "reconcile_mismatch_active"
    if data_status == "disconnected":
        return False, "broker_disconnected"
    if data_status == "stale" and not allow_cached_chain:
        return False, "market_data_stale"
    if data_status == "mock" and not allow_mock_option_chain:
        return False, "mock_chain_not_allowed"
    return True, "ok"


def chain_runtime_gate_status(
    *,
    scanner_status: str,
    data_status: str,
    chain_source: str,
    allow_mock_option_chain: bool,
    last_scan_completed_at: datetime | str | None = None,
    contracts_usable: int = 0,
    max_runtime_age_seconds: int = 900,
    allow_stale_runtime_dev: bool = False,
    min_usable_contracts: int = 10,
) -> tuple[bool, str, str | None]:
    """Return (allowed, block_reason, runtime_warning)."""
    if chain_source in {"none", "fallback"} and not allow_mock_option_chain:
        return False, "chain_fallback", None
    if chain_source == "mock" and not allow_mock_option_chain:
        return False, "chain_fallback", None
    if scanner_status == "failed":
        return False, "chain_failed", None

    if (
        allow_stale_runtime_dev
        and scanner_status == "stale"
        and chain_source == "broker"
        and contracts_usable >= min_usable_contracts
    ):
        return True, "ok", "Dev mode: using stale broker cache from last session"

    age = scan_age_seconds(last_scan_completed_at)
    cache_runtime_ok = (
        contracts_usable > 0
        and chain_source == "broker"
        and age is not None
        and age <= max_runtime_age_seconds
    )
    if cache_runtime_ok:
        warning: str | None = None
        if data_status in {"degraded", "stale", "disconnected"} or scanner_status in {
            "stale",
            "partial",
            "idle",
            "scanning",
        }:
            age_min = max(0, int(age // 60))
            warning = (
                f"Using cached broker chain (~{age_min}m old); "
                "data may be degraded — review quotes before entry"
            )
        return True, "ok", warning

    if scanner_status in {"stale", "partial"}:
        return False, f"chain_{scanner_status}", None
    if data_status in {"stale", "disconnected", "degraded"}:
        return False, f"chain_{data_status}", None
    if scanner_status not in {"fresh", "scanning"} and data_status not in {"live", "mock"}:
        return False, "chain_unavailable", None
    return True, "ok", None
