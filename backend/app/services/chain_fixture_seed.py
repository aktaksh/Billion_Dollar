from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import Engine

from app.config import settings
from app.db import get_engine, init_db
from app.services.options_chain_scanner import _classify_row
from app.services.options_chain_store import replace_contracts, update_scan_status

TESTING_SCAN_NOTE = "testing fixture (not live market data)"
DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "qqq_broker_snapshot.json"


def _contract_row(
    *,
    expiry: str,
    dte: int,
    option_type: str,
    strike: float,
    underlying: float,
) -> dict:
    mid = max(2.0, abs(underlying - strike) * 0.08 + 1.5)
    bid = round(mid - 0.05, 2)
    ask = round(mid + 0.05, 2)
    return {
        "expiry": expiry,
        "dte": dte,
        "option_type": option_type,
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "last": round(mid, 2),
        "mid": round(mid, 2),
        "spread_pct": round((ask - bid) / mid, 4),
        "volume": 800,
        "open_interest": 2500,
        "iv": 0.22,
        "delta": 0.45 if option_type == "call" else -0.45,
        "gamma": 0.02,
        "theta": -0.08,
        "vega": 0.12,
    }


def build_default_fixture() -> dict[str, Any]:
    underlying = 735.0
    expiry = "2026-07-18"
    dte = 30
    strikes = [underlying + offset for offset in range(-20, 25, 5)]
    contracts: list[dict] = []
    for strike in strikes:
        for option_type in ("call", "put"):
            contracts.append(
                _contract_row(
                    expiry=expiry,
                    dte=dte,
                    option_type=option_type,
                    strike=strike,
                    underlying=underlying,
                )
            )
    usable = len(contracts)
    return {
        "symbol": "QQQ",
        "scanner_status": "fresh",
        "chain_source": "broker",
        "underlying_price": underlying,
        "expiries_selected": [expiry],
        "strike_low": min(strikes),
        "strike_high": max(strikes),
        "contracts_scanned": usable,
        "contracts_usable": usable,
        "contracts_rejected": 0,
        "contracts_planned": usable,
        "scan_notes": [TESTING_SCAN_NOTE],
        "contracts": contracts,
    }


def load_fixture(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("fixture must be a JSON object")
    notes = list(raw.get("scan_notes") or [])
    if not notes or any("seeded snapshot" in str(n).lower() for n in notes):
        raw["scan_notes"] = [TESTING_SCAN_NOTE]
    return raw


def seed_testing_fixture(
    engine: Engine,
    *,
    fixture_path: Path | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    path = fixture_path or (DEFAULT_FIXTURE_PATH if DEFAULT_FIXTURE_PATH.is_file() else None)
    payload = load_fixture(path) if path else build_default_fixture()
    sym = (symbol or str(payload.get("symbol") or "QQQ")).strip().upper()
    contracts_in = payload.get("contracts") or []
    if not isinstance(contracts_in, list) or not contracts_in:
        raise ValueError("fixture must include a non-empty contracts array")

    cfg = settings.options_chain
    classified: list[dict] = []
    for row in contracts_in:
        if not isinstance(row, dict):
            continue
        classified.append(_classify_row(dict(row), cfg))

    usable = sum(1 for row in classified if row.get("status") == "usable")
    if usable < 10:
        raise ValueError(f"fixture has only {usable} usable contracts; need at least 10")

    scan_run_id = str(payload.get("scan_run_id") or uuid4())
    now = datetime.now(UTC)
    init_db(engine)
    replace_contracts(engine, symbol=sym, scan_run_id=scan_run_id, rows=classified)
    update_scan_status(
        engine,
        sym,
        scanner_status=str(payload.get("scanner_status") or "fresh"),
        chain_source=str(payload.get("chain_source") or "broker"),
        chain_origin="seeded_fixture",
        last_scan_started_at=now,
        last_scan_completed_at=now,
        last_error=None,
        expiries_selected=list(payload.get("expiries_selected") or []),
        strike_low=payload.get("strike_low"),
        strike_high=payload.get("strike_high"),
        underlying_price=float(payload.get("underlying_price") or classified[0]["strike"]),
        contracts_scanned=int(payload.get("contracts_scanned") or len(classified)),
        contracts_rejected=int(payload.get("contracts_rejected") or max(0, len(classified) - usable)),
        contracts_usable=usable,
        contracts_planned=int(payload.get("contracts_planned") or len(classified)),
        scan_notes=list(payload.get("scan_notes") or [TESTING_SCAN_NOTE]),
        scan_run_id=scan_run_id,
    )
    return {
        "symbol": sym,
        "contracts_written": len(classified),
        "contracts_usable": usable,
        "scan_run_id": scan_run_id,
        "scanner_status": payload.get("scanner_status") or "fresh",
        "chain_source": payload.get("chain_source") or "broker",
        "chain_origin": "seeded_fixture",
    }


def seed_snapshot(*, fixture_path: Path | None = None, symbol: str | None = None) -> dict[str, Any]:
    """CLI-compatible entrypoint."""
    engine = get_engine()
    return seed_testing_fixture(engine, fixture_path=fixture_path, symbol=symbol)
