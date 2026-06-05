from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.engine import Engine

from app.engines.decision_builder import build_decision_from_candidate
from app.models import EnrichedRecommendation, StrategyCandidateOut, TradeDecisionOut
from app.services.decision_store import dashboard_summary, get_decision, insert_decision, list_decisions, patch_decision
from app.services.event_store import list_recommendations_view


def _to_decision_out(row: dict[str, Any]) -> TradeDecisionOut:
    return TradeDecisionOut(**{k: v for k, v in row.items() if k in TradeDecisionOut.model_fields})


def save_decision_from_candidate(engine: Engine, payload: dict[str, Any]) -> TradeDecisionOut:
    candidate = payload["candidate"]
    if not isinstance(candidate, StrategyCandidateOut):
        candidate = StrategyCandidateOut(**candidate)
    built = build_decision_from_candidate(
        candidate=candidate,
        symbol=payload["symbol"],
        direction=payload["direction"],
        universe=payload.get("universe"),
        signal_id=payload.get("signal_id"),
        confidence=float(payload.get("confidence", 50.0)),
        edge=float(payload.get("edge", 0.0)),
        market_regime=str(payload.get("market_regime", "unknown")),
        thesis=str(payload.get("thesis", "")),
        feature=payload.get("feature"),
        data_status=str(payload.get("data_status", "mock")),
        broker_status=str(payload.get("broker_status", "disconnected")),
        reconciliation_status=str(payload.get("reconciliation_status", "ok")),
    )
    if payload.get("rejected"):
        built["current_status"] = "rejected"
        built["review_status"] = "reviewed"
        built["final_outcome"] = "not_reviewed"
    row = insert_decision(engine, built)
    return _to_decision_out(row)


def enriched_recommendations(engine: Engine) -> list[EnrichedRecommendation]:
    signals = list_recommendations_view(engine)
    decisions = list_decisions(engine, limit=500)
    by_signal = {str(d.get("signal_id")): d for d in decisions if d.get("signal_id")}
    by_symbol = {}
    for d in decisions:
        sym = str(d.get("symbol", "")).upper()
        if sym and sym not in by_symbol:
            by_symbol[sym] = d
    out: list[EnrichedRecommendation] = []
    for sig in signals:
        dec = by_signal.get(sig.signal_id) or by_symbol.get(sig.ticker.upper())
        strategy = dec.get("strategy_type") if dec else sig.strategy_sleeve.replace("_", " ").title()
        reasons = [
            f"Regime: {sig.regime_label}",
            f"Thesis: {sig.thesis[:120]}" if sig.thesis else "Thesis pending",
            f"Data: {dec.get('data_status') if dec else 'from signal'}",
        ]
        if dec and dec.get("rule_reasons"):
            top = dec["rule_reasons"][0]
            reasons.append(f"Risk: {top.get('message', top.get('rule_code', 'checked'))}")
        out.append(
            EnrichedRecommendation(
                signal_id=sig.signal_id,
                ticker=sig.ticker,
                strategy=str(strategy),
                direction=sig.side if sig.side != "neutral" else "bullish",
                confidence=sig.confidence_total,
                edge=sig.expected_edge_after_cost_usd,
                max_loss=float(dec["max_loss"]) if dec and dec.get("max_loss") is not None else None,
                max_profit=float(dec["max_profit"]) if dec and dec.get("max_profit") is not None else None,
                pop=float(dec["probability_profit"]) if dec and dec.get("probability_profit") is not None else None,
                risk_status=str(dec.get("risk_status", "unknown")) if dec else "unknown",
                decision_status=str(dec.get("current_status", "none")) if dec else "none",
                decision_id=dec.get("decision_id") if dec else None,
                regime_label=sig.regime_label,
                thesis=sig.thesis,
                entry_trigger=str(dec.get("entry_trigger", "not_ready")) if dec else "not_ready",
                invalidation_rule=str(dec.get("invalidation_rule", "not_ready")) if dec else "not_ready",
                liquidity_status="ok" if dec and float(dec.get("liquidity_score") or 0) >= 50 else "check",
                reason_preview=reasons,
            )
        )
    return out


def latest_decision_for_symbol(engine: Engine, symbol: str) -> dict[str, Any] | None:
    rows = list_decisions(engine, symbol=symbol, limit=1)
    return rows[0] if rows else None
