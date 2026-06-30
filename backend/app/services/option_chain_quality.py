from __future__ import annotations

from typing import Any


def _parse_row(row: dict[str, Any]) -> tuple[float, float, float] | None:
    try:
        strike = float(row["strike"])
        bid = float(row.get("bid", 0.0))
        ask = float(row.get("ask", 0.0))
        return strike, bid, ask
    except (KeyError, TypeError, ValueError):
        return None


def _is_well_formed_row(row: dict[str, Any]) -> bool:
    try:
        expiry = str(row["expiry"]).strip()
        dte = int(row["dte"])
        option_type = str(row["option_type"]).strip().lower()
        strike = float(row["strike"])
    except (KeyError, TypeError, ValueError):
        return False
    if not expiry or dte < 0 or strike <= 0:
        return False
    return option_type in {"call", "put"}


def _effective_scanner_status(
    scanner_status: str,
    contracts_usable: int,
    min_usable_contracts: int,
    *,
    allow_stale_runtime_dev: bool = False,
    chain_source: str = "",
) -> str:
    if scanner_status == "partial" and contracts_usable >= min_usable_contracts:
        return "partial_with_enough_usable"
    if (
        allow_stale_runtime_dev
        and scanner_status == "stale"
        and chain_source.strip().lower() == "broker"
        and contracts_usable >= min_usable_contracts
    ):
        return "partial_with_enough_usable"
    return scanner_status


def _nearest_strike_distance_pct(option_chain_rows: list[dict[str, Any]], underlying_price: float) -> float | None:
    if underlying_price <= 0:
        return None
    strikes: list[float] = []
    for row in option_chain_rows:
        parsed = _parse_row(row)
        if parsed is None:
            continue
        strike, bid, ask = parsed
        if bid > 0 and ask > 0:
            strikes.append(strike)
    if not strikes:
        return None
    nearest = min(strikes, key=lambda s: abs(s - underlying_price))
    return abs(nearest - underlying_price) / underlying_price


def validate_chain_quality(
    *,
    symbol: str,
    option_chain_rows: list[dict[str, Any]],
    underlying_price: float,
    chain_source: str,
    scanner_status: str,
    data_status: str,
    snapshot_age_seconds: float | None,
    max_runtime_age_seconds: int,
    contracts_usable: int = 0,
    min_usable_contracts: int = 10,
    max_nearest_strike_pct: float = 0.10,
    allow_stale_runtime_dev: bool = False,
    chain_origin: str = "none",
    runtime_mode: str = "production",
) -> tuple[bool, str | None, dict[str, Any]]:
    """Validate scanner option-chain quality before Strategy Builder candidate generation."""
    normalized_data_status = data_status.strip().lower()
    normalized_chain_source = chain_source.strip().lower()
    normalized_scanner_status = scanner_status.strip().lower()
    effective_status = _effective_scanner_status(
        normalized_scanner_status,
        contracts_usable,
        min_usable_contracts,
        allow_stale_runtime_dev=allow_stale_runtime_dev,
        chain_source=normalized_chain_source,
    )

    diagnostics: dict[str, Any] = {
        "symbol": symbol.upper(),
        "underlying_price": underlying_price,
        "chain_source": normalized_chain_source,
        "scanner_status": normalized_scanner_status,
        "effective_scanner_status": effective_status,
        "data_status": normalized_data_status,
        "snapshot_age_seconds": snapshot_age_seconds,
        "contracts_usable": contracts_usable,
        "raw_contracts": len(option_chain_rows),
        "allow_stale_runtime_dev": allow_stale_runtime_dev,
        "chain_origin": str(chain_origin or "none"),
        "runtime_mode": str(runtime_mode or "production"),
    }

    normalized_runtime_mode = runtime_mode.strip().lower()
    normalized_chain_origin = str(chain_origin or "none").strip().lower()
    if normalized_runtime_mode == "production" and normalized_chain_origin == "seeded_fixture":
        return False, "option_chain_quality_failed_seeded_fixture_in_production", diagnostics

    well_formed = [row for row in option_chain_rows if _is_well_formed_row(row)]
    quoted = [
        row
        for row in well_formed
        if (parsed := _parse_row(row)) is not None and parsed[1] > 0 and parsed[2] > 0
    ]
    nearest_pct = _nearest_strike_distance_pct(option_chain_rows, underlying_price)
    diagnostics["well_formed_contracts"] = len(well_formed)
    diagnostics["quoted_contracts"] = len(quoted)
    diagnostics["nearest_strike_distance_pct"] = nearest_pct

    if normalized_data_status == "mock":
        return False, "option_chain_quality_failed_mock_data", diagnostics

    if normalized_chain_source != "broker":
        return False, "option_chain_quality_failed_non_broker", diagnostics

    allowed_scanner_statuses = {"fresh", "partial_with_enough_usable"}
    if effective_status not in allowed_scanner_statuses:
        return False, "option_chain_quality_failed_scanner_status", diagnostics

    if underlying_price <= 0:
        return False, "option_chain_quality_failed_no_underlying", diagnostics

    if not well_formed:
        return False, "option_chain_quality_failed_malformed", diagnostics

    if not quoted:
        return False, "option_chain_quality_failed_no_quotes", diagnostics

    if nearest_pct is not None and nearest_pct > max_nearest_strike_pct:
        return False, "option_chain_quality_failed_far_strikes", diagnostics

    if snapshot_age_seconds is not None and snapshot_age_seconds > max_runtime_age_seconds:
        dev_stale_ok = (
            allow_stale_runtime_dev
            and normalized_chain_source == "broker"
            and contracts_usable >= min_usable_contracts
            and normalized_scanner_status == "stale"
        )
        if not dev_stale_ok:
            return False, "option_chain_quality_failed_stale", diagnostics

    return True, None, diagnostics
