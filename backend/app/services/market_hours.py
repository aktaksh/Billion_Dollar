from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def is_us_equity_regular_session(now: datetime | None = None) -> bool:
    """US equity/ETF regular session (Mon–Fri 09:30–16:00 ET)."""
    current = now or datetime.now(_ET)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_ET)
    else:
        current = current.astimezone(_ET)
    if current.weekday() >= 5:
        return False
    session_open = current.replace(hour=9, minute=30, second=0, microsecond=0)
    session_close = current.replace(hour=16, minute=0, second=0, microsecond=0)
    return session_open <= current < session_close


def empty_quotes_reason() -> str:
    if is_us_equity_regular_session():
        return "broker returned empty or zero quotes"
    return "broker returned empty or zero quotes (likely off-hours)"
