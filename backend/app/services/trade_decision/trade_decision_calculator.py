"""Trade decision calculator — orchestrates score + ranking."""

from __future__ import annotations

from typing import Any

from app.services.market_regime.indicator_helpers import count_trend_checks
from app.services.trade_decision.decision_explanation_service import DecisionExplanationService
from app.services.trade_decision.strategy_ranking_engine import StrategyRankingEngine
from app.services.trade_decision.trade_score_calculator import TradeScoreCalculator


class TradeDecisionCalculator:
    def __init__(self, weights: dict[str, int] | None = None) -> None:
        self._scores = TradeScoreCalculator(weights)
        self._ranking = StrategyRankingEngine()
        self._explainer = DecisionExplanationService()

    def evaluate(self, analysis: dict[str, Any], *, regime_label: str, regime_scores: dict[str, Any], strategy_filter: str) -> dict[str, Any]:
        daily = analysis.get("daily_indicators") or {}
        bull, bear = count_trend_checks(daily)
        components = self._scores.component_scores(analysis, regime_scores)
        trade_score = self._scores.weighted_total(components)

        accepted = [c for c in analysis.get("spread_candidates", []) if c.get("status") == "Accepted"]
        expiry_search = analysis.get("expiry_search") or {}
        force_wait = expiry_search.get("force_wait", False)

        if not accepted and not force_wait:
            force_wait = True

        if force_wait:
            trade_score = min(trade_score, 55)

        ranked = self._ranking.rank(
            analysis,
            trend_bull=bull,
            trend_bear=bear,
            trade_score=trade_score,
            strategy_filter=strategy_filter,
        )

        if force_wait:
            decision = "WAIT"
        else:
            decision = self._ranking.pick_decision(ranked, trade_score)

        why_not = self._explainer.why_not(analysis, strategy_filter)
        if force_wait:
            wait_reason = expiry_search.get("wait_reason", "No valid spread candidates across all scanned expiries.")
            why_not.append(wait_reason)

        return {
            "decision": decision,
            "trade_score": trade_score,
            "confidence": "Low" if force_wait else analysis.get("confidence", "Medium"),
            "market_regime": regime_label,
            "strategy": decision if decision != "WAIT" else analysis.get("suggested_action", "Wait"),
            "reason": self._explainer.summary_paragraph(decision, why_not),
            "risk_level": "High" if trade_score < 45 else "Medium" if trade_score < 70 else "Low",
            "probability": None,
            "summary": f"Decision: {decision}",
            "breakdown": self._scores.breakdown_rows(components),
            "strategy_comparison": ranked,
            "why_not": why_not,
            "force_wait_no_candidates": force_wait,
        }
