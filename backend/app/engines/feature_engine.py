from __future__ import annotations

from typing import Any


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _avg(values: list[float], fallback: float = 0.0) -> float:
    return sum(values) / len(values) if values else fallback


def build_symbol_features(
    *,
    ticker: str,
    market_snapshot: dict[str, Any],
    option_chain: list[dict[str, Any]],
    context_snapshot: dict[str, Any],
) -> dict[str, Any]:
    last = _safe_float(market_snapshot.get("last"), 100.0)
    bid = _safe_float(market_snapshot.get("bid"), last * 0.998)
    ask = _safe_float(market_snapshot.get("ask"), last * 1.002)
    volume = max(1.0, _safe_float(market_snapshot.get("volume"), 1_000_000.0))

    spread_pct = 0.0
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2.0
        spread_pct = max(0.0, (ask - bid) / mid) if mid > 0 else 0.0

    call_ivs = [_safe_float(row.get("iv"), 0.25) for row in option_chain if str(row.get("option_type")) == "call"]
    put_ivs = [_safe_float(row.get("iv"), 0.25) for row in option_chain if str(row.get("option_type")) == "put"]
    all_ivs = call_ivs + put_ivs
    iv_mean = _avg(all_ivs, 0.25)
    iv_percentile = max(1.0, min(99.0, ((iv_mean - 0.15) / 0.35) * 100.0))

    deltas = [abs(_safe_float(row.get("delta"), 0.35)) for row in option_chain]
    gammas = [_safe_float(row.get("gamma"), 0.02) for row in option_chain]
    open_interest = [_safe_float(row.get("open_interest"), 1000.0) for row in option_chain]
    option_volume = [_safe_float(row.get("volume"), 300.0) for row in option_chain]

    avg_abs_delta = _avg(deltas, 0.35)
    avg_gamma = _avg(gammas, 0.02)
    oi_score = min(100.0, (_avg(open_interest, 1200.0) / 2500.0) * 100.0)
    vol_score = min(100.0, (_avg(option_volume, 300.0) / 900.0) * 100.0)

    # Deterministic pseudo factors based on microstructure and context.
    trend_score = max(0.0, min(100.0, 62.0 + ((0.01 - spread_pct) * 900.0)))
    momentum_score = max(0.0, min(100.0, 50.0 + ((avg_abs_delta - 0.35) * 120.0)))
    relative_strength_score = max(0.0, min(100.0, 45.0 + ((volume / 1_000_000.0) * 10.0)))
    atr_14 = max(1.0, last * (0.012 + avg_gamma))
    beta_to_spy = max(0.6, min(1.8, 0.95 + (avg_abs_delta * 0.6)))
    beta_to_qqq = max(0.6, min(2.0, 1.0 + (avg_abs_delta * 0.7)))

    event_risk_score = _safe_float(context_snapshot.get("event_risk_score"), 50.0)
    vwap = _safe_float(context_snapshot.get("vwap"), (bid + ask + last) / 3.0 if bid > 0 and ask > 0 else last)
    ema_20 = _safe_float(context_snapshot.get("ema_20"), last * (0.995 + (trend_score - 50.0) * 0.0002))
    ema_20_slope = _safe_float(context_snapshot.get("ema_20_slope"), (trend_score - 50.0) * 0.02)
    rsi_14 = _safe_float(context_snapshot.get("rsi_14"), max(30.0, min(70.0, 50.0 + (momentum_score - 50.0) * 0.4)))

    if event_risk_score >= 60.0 or trend_score < 40.0:
        regime = "risk_off"
    elif trend_score >= 55.0 and event_risk_score < 50.0:
        regime = "risk_on"
    else:
        regime = str(context_snapshot.get("regime") or "neutral").strip().lower()
        if regime not in {"risk_on", "risk_off", "neutral"}:
            regime = "neutral"

    return {
        "ticker": ticker.upper(),
        "last_price": round(last, 4),
        "vwap": round(vwap, 4),
        "ema_20": round(ema_20, 4),
        "ema_20_slope": round(ema_20_slope, 4),
        "rsi_14": round(rsi_14, 2),
        "regime": regime,
        "trend_score": round(trend_score, 2),
        "momentum_score": round(momentum_score, 2),
        "relative_strength_score": round(relative_strength_score, 2),
        "atr_14": round(atr_14, 4),
        "iv_percentile": round(iv_percentile, 2),
        "beta_to_spy": round(beta_to_spy, 4),
        "beta_to_qqq": round(beta_to_qqq, 4),
        "liquidity_composite_score": round((0.55 * oi_score) + (0.45 * vol_score), 2),
        "gamma_pressure_score": round(max(0.0, min(100.0, avg_gamma * 2500.0)), 2),
        "news_score": float(context_snapshot.get("news_score", 0.0)),
        "sector_strength_score": float(context_snapshot.get("sector_strength_score", 50.0)),
        "event_risk_score": float(context_snapshot.get("event_risk_score", 50.0)),
        "overextended_penalty": 0.0,
    }
