from __future__ import annotations

from typing import Any


def replay_candidates_under_scenarios(
    *,
    candidates: list[dict[str, Any]],
    scenarios: list[float],
) -> list[dict[str, Any]]:
    """
    Replays ranked candidates under deterministic underlying return scenarios.
    scenarios are decimal returns (e.g., -0.03, 0.02).
    """
    out: list[dict[str, Any]] = []
    for row in candidates:
        max_profit = float(row.get("max_profit", 0.0))
        max_loss = float(row.get("max_loss", 0.0))
        probability_profit = float(row.get("probability_profit", 0.0))
        expected_value = float(row.get("expected_value", 0.0))
        scenario_pnls: list[float] = []
        for move in scenarios:
            # Directional deterministic approximation.
            directional = 1.0 if str(row.get("direction")) == "bullish" else -1.0
            alignment = 0.5 + (directional * move * 8.0)
            bounded = max(0.0, min(1.0, alignment))
            pnl = (bounded * max_profit) - ((1.0 - bounded) * max_loss)
            scenario_pnls.append(round(pnl, 2))
        avg_replay_pnl = round(sum(scenario_pnls) / len(scenario_pnls), 2) if scenario_pnls else 0.0
        out.append(
            {
                "strategy_type": row.get("strategy_type"),
                "risk_status": row.get("risk_status"),
                "strategy_score": float(row.get("strategy_score", 0.0)),
                "probability_profit": probability_profit,
                "expected_value": expected_value,
                "replay_avg_pnl": avg_replay_pnl,
                "scenario_pnls": scenario_pnls,
            }
        )
    return sorted(out, key=lambda x: (x["replay_avg_pnl"], x["strategy_score"]), reverse=True)
