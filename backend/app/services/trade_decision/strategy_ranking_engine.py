"""Strategy ranking engine."""

from __future__ import annotations

from typing import Any


class StrategyRankingEngine:
    STRATEGIES = (
        "Bull Call Spread",
        "Bear Put Spread",
        "Bull Put Spread",
        "Bear Call Spread",
        "Iron Condor",
        "WAIT",
    )

    def rank(
        self,
        analysis: dict[str, Any],
        *,
        trend_bull: int,
        trend_bear: int,
        trade_score: float,
        strategy_filter: str,
    ) -> list[dict[str, Any]]:
        bull_trend = trend_bull >= 3
        bear_trend = trend_bear >= 3
        accepted = [c for c in analysis.get("spread_candidates", []) if c.get("status") == "Accepted"]

        scores: dict[str, float] = {
            "Bull Call Spread": 75 if bull_trend else 35,
            "Bear Put Spread": 75 if bear_trend else 30,
            "Bull Put Spread": 55 if bull_trend else 40,
            "Bear Call Spread": 45 if bear_trend else 20,
            "Iron Condor": 60,
            "WAIT": 70 if trade_score < 55 else 45,
        }
        if strategy_filter == "Bull Call Spread":
            scores["Bull Call Spread"] += 10
        elif strategy_filter == "Bear Put Spread":
            scores["Bear Put Spread"] += 10
        elif strategy_filter == "WAIT":
            scores["WAIT"] += 8

        for c in accepted:
            name = str(c.get("strategy", "")).lower()
            if "bull" in name and "call" in name:
                scores["Bull Call Spread"] = max(scores["Bull Call Spread"], 80)
            if "bear" in name and "put" in name:
                scores["Bear Put Spread"] = max(scores["Bear Put Spread"], 80)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top = ranked[0][1] if ranked else 0
        out = []
        for strategy, score in ranked:
            status = "Neutral"
            if score == top and strategy != "WAIT":
                status = "Preferred"
            elif score >= top - 8 and strategy != "WAIT":
                status = "Alternative"
            elif strategy == "WAIT" and trade_score < 60:
                status = "Acceptable"
            elif score < 35:
                status = "Avoid"
            out.append({
                "strategy": strategy,
                "score": round(score),
                "probability": "—",
                "risk": "Medium" if score >= 45 else "High",
                "status": status,
            })
        return out

    def pick_decision(self, ranked: list[dict[str, Any]], trade_score: float) -> str:
        if not ranked or trade_score < 50:
            return "WAIT"
        top = ranked[0]
        if top["strategy"] == "WAIT" and trade_score < 65:
            return "WAIT"
        return str(top["strategy"])
