from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def classify_paper_outcome(
    *,
    decision: dict[str, Any],
    entry_price: float,
    exit_price: float,
    realized_pnl: float,
    max_drawdown: float,
    entry_trigger_met: bool = True,
    invalidation_hit: bool = False,
    profit_target_hit: bool = False,
    exit_followed_plan: bool = True,
) -> str:
    if not entry_trigger_met:
        return "invalid_entry"
    if not exit_followed_plan and invalidation_hit:
        return "invalid_exit"
    max_loss = float(decision.get("max_loss") or 0.0)
    if invalidation_hit and realized_pnl < 0:
        return "wrong"
    if profit_target_hit and realized_pnl > 0 and exit_followed_plan:
        return "correct"
    if realized_pnl > 0 and not profit_target_hit:
        return "partially_correct"
    if max_loss > 0 and abs(realized_pnl) >= max_loss * 0.9:
        return "wrong"
    if realized_pnl >= 0:
        return "partially_correct"
    return "wrong"


def infer_review_flags(
    *,
    decision: dict[str, Any],
    realized_pnl: float,
    scenario_return: float,
) -> dict[str, Any]:
    direction = str(decision.get("direction", "bullish"))
    directional = 1.0 if direction == "bullish" else -1.0
    aligned = directional * scenario_return > 0
    entry_trigger_met = bool(decision.get("extra", {}).get("entry_trigger_met", True))
    invalidation_hit = bool(decision.get("extra", {}).get("invalidation_hit", realized_pnl < -abs(float(decision.get("max_loss") or 1)) * 0.5))
    profit_target_hit = realized_pnl > float(decision.get("max_profit") or 0) * 0.4
    exit_followed_plan = not invalidation_hit or realized_pnl >= 0
    if not entry_trigger_met:
        outcome = "skipped_trigger_not_met"
    else:
        outcome = classify_paper_outcome(
            decision=decision,
            entry_price=float(decision.get("extra", {}).get("entry_price", 0)),
            exit_price=float(decision.get("extra", {}).get("exit_price", 0)),
            realized_pnl=realized_pnl,
            max_drawdown=float(decision.get("max_drawdown") or 0),
            entry_trigger_met=entry_trigger_met,
            invalidation_hit=invalidation_hit,
            profit_target_hit=profit_target_hit,
            exit_followed_plan=exit_followed_plan,
        )
    return {
        "final_outcome": outcome,
        "entry_trigger_met": entry_trigger_met,
        "invalidation_hit": invalidation_hit,
        "profit_target_hit": profit_target_hit,
        "exit_followed_plan": exit_followed_plan,
        "direction_aligned": aligned,
    }
