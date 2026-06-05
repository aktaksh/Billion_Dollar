from __future__ import annotations


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


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

