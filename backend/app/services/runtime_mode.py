from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.engine import Engine

from app.config import settings
from app.db import app_runtime_settings

RuntimeMode = Literal["production", "testing"]
ChainOrigin = Literal["none", "seeded_fixture", "broker_live"]

RUNTIME_MODE_KEY = "runtime_mode"
VALID_MODES: frozenset[str] = frozenset({"production", "testing"})


def _normalize_mode(value: str | None) -> RuntimeMode:
    normalized = str(value or "production").strip().lower()
    if normalized not in VALID_MODES:
        return "production"
    return normalized  # type: ignore[return-value]


def get_runtime_mode(engine: Engine) -> RuntimeMode:
    with engine.begin() as conn:
        row = conn.execute(
            select(app_runtime_settings.c.value).where(app_runtime_settings.c.key == RUNTIME_MODE_KEY)
        ).first()
    if row:
        return _normalize_mode(row[0])
    return _normalize_mode(os.environ.get("BILLION_DOLLAR_RUNTIME_MODE"))


def set_runtime_mode(engine: Engine, mode: str) -> RuntimeMode:
    normalized = _normalize_mode(mode)
    now = datetime.now(UTC)
    with engine.begin() as conn:
        existing = conn.execute(
            select(app_runtime_settings.c.key).where(app_runtime_settings.c.key == RUNTIME_MODE_KEY)
        ).first()
        if existing:
            conn.execute(
                app_runtime_settings.update()
                .where(app_runtime_settings.c.key == RUNTIME_MODE_KEY)
                .values(value=normalized, updated_at=now)
            )
        else:
            conn.execute(
                app_runtime_settings.insert().values(
                    key=RUNTIME_MODE_KEY,
                    value=normalized,
                    updated_at=now,
                )
            )
    return normalized


def apply_startup_runtime_mode_override(engine: Engine) -> RuntimeMode:
    env_mode = os.environ.get("BILLION_DOLLAR_RUNTIME_MODE")
    if env_mode:
        return set_runtime_mode(engine, env_mode)
    return get_runtime_mode(engine)


def effective_allow_stale_runtime_dev(mode: RuntimeMode) -> bool:
    if mode == "testing":
        return True
    return False


def is_seeded_chain_allowed(mode: RuntimeMode) -> bool:
    return mode == "testing"


def is_production_valid_chain(
    *,
    chain_origin: str,
    chain_source: str = "none",
    contracts_usable: int = 0,
    scanner_status: str = "idle",
    runtime_mode: RuntimeMode | None = None,
) -> bool:
    """True when cached chain data is from a live broker scan with usable contracts."""
    _ = runtime_mode
    _ = scanner_status
    if str(chain_origin or "none").strip().lower() != "broker_live":
        return False
    if str(chain_source or "none").strip().lower() != "broker":
        return False
    return contracts_usable > 0


def runtime_flags_for_symbol(
    engine: Engine,
    *,
    chain_origin: str,
    chain_source: str = "none",
    contracts_usable: int = 0,
    scanner_status: str = "idle",
) -> dict[str, Any]:
    mode = get_runtime_mode(engine)
    allow_stale = effective_allow_stale_runtime_dev(mode)
    return {
        "runtime_mode": mode,
        "allow_stale_runtime_dev": allow_stale,
        "chain_origin": str(chain_origin or "none"),
        "is_production_valid_chain": is_production_valid_chain(
            chain_origin=chain_origin,
            chain_source=chain_source,
            contracts_usable=contracts_usable,
            scanner_status=scanner_status,
            runtime_mode=mode,
        ),
    }


def resolve_allow_stale_runtime_dev(engine: Engine) -> bool:
    mode = get_runtime_mode(engine)
    if mode == "testing":
        return True
    return settings.options_chain.allow_stale_runtime_dev
