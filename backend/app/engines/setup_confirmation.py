from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.engines.options_risk_rules import rule

Direction = Literal["bullish", "bearish"]
SetupStatus = Literal["confirmed", "mixed", "conflict"]
Regime = Literal["risk_on", "risk_off", "neutral"]


@dataclass(frozen=True)
class SetupEvaluation:
    setup_status: SetupStatus
    conditions: dict[str, bool]
    price: float
    vwap: float
    ema_20: float
    ema_20_slope: float
    rsi_14: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "setup_status": self.setup_status,
            "conditions": self.conditions,
            "price": self.price,
            "vwap": self.vwap,
            "ema_20": self.ema_20,
            "ema_20_slope": self.ema_20_slope,
            "rsi_14": self.rsi_14,
        }


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def evaluate_setup_status(
    *,
    direction: Direction,
    price: float,
    vwap: float,
    ema_20: float,
    ema_20_slope: float,
    rsi_14: float,
) -> SetupEvaluation:
    """Evaluate directional setup for 2–4 week swing debit spreads."""
    if direction == "bullish":
        conditions = {
            "price_above_vwap": price > vwap,
            "price_above_ema20": price > ema_20,
            "ema20_slope_non_negative": ema_20_slope >= 0,
            "rsi_in_range": 45.0 <= rsi_14 <= 70.0,
        }
        if all(conditions.values()):
            status: SetupStatus = "confirmed"
        elif not conditions["price_above_vwap"] and not conditions["price_above_ema20"]:
            status = "conflict"
        else:
            status = "mixed"
    else:
        conditions = {
            "price_below_vwap": price < vwap,
            "price_below_ema20": price < ema_20,
            "ema20_slope_non_positive": ema_20_slope <= 0,
            "rsi_in_range": 30.0 <= rsi_14 <= 55.0,
        }
        if all(conditions.values()):
            status = "confirmed"
        elif not conditions["price_below_vwap"] and not conditions["price_below_ema20"]:
            status = "conflict"
        else:
            status = "mixed"

    return SetupEvaluation(
        setup_status=status,
        conditions=conditions,
        price=price,
        vwap=vwap,
        ema_20=ema_20,
        ema_20_slope=ema_20_slope,
        rsi_14=rsi_14,
    )


def setup_confirmation_score(setup_status: SetupStatus) -> float:
    if setup_status == "confirmed":
        return 100.0
    if setup_status == "mixed":
        return 55.0
    return 0.0


def breakeven_distance_score(distance_pct: float, *, ideal_low: float = 0.02, ideal_high: float = 0.04) -> float:
    """Peak score when breakeven is 2–4% from underlying; decay outside band."""
    if ideal_low <= distance_pct <= ideal_high:
        return 100.0
    if distance_pct < ideal_low:
        if ideal_low <= 0:
            return 0.0
        return max(0.0, min(100.0, (distance_pct / ideal_low) * 100.0))
    # distance_pct > ideal_high
    span = max(0.01, 0.10 - ideal_high)
    return max(0.0, min(100.0, 100.0 - ((distance_pct - ideal_high) / span) * 100.0))


def apply_regime_gate(
    *,
    risk_status: str,
    direction: Direction,
    regime: str,
    setup_status: SetupStatus,
    reasons: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Downgrade allow to override_required when regime conflicts with direction."""
    if risk_status in {"reject", "watch_only"}:
        return risk_status, reasons

    normalized_regime = str(regime or "neutral").strip().lower()
    if normalized_regime == "risk_off" and direction == "bullish" and setup_status != "confirmed":
        reasons = [r for r in reasons if r.get("rule_id") != "OPT-PASS-000"]
        reasons.append(rule("REGIME_CONFLICT", "Risk-off regime; bullish setup not confirmed", "override_required"))
        return "override_required", reasons

    if normalized_regime == "risk_on" and direction == "bearish" and setup_status != "confirmed":
        reasons = [r for r in reasons if r.get("rule_id") != "OPT-PASS-000"]
        reasons.append(rule("REGIME_CONFLICT", "Risk-on regime; bearish setup not confirmed", "override_required"))
        return "override_required", reasons

    return risk_status, reasons


def apply_setup_conflict_gate(
    *,
    risk_status: str,
    setup_status: SetupStatus,
    reasons: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    if setup_status != "conflict":
        return risk_status, reasons
    if risk_status == "reject":
        return risk_status, reasons
    reasons = [r for r in reasons if r.get("rule_id") != "OPT-PASS-000"]
    reasons.append(rule("SETUP-CONFLICT", "Directional setup conflicts with trade bias", "watch_only"))
    return "watch_only", reasons


def apply_breakeven_gate(
    *,
    risk_status: str,
    breakeven_distance_pct: float,
    max_breakeven_distance_pct: float,
    reasons: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    if risk_status in {"reject", "watch_only"}:
        return risk_status, reasons
    if breakeven_distance_pct <= max_breakeven_distance_pct:
        return risk_status, reasons
    reasons = [r for r in reasons if r.get("rule_id") != "OPT-PASS-000"]
    reasons.append(
        rule(
            "BREAKEVEN_TOO_FAR",
            f"Breakeven {breakeven_distance_pct:.1%} from spot exceeds {max_breakeven_distance_pct:.1%} limit",
            "watch_only",
        )
    )
    return "watch_only", reasons
