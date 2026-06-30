from __future__ import annotations

import math
from typing import Literal


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def clamp_pop(value: float) -> float:
    return max(0.05, min(0.80, value))


def probability_profit_long_call(delta: float, debit: float, underlying: float, strike: float) -> float:
    """
    Deterministic POP approximation:
    - Base from call delta
    - Penalize if breakeven is far above underlying
    """
    base = abs(delta)
    breakeven = strike + debit
    distance_ratio = max(0.0, (breakeven - underlying) / max(underlying, 1e-6))
    penalty = distance_ratio * 1.4
    return clamp01(base - penalty)


def probability_profit_long_put(delta: float, debit: float, underlying: float, strike: float) -> float:
    """
    Deterministic POP approximation:
    - Base from put absolute delta
    - Penalize if breakeven is far below underlying
    """
    base = abs(delta)
    breakeven = strike - debit
    distance_ratio = max(0.0, (underlying - breakeven) / max(underlying, 1e-6))
    penalty = distance_ratio * 1.4
    return clamp01(base - penalty)


def probability_profit_bull_call_spread(buy_delta: float, sell_delta: float) -> float:
    # Favor higher buy-delta and lower short-delta.
    return clamp01((abs(buy_delta) * 0.7) + ((1.0 - abs(sell_delta)) * 0.3))


def probability_profit_bear_put_spread(buy_delta: float, sell_delta: float) -> float:
    return clamp01((abs(buy_delta) * 0.7) + ((1.0 - abs(sell_delta)) * 0.3))


def probability_profit_debit_spread_breakeven(
    *,
    underlying: float,
    breakeven: float,
    dte: int,
    iv: float,
    direction: Literal["bullish", "bearish"],
    buy_delta: float = 0.0,
    sell_delta: float = 0.0,
) -> float:
    """Breakeven-distance POP using IV when available; delta fallback otherwise."""
    if iv > 0 and dte > 0 and underlying > 0:
        estimated_move = underlying * iv * math.sqrt(dte / 365.0)
        if estimated_move > 0:
            if direction == "bullish":
                distance = breakeven - underlying
            else:
                distance = underlying - breakeven
            z_like = distance / estimated_move
            return clamp_pop(0.50 - (z_like * 0.30))
    if direction == "bullish":
        return probability_profit_bull_call_spread(buy_delta, sell_delta)
    return probability_profit_bear_put_spread(buy_delta, sell_delta)

