from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

OptionType = Literal["call", "put"]


@dataclass
class LegFilterDiagnostics:
    raw_contracts: int = 0
    usable_contracts: int = 0
    rejected_for_bad_bid_ask: int = 0
    rejected_for_spread: int = 0
    rejected_for_far_strike: int = 0
    rejected_for_malformed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "raw_contracts": self.raw_contracts,
            "usable_contracts": self.usable_contracts,
            "rejected_for_bad_bid_ask": self.rejected_for_bad_bid_ask,
            "rejected_for_spread": self.rejected_for_spread,
            "rejected_for_far_strike": self.rejected_for_far_strike,
            "rejected_for_malformed": self.rejected_for_malformed,
        }


def _spread_pct(bid: float, ask: float) -> float:
    if bid <= 0 or ask <= 0:
        return 1.0
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 1.0
    return max(0.0, (ask - bid) / mid)


def _strike_window(
    underlying_price: float,
    *,
    strikes_below: int,
    strikes_above: int,
    strike_interval: float,
) -> tuple[float, float]:
    low = underlying_price - (strikes_below * strike_interval)
    high = underlying_price + (strikes_above * strike_interval)
    return max(0.01, low), high


def filter_usable_legs(
    option_chain: list[dict[str, Any]],
    *,
    underlying_price: float,
    max_spread_pct: float,
    strikes_below: int = 8,
    strikes_above: int = 12,
    strike_interval: float = 5.0,
) -> tuple[list[dict[str, Any]], LegFilterDiagnostics]:
    """Return chain rows that pass bid/ask, spread, and near-spot strike filters."""
    diag = LegFilterDiagnostics(raw_contracts=len(option_chain))
    usable: list[dict[str, Any]] = []
    strike_low, strike_high = _strike_window(
        underlying_price,
        strikes_below=strikes_below,
        strikes_above=strikes_above,
        strike_interval=strike_interval,
    )

    for row in option_chain:
        try:
            expiry = str(row["expiry"]).strip()
            dte = int(row["dte"])
            option_type = str(row["option_type"]).strip().lower()
            strike = float(row["strike"])
            bid = float(row.get("bid", 0.0))
            ask = float(row.get("ask", 0.0))
        except (KeyError, TypeError, ValueError):
            diag.rejected_for_malformed += 1
            continue

        if not expiry or dte < 0 or strike <= 0 or option_type not in {"call", "put"}:
            diag.rejected_for_malformed += 1
            continue

        if bid <= 0 or ask <= 0 or ask < bid:
            diag.rejected_for_bad_bid_ask += 1
            continue

        spread = _spread_pct(bid, ask)
        if spread > max_spread_pct:
            diag.rejected_for_spread += 1
            continue

        if strike < strike_low or strike > strike_high:
            diag.rejected_for_far_strike += 1
            continue

        normalized = dict(row)
        normalized["expiry"] = expiry
        normalized["dte"] = dte
        normalized["option_type"] = option_type
        normalized["strike"] = strike
        normalized["bid"] = bid
        normalized["ask"] = ask
        normalized["volume"] = int(row.get("volume") or 0)
        normalized["open_interest"] = int(row.get("open_interest") or 0)
        normalized["delta"] = float(row.get("delta") or 0.0)
        normalized["gamma"] = float(row.get("gamma") or 0.0)
        normalized["theta"] = float(row.get("theta") or 0.0)
        normalized["vega"] = float(row.get("vega") or 0.0)
        normalized["iv"] = float(row.get("iv") or 0.0)
        normalized["spread_pct"] = spread
        usable.append(normalized)

    diag.usable_contracts = len(usable)
    return usable, diag
