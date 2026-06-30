from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

PREFERRED_EXCHANGES = ("SMART", "AMEX")
DEFAULT_MULTIPLIER = 100


@dataclass(frozen=True)
class OptionChainParam:
    exchange: str
    trading_class: str
    multiplier: int
    expirations: tuple[str, ...]
    strikes: tuple[float, ...]


@dataclass
class ChainFetchDiagnostics:
    symbol: str
    underlying_conid: int = 0
    chains_returned: int = 0
    selected_exchange: str = ""
    selected_trading_class: str = ""
    selected_multiplier: int = 0
    selected_expiries: list[str] = field(default_factory=list)
    strike_low: float = 0.0
    strike_high: float = 0.0
    contracts_built: int = 0
    contracts_qualified: int = 0
    contracts_with_bid_ask: int = 0
    contracts_missing_quotes: int = 0
    live_quotes: int = 0
    delayed_quotes: int = 0
    notes: list[str] = field(default_factory=list)

    def log_summary(self) -> None:
        log.info(
            "option_chain_fetch symbol=%s underlying_conid=%s chains_returned=%s "
            "selected exchange=%s tradingClass=%s multiplier=%s "
            "expiries=%s strike_range=[%.2f, %.2f] "
            "built=%s qualified=%s bid_ask=%s missing=%s live=%s delayed=%s notes=%s",
            self.symbol,
            self.underlying_conid,
            self.chains_returned,
            self.selected_exchange,
            self.selected_trading_class,
            self.selected_multiplier,
            self.selected_expiries,
            self.strike_low,
            self.strike_high,
            self.contracts_built,
            self.contracts_qualified,
            self.contracts_with_bid_ask,
            self.contracts_missing_quotes,
            self.live_quotes,
            self.delayed_quotes,
            self.notes or "-",
        )


def _normalize_multiplier(value: Any) -> int:
    if value is None or value == "":
        return DEFAULT_MULTIPLIER
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _normalize_expiry(expiry: str) -> str:
    if len(expiry) == 8 and expiry.isdigit():
        return f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:8]}"
    return expiry


def _expiry_compact(expiry: str) -> str:
    if len(expiry) == 8 and expiry.isdigit():
        return expiry
    return expiry.replace("-", "")


def parse_secdef_option_chains(chains: list[Any]) -> list[OptionChainParam]:
    """Normalize all securityDefinitionOptionParameter callbacks."""
    out: list[OptionChainParam] = []
    for chain in chains or []:
        expirations = tuple(sorted(str(e) for e in (getattr(chain, "expirations", None) or []) if e))
        strikes = tuple(sorted(float(s) for s in (getattr(chain, "strikes", None) or []) if s))
        if not expirations and not strikes:
            continue
        out.append(
            OptionChainParam(
                exchange=str(getattr(chain, "exchange", "") or "").upper(),
                trading_class=str(getattr(chain, "tradingClass", "") or "").upper(),
                multiplier=_normalize_multiplier(getattr(chain, "multiplier", None)),
                expirations=expirations,
                strikes=strikes,
            )
        )
    return out


def select_option_chain(
    chains: list[OptionChainParam],
    *,
    symbol: str,
    preferred_exchanges: tuple[str, ...] = PREFERRED_EXCHANGES,
    trading_class: str | None = None,
    multiplier: int = DEFAULT_MULTIPLIER,
) -> OptionChainParam | None:
    """Pick chain: tradingClass match, multiplier, SMART then AMEX."""
    target_class = (trading_class or symbol).strip().upper()
    candidates = [
        c
        for c in chains
        if c.trading_class == target_class and c.multiplier == multiplier
    ]
    if not candidates:
        candidates = [c for c in chains if c.multiplier == multiplier]
    if not candidates:
        candidates = list(chains)
    if not candidates:
        return None
    for exchange in preferred_exchanges:
        for chain in candidates:
            if chain.exchange == exchange.upper():
                return chain
    return candidates[0]


def expiry_dte(expiry: str, *, today: datetime | None = None) -> int | None:
    ref = (today or datetime.now(timezone.utc)).date()
    iso = _normalize_expiry(expiry)
    try:
        expiry_date = datetime.fromisoformat(iso).date()
    except ValueError:
        compact = _expiry_compact(expiry)
        if len(compact) == 8 and compact.isdigit():
            expiry_date = datetime.strptime(compact, "%Y%m%d").date()
        else:
            return None
    return max(0, (expiry_date - ref).days)


def filter_expiries_by_dte(
    expirations: list[str] | tuple[str, ...],
    *,
    min_dte: int,
    max_dte: int,
) -> list[str]:
    selected: list[tuple[int, str]] = []
    for exp in expirations:
        dte = expiry_dte(exp)
        if dte is None or dte < min_dte or dte > max_dte:
            continue
        selected.append((dte, _normalize_expiry(exp)))
    selected.sort(key=lambda item: item[0])
    return [exp for _, exp in selected]


def filter_strikes_by_pct(
    strikes: list[float] | tuple[float, ...],
    *,
    spot: float,
    pct: float,
) -> list[float]:
    if spot <= 0 or pct <= 0:
        return sorted(float(s) for s in strikes)
    low = spot * (1.0 - pct)
    high = spot * (1.0 + pct)
    return sorted(s for s in (float(x) for x in strikes) if low <= s <= high)


def build_option_contract_specs(
    *,
    symbol: str,
    expiry: str,
    strikes: list[float],
    exchange: str,
    trading_class: str,
    multiplier: int = DEFAULT_MULTIPLIER,
    rights: tuple[str, ...] = ("C", "P"),
) -> list[dict[str, Any]]:
    target = symbol.strip().upper()
    expiry_compact = _expiry_compact(expiry)
    specs: list[dict[str, Any]] = []
    for strike in strikes:
        for right in rights:
            specs.append(
                {
                    "symbol": target,
                    "sec_type": "OPT",
                    "expiry": expiry_compact,
                    "expiry_iso": _normalize_expiry(expiry),
                    "strike": float(strike),
                    "right": right,
                    "exchange": exchange,
                    "trading_class": trading_class,
                    "multiplier": multiplier,
                    "currency": "USD",
                }
            )
    return specs
