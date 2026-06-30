from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.engine import Engine

from app.config import settings
from app.services.broker_status import normalize_chain_data_status
from app.db import option_chain_contracts, options_chain_metadata, options_chain_scan_status


def coerce_utc_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def ensure_scan_status_row(engine: Engine, symbol: str) -> None:
    sym = symbol.strip().upper()
    with engine.begin() as conn:
        existing = conn.execute(
            select(options_chain_scan_status.c.symbol).where(options_chain_scan_status.c.symbol == sym)
        ).first()
        if existing:
            return
        conn.execute(
            options_chain_scan_status.insert().values(
                symbol=sym,
                scanner_status="idle",
                chain_source="none",
                expiries_selected=[],
                contracts_scanned=0,
                contracts_rejected=0,
                contracts_usable=0,
            )
        )


def upsert_metadata(engine: Engine, payload: dict[str, Any]) -> None:
    sym = str(payload["symbol"]).upper()
    now = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(options_chain_metadata.delete().where(options_chain_metadata.c.symbol == sym))
        conn.execute(
            options_chain_metadata.insert().values(
                symbol=sym,
                exchange=str(payload.get("exchange", "SMART")),
                trading_class=str(payload.get("trading_class") or ""),
                expiries=list(payload.get("expiries") or []),
                strikes=list(payload.get("strikes") or []),
                refreshed_at=now,
            )
        )


def get_metadata(engine: Engine, symbol: str) -> dict[str, Any] | None:
    sym = symbol.strip().upper()
    with engine.begin() as conn:
        row = conn.execute(
            select(options_chain_metadata).where(options_chain_metadata.c.symbol == sym)
        ).mappings().first()
    return dict(row) if row else None


def update_scan_status(engine: Engine, symbol: str, **fields: Any) -> None:
    sym = symbol.strip().upper()
    ensure_scan_status_row(engine, sym)
    with engine.begin() as conn:
        conn.execute(
            options_chain_scan_status.update()
            .where(options_chain_scan_status.c.symbol == sym)
            .values(**fields)
        )


def get_scan_status(engine: Engine, symbol: str) -> dict[str, Any] | None:
    sym = symbol.strip().upper()
    ensure_scan_status_row(engine, sym)
    with engine.begin() as conn:
        row = conn.execute(
            select(options_chain_scan_status).where(options_chain_scan_status.c.symbol == sym)
        ).mappings().first()
    return dict(row) if row else None


def replace_contracts(
    engine: Engine,
    *,
    symbol: str,
    scan_run_id: str,
    rows: list[dict[str, Any]],
) -> None:
    sym = symbol.strip().upper()
    now = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(delete(option_chain_contracts).where(option_chain_contracts.c.symbol == sym))
        for row in rows:
            conn.execute(
                option_chain_contracts.insert().values(
                    symbol=sym,
                    scan_run_id=scan_run_id,
                    expiry=str(row["expiry"]),
                    dte=int(row.get("dte") or 0),
                    option_type=str(row["option_type"]),
                    strike=float(row["strike"]),
                    bid=float(row.get("bid") or 0),
                    ask=float(row.get("ask") or 0),
                    last=row.get("last"),
                    mid=float(row.get("mid") or 0),
                    spread_pct=float(row.get("spread_pct") or 0),
                    volume=int(row.get("volume") or 0),
                    open_interest=int(row.get("open_interest") or 0),
                    iv=float(row.get("iv") or 0),
                    delta=float(row.get("delta") or 0),
                    gamma=float(row.get("gamma") or 0),
                    theta=float(row.get("theta") or 0),
                    vega=float(row.get("vega") or 0),
                    status=str(row.get("status") or "reject"),
                    rejection_reason=row.get("rejection_reason"),
                    captured_at=now,
                )
            )


def invalidate_mock_scanner_cache(engine: Engine, symbol: str) -> bool:
    """Drop mock contracts/status so a TWS rescan can replace them with broker data."""
    sym = symbol.strip().upper()
    status = get_scan_status(engine, sym) or {}
    if str(status.get("chain_source") or "") != "mock":
        return False
    clear_scanner_contracts(engine, sym)
    update_scan_status(
        engine,
        sym,
        scanner_status="idle",
        chain_source="none",
        chain_origin="none",
        last_error="mock cache cleared for broker rescan",
        contracts_scanned=0,
        contracts_rejected=0,
        contracts_usable=0,
        underlying_price=None,
        strike_low=None,
        strike_high=None,
        expiries_selected=[],
    )
    return True


def clear_scanner_contracts(engine: Engine, symbol: str) -> None:
    sym = symbol.strip().upper()
    with engine.begin() as conn:
        conn.execute(delete(option_chain_contracts).where(option_chain_contracts.c.symbol == sym))


def recover_stuck_scan_if_needed(engine: Engine, symbol: str, *, max_scan_seconds: int = 60) -> bool:
    """Mark long-running 'scanning' status as failed so a new scan can be enqueued."""
    sym = symbol.strip().upper()
    status = get_scan_status(engine, sym) or {}
    if status.get("scanner_status") != "scanning":
        return False
    started = coerce_utc_datetime(status.get("last_scan_started_at"))
    if not started:
        return False
    age = (datetime.now(UTC) - started).total_seconds()
    if age < max_scan_seconds:
        return False
    update_scan_status(
        engine,
        sym,
        scanner_status="failed",
        last_error="scan timed out; refresh to retry",
    )
    return True


def get_contracts(engine: Engine, symbol: str) -> list[dict[str, Any]]:
    sym = symbol.strip().upper()
    with engine.begin() as conn:
        rows = conn.execute(
            select(option_chain_contracts)
            .where(option_chain_contracts.c.symbol == sym)
            .order_by(option_chain_contracts.c.expiry, option_chain_contracts.c.strike)
        ).mappings()
        return [dict(row) for row in rows]


def chain_data_status(
    scanner_status: str,
    last_completed_at: datetime | None,
    *,
    has_contracts: bool = False,
) -> str:
    if scanner_status in {"failed"}:
        return normalize_chain_data_status("unavailable")
    if scanner_status == "partial":
        return normalize_chain_data_status("partial")
    if scanner_status == "scanning":
        return "degraded"
    if not last_completed_at:
        return normalize_chain_data_status("unavailable")
    completed_utc = coerce_utc_datetime(last_completed_at)
    if not completed_utc:
        return normalize_chain_data_status("unavailable")
    age = (datetime.now(UTC) - completed_utc).total_seconds()
    stale_after = float(settings.options_chain.runtime_max_age_seconds)
    if scanner_status == "idle" and has_contracts:
        return "stale"
    if age > stale_after or scanner_status == "stale":
        return "stale"
    if scanner_status == "fresh":
        return "live"
    return "degraded"


def get_latest_snapshot(engine: Engine, symbol: str) -> dict[str, Any]:
    sym = symbol.strip().upper()
    status = get_scan_status(engine, sym) or {}
    contracts = get_contracts(engine, sym)
    completed = coerce_utc_datetime(status.get("last_scan_completed_at"))
    data_status = chain_data_status(
        str(status.get("scanner_status", "idle")),
        completed,
        has_contracts=bool(contracts),
    )
    chain_source = str(status.get("chain_source") or "none")
    if chain_source == "mock":
        data_status = "mock"
    return {
        "symbol": sym,
        "contracts": contracts,
        "scan_status": status,
        "data_status": data_status,
        "chain_source": chain_source,
        "as_of": datetime.now(UTC),
    }
