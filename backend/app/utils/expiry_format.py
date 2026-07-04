from __future__ import annotations

from datetime import UTC, date, datetime


def normalize_expiry_iso(expiry: str | None) -> str:
    """Normalize any expiry string to YYYY-MM-DD (same format used for puts in export)."""
    if not expiry:
        return ""
    raw = str(expiry).strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    if len(raw) == 6 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-15"
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return raw


def expiry_compact(expiry: str) -> str:
    iso = normalize_expiry_iso(expiry)
    if len(iso) == 10 and iso[4] == "-":
        return iso.replace("-", "")
    return iso


def dte_from_expiry(expiry: str, *, as_of: date | None = None) -> int:
    today = as_of or datetime.now(UTC).date()
    try:
        exp = date.fromisoformat(normalize_expiry_iso(expiry))
    except ValueError:
        return 0
    return max(0, (exp - today).days)
