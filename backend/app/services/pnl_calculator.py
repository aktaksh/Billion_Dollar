from __future__ import annotations

from datetime import UTC, date, datetime


def spread_entry_value(debit: float, quantity: int = 1) -> float:
    return round(debit * 100.0 * quantity, 2)


def mark_debit_spread(long_mid: float, short_mid: float, quantity: int = 1) -> float:
    return round(max(0.0, (long_mid - short_mid) * 100.0 * quantity), 2)


def unrealized_pnl(entry_value: float, current_value: float) -> float:
    return round(current_value - entry_value, 2)


def percent_return(pnl: float, max_loss: float) -> float:
    if max_loss <= 0:
        return 0.0
    return round((pnl / max_loss) * 100.0, 2)


def max_profit_remaining(current_value: float, max_profit: float, entry_value: float) -> float:
    return round(max(0.0, max_profit - (current_value - entry_value)), 2)


from app.utils.expiry_format import normalize_expiry_iso


def is_expired(expiry_date: str, *, as_of: date | None = None) -> bool:
    today = as_of or datetime.now(UTC).date()
    try:
        exp = date.fromisoformat(normalize_expiry_iso(expiry_date))
    except ValueError:
        return False
    return exp < today


def dte_remaining(expiry_date: str, *, as_of: date | None = None) -> int:
    today = as_of or datetime.now(UTC).date()
    try:
        exp = date.fromisoformat(normalize_expiry_iso(expiry_date))
    except ValueError:
        return 0
    return max(0, (exp - today).days)
