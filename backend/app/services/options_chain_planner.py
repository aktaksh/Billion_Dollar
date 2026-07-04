from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.broker.option_chain_ibkr import filter_strikes_by_pct


@dataclass
class ScanPlan:
    expiries: list[str]
    strikes: list[float]
    strike_low: float
    strike_high: float
    strike_interval: float
    planned_contracts: int
    truncation_notes: list[str] = field(default_factory=list)


def _parse_expiry_dte(expiry: str) -> int | None:
    try:
        expiry_date = datetime.fromisoformat(expiry).date()
    except ValueError:
        if len(expiry) == 8 and expiry.isdigit():
            expiry_date = datetime.strptime(expiry, "%Y%m%d").date()
        else:
            return None
    return max(0, (expiry_date - datetime.now(timezone.utc).date()).days)


def _is_five_dollar_multiple(strike: float) -> bool:
    return abs(round(strike / 5.0) * 5.0 - strike) < 0.01


def _listed_five_dollar_strikes(all_strikes: list[float]) -> list[float]:
    """IBKR-listed strikes that are exact $5 multiples (700, 705 — not 706 or 727)."""
    out: list[float] = []
    seen: set[float] = set()
    for raw in all_strikes:
        strike = round(float(raw), 2)
        if strike in seen:
            continue
        if not _is_five_dollar_multiple(strike):
            continue
        seen.add(strike)
        out.append(strike)
    return sorted(out)


def _select_strikes_around_spot(
    *,
    spot: float,
    listed: list[float],
    below_count: int,
    above_count: int,
) -> list[float]:
    below = [s for s in listed if s < spot]
    above = [s for s in listed if s > spot]
    selected_below = below[-below_count:] if below_count else []
    selected_above = above[:above_count] if above_count else []
    return sorted(set(selected_below + selected_above))


def _planned_contracts(*, strikes: list[float], expiries: list[str]) -> int:
    return len(strikes) * 2 * len(expiries)


def _select_expiries_in_dte_window(
    all_expiries: list[str],
    *,
    min_dte: int,
    max_dte: int,
    max_expiries: int,
) -> list[str]:
    candidates: list[tuple[int, str]] = []
    for expiry in all_expiries:
        dte = _parse_expiry_dte(expiry)
        if dte is None or dte < min_dte or dte > max_dte:
            continue
        candidates.append((dte, expiry))
    candidates.sort(key=lambda item: item[0])
    return [expiry for _, expiry in candidates[:max_expiries]]


def _select_expiries_multi_bucket(
    all_expiries: list[str],
    *,
    buckets: list[tuple[int, int]],
    max_per_bucket: int = 2,
    max_expiries: int = 8,
) -> list[str]:
    """Select expiries across multiple DTE buckets, picking up to max_per_bucket from each."""
    selected: list[str] = []
    seen: set[str] = set()

    for lo, hi in buckets:
        bucket_candidates: list[tuple[int, str]] = []
        for expiry in all_expiries:
            if expiry in seen:
                continue
            dte = _parse_expiry_dte(expiry)
            if dte is None or dte < lo or dte > hi:
                continue
            bucket_candidates.append((dte, expiry))
        bucket_candidates.sort(key=lambda item: item[0])
        for _, exp in bucket_candidates[:max_per_bucket]:
            if len(selected) >= max_expiries:
                break
            selected.append(exp)
            seen.add(exp)

    return selected


def plan_scan_scope(
    *,
    spot: float,
    all_expiries: list[str],
    all_strikes: list[float],
    cfg: Any,
) -> ScanPlan:
    notes: list[str] = []
    interval = float(cfg.strike_interval)
    max_contracts = int(cfg.max_contracts_per_scan)
    allow_exceed = bool(cfg.allow_exceed_max_contracts)
    below_count = int(getattr(cfg, "strikes_below", 8))
    above_count = int(getattr(cfg, "strikes_above", 12))

    expiries: list[str]
    dte_buckets = getattr(cfg, "dte_buckets", None)
    if dte_buckets:
        aggressive = getattr(cfg, "aggressive_mode", False)
        buckets = list(dte_buckets)
        if aggressive:
            agg_bucket = getattr(cfg, "dte_bucket_aggressive", (7, 14))
            buckets.insert(0, agg_bucket)
        max_per_bucket = int(getattr(cfg, "max_expiries_per_bucket", 2))
        expiries = _select_expiries_multi_bucket(
            all_expiries,
            buckets=buckets,
            max_per_bucket=max_per_bucket,
            max_expiries=int(cfg.max_expiries),
        )
    else:
        expiries = _select_expiries_in_dte_window(
            all_expiries,
            min_dte=int(cfg.min_dte),
            max_dte=int(cfg.max_dte),
            max_expiries=int(cfg.max_expiries),
        )

    listed = _listed_five_dollar_strikes(all_strikes)
    pct_range = float(getattr(cfg, "strike_pct_range", 0.0) or 0.0)
    if pct_range > 0:
        listed = filter_strikes_by_pct(listed, spot=spot, pct=pct_range)
    strikes = _select_strikes_around_spot(
        spot=spot,
        listed=listed,
        below_count=below_count,
        above_count=above_count,
    )

    if len(strikes) < below_count + above_count:
        notes.append(
            f"only {len(strikes)} listed $5 strikes around spot "
            f"(wanted {below_count} below + {above_count} above)"
        )

    def _fits() -> bool:
        return allow_exceed or _planned_contracts(strikes=strikes, expiries=expiries) <= max_contracts

    while not _fits() and len(expiries) > 1:
        dropped = expiries.pop()
        notes.append(f"dropped expiry {dropped} to stay under {max_contracts} contracts")

    while not _fits() and (below_count > 0 or above_count > 0):
        if above_count >= below_count and above_count > 0:
            above_count -= 1
            notes.append("removed furthest strike above spot")
        elif below_count > 0:
            below_count -= 1
            notes.append("removed furthest strike below spot")
        else:
            break
        strikes = _select_strikes_around_spot(
            spot=spot,
            listed=listed,
            below_count=below_count,
            above_count=above_count,
        )

    planned = _planned_contracts(strikes=strikes, expiries=expiries)
    if not allow_exceed and planned > max_contracts:
        notes.append(f"warning: planned {planned} still exceeds cap {max_contracts}")

    strike_low = min(strikes) if strikes else spot
    strike_high = max(strikes) if strikes else spot

    return ScanPlan(
        expiries=expiries,
        strikes=strikes,
        strike_low=strike_low,
        strike_high=strike_high,
        strike_interval=interval,
        planned_contracts=planned,
        truncation_notes=notes,
    )
