"""Symbol <-> company-name registry used for primary-ticker detection.

Seeded from the Market Intelligence watchlist defaults and extensible at
runtime from the DB-backed watchlist (see ``load_from_watchlist``).
"""

from __future__ import annotations

import re
import threading

_COMPANY_SUFFIX_RE = re.compile(
    r"\b(inc\.?|incorporated|corp\.?|corporation|co\.?|company|ltd\.?|limited|plc|holdings?|technologies|group)\b",
    re.IGNORECASE,
)
_NON_WORD_RE = re.compile(r"[^\w\s]")


def _short_name(company: str) -> str:
    """Strip common corporate suffixes to get a matchable short name, e.g.
    'NVIDIA Corporation' -> 'NVIDIA'."""
    text = _NON_WORD_RE.sub(" ", company)
    text = _COMPANY_SUFFIX_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


class TickerRegistry:
    """Thread-safe symbol -> company-name(s) lookup."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._symbol_to_company: dict[str, str] = {}
        self._symbol_to_short: dict[str, str] = {}

    def register(self, symbol: str, company: str) -> None:
        sym = symbol.strip().upper()
        if not sym or not company:
            return
        with self._lock:
            self._symbol_to_company[sym] = company
            self._symbol_to_short[sym] = _short_name(company)

    def load_from_watchlist(self, rows: list[dict]) -> None:
        for row in rows:
            sym = row.get("symbol")
            company = row.get("company")
            if sym and company and company != "—":
                self.register(sym, company)

    def company_name(self, symbol: str) -> str | None:
        return self._symbol_to_company.get(symbol.strip().upper())

    def short_name(self, symbol: str) -> str | None:
        return self._symbol_to_short.get(symbol.strip().upper())

    def all_symbols(self) -> list[str]:
        return list(self._symbol_to_company.keys())

    def find_company_mentioned(self, text: str, *, exclude: str | None = None) -> str | None:
        """Return a registered symbol other than `exclude` whose short company
        name appears in `text`, or None if none found. Used to detect that a
        headline's clear subject is a *different* known company."""
        if not text:
            return None
        excl = (exclude or "").strip().upper()
        text_lower = text.lower()
        for sym, short in self._symbol_to_short.items():
            if sym == excl or not short or len(short) < 3:
                continue
            if short.lower() in text_lower:
                return sym
        return None


_default_registry: TickerRegistry | None = None
_default_lock = threading.Lock()


def get_default_registry() -> TickerRegistry:
    """Module-level singleton seeded from watchlist defaults on first use."""
    global _default_registry
    with _default_lock:
        if _default_registry is None:
            _default_registry = TickerRegistry()
            try:
                from app.services.market_intelligence.watchlist_defaults import DEFAULT_WATCHLIST

                for sym, company, _sector, _pri in DEFAULT_WATCHLIST:
                    _default_registry.register(sym, company)
            except Exception:
                pass
        return _default_registry
