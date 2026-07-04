from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.pnl_calculator import mark_debit_spread, percent_return, spread_entry_value, unrealized_pnl
from app.utils.expiry_format import dte_from_expiry, normalize_expiry_iso


@dataclass
class SpreadValuation:
    current_spread_value: float
    entry_value: float
    unrealized_pnl: float
    percent_return: float
    max_profit: float
    max_loss: float
    max_profit_remaining: float
    distance_to_max_profit_pct: float
    breakeven: float
    breakeven_distance: float
    distance_to_long_strike: float
    distance_to_short_strike: float
    days_remaining: int
    underlying_price: float
    long_mid: float
    short_mid: float


class SpreadValuationService:
    def value_spread(
        self,
        *,
        strategy_type: str,
        long_strike: float,
        short_strike: float,
        quantity: int,
        entry_debit: float | None,
        entry_credit: float | None,
        long_mid: float,
        short_mid: float,
        underlying_price: float,
        expiry: str,
        is_debit: bool | None = None,
    ) -> SpreadValuation:
        qty = max(1, quantity)
        expiry_iso = normalize_expiry_iso(expiry)
        debit = float(entry_debit or 0)
        credit = float(entry_credit or 0)
        if is_debit is None:
            is_debit = "Bull Call" in strategy_type or "Bear Put" in strategy_type

        width = abs(long_strike - short_strike)
        if is_debit:
            entry_per = debit
            max_loss = round(debit * 100 * qty, 2)
            max_profit = round(max(0.0, (width - debit) * 100 * qty), 2)
            breakeven = long_strike + debit if "Call" in strategy_type else long_strike - debit
        else:
            entry_per = credit
            max_loss = round(max(0.0, (width - credit) * 100 * qty), 2)
            max_profit = round(credit * 100 * qty, 2)
            breakeven = short_strike + credit if "Call" in strategy_type else short_strike - credit

        entry_value = spread_entry_value(entry_per, qty) if is_debit else -spread_entry_value(entry_per, qty)
        current_value = mark_debit_spread(long_mid, short_mid, qty)
        if not is_debit:
            current_value = -current_value
        pnl = unrealized_pnl(abs(entry_value), abs(current_value)) if is_debit else unrealized_pnl(abs(entry_value), abs(current_value))
        if not is_debit:
            pnl = -pnl if current_value < entry_value else pnl
        pct = percent_return(pnl, max_loss if max_loss > 0 else 1.0)
        max_profit_remaining = max(0.0, max_profit - max(0.0, pnl))
        progress = (pnl / max_profit * 100.0) if max_profit > 0 else 0.0
        progress = max(0.0, min(100.0, progress))

        return SpreadValuation(
            current_spread_value=round(abs(current_value), 2),
            entry_value=round(abs(entry_value), 2),
            unrealized_pnl=round(pnl, 2),
            percent_return=round(pct, 2),
            max_profit=max_profit,
            max_loss=max_loss,
            max_profit_remaining=round(max_profit_remaining, 2),
            distance_to_max_profit_pct=round(progress, 1),
            breakeven=round(breakeven, 2),
            breakeven_distance=round(abs(underlying_price - breakeven), 2),
            distance_to_long_strike=round(abs(underlying_price - long_strike), 2),
            distance_to_short_strike=round(abs(underlying_price - short_strike), 2),
            days_remaining=dte_from_expiry(expiry_iso),
            underlying_price=underlying_price,
            long_mid=long_mid,
            short_mid=short_mid,
        )

    def apply_market_snapshot(self, leg: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
        out = dict(leg)
        out["bid"] = _field(snapshot, "84", "bid")
        out["ask"] = _field(snapshot, "86", "ask")
        out["last"] = _field(snapshot, "31", "last")
        bid = out.get("bid") or 0
        ask = out.get("ask") or 0
        last = out.get("last") or 0
        out["mid"] = round((bid + ask) / 2, 4) if bid and ask else last
        out["iv"] = _field(snapshot, "7633", "iv")
        out["delta"] = _field(snapshot, "7308", "delta")
        out["gamma"] = _field(snapshot, "7309", "gamma")
        out["theta"] = _field(snapshot, "7310", "theta")
        out["vega"] = _field(snapshot, "7311", "vega")
        out["volume"] = _field(snapshot, "87", "volume")
        out["open_interest"] = _field(snapshot, "7638", "open_interest")
        return out


def _field(snapshot: dict[str, Any], cp_key: str, plain_key: str) -> float | None:
    val = snapshot.get(cp_key)
    if val is None:
        val = snapshot.get(plain_key)
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
