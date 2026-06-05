from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import StrategyCandidateOut


def _entry_trigger(*, symbol: str, direction: str, regime: str, feature: dict[str, Any] | None) -> str:
    feat = feature or {}
    spread_pct = float(feat.get("spread_pct", 0.01))
    if spread_pct > 0.015:
        return "No entry trigger yet — wait for spread <= 1.5% and tighter bid/ask"
    if direction == "bullish":
        if regime in {"trend_low_vol", "risk_on"}:
            return f"{symbol}: Pullback to 20 EMA support with volume > 1.2x average, then reclaim prior session VWAP"
        return f"{symbol}: Break above previous day high with volume > 1.5x average"
    if regime in {"trend_low_vol", "risk_on"}:
        return f"{symbol}: Rejection at 20 EMA resistance with rising put volume"
    return f"{symbol}: Break below previous day low with volume > 1.5x average"


def _invalidation_rule(*, symbol: str, direction: str, max_loss: float) -> str:
    if direction == "bullish":
        return (
            f"Close below VWAP; break below 20 EMA; max loss ${max_loss:.2f} breached; "
            "spread liquidity deteriorates; regime shifts to risk_off"
        )
    return (
        f"Close above VWAP; break above 20 EMA; max loss ${max_loss:.2f} breached; "
        "spread liquidity deteriorates; regime shifts to risk_on"
    )


def _profit_plan(*, max_profit: float, breakeven: float) -> str:
    return f"Take 50% at ${max_profit * 0.5:.2f} target; trail remainder; hard exit at breakeven ${breakeven:.2f}"


def build_decision_from_candidate(
    *,
    candidate: StrategyCandidateOut | dict[str, Any],
    symbol: str,
    direction: str,
    universe: str | None,
    signal_id: str | None,
    confidence: float,
    edge: float,
    market_regime: str,
    thesis: str,
    feature: dict[str, Any] | None,
    data_status: str,
    broker_status: str,
    reconciliation_status: str,
    technical_score: float | None = None,
    catalyst_score: float | None = None,
) -> dict[str, Any]:
    row = candidate.model_dump(mode="json") if isinstance(candidate, StrategyCandidateOut) else dict(candidate)
    max_loss = float(row.get("max_loss", 0.0))
    max_profit = float(row.get("max_profit", 0.0))
    breakeven = float(row.get("breakeven", 0.0))
    return {
        "symbol": symbol.upper(),
        "universe": universe,
        "signal_id": signal_id,
        "direction": direction,
        "strategy_type": str(row.get("strategy_type", "unknown")),
        "risk_status": str(row.get("risk_status", "reject")),
        "confidence": confidence,
        "score": float(row.get("strategy_score", 0.0)),
        "edge": edge,
        "market_regime": market_regime,
        "technical_score": technical_score if technical_score is not None else float(row.get("alpha_score", 0.0)),
        "catalyst_score": catalyst_score if catalyst_score is not None else 50.0,
        "liquidity_score": float(row.get("liquidity_score", 0.0)),
        "risk_score": float(row.get("beta_score", 0.0)),
        "max_loss": max_loss,
        "max_profit": max_profit,
        "breakeven": breakeven,
        "probability_profit": float(row.get("probability_profit", 0.0)),
        "expected_value": float(row.get("expected_value", 0.0)),
        "entry_trigger": _entry_trigger(symbol=symbol, direction=direction, regime=market_regime, feature=feature),
        "invalidation_rule": _invalidation_rule(symbol=symbol, direction=direction, max_loss=max_loss),
        "profit_plan": _profit_plan(max_profit=max_profit, breakeven=breakeven),
        "thesis": thesis,
        "rule_reasons": list(row.get("rule_reasons", [])),
        "legs": list(row.get("legs", [])),
        "data_status": data_status,
        "broker_status": broker_status,
        "reconciliation_status": reconciliation_status,
        "current_status": "decision_saved",
        "review_status": "pending",
    }
