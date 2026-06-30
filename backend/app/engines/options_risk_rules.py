from __future__ import annotations

from typing import Any


def rule(code: str, message: str, severity: str = "reject") -> dict[str, Any]:
    return {"rule_id": code, "message": message, "severity": severity}


def apply_chain_quality_gate(
    *,
    scanner_status: str,
    data_status: str,
    chain_source: str,
) -> tuple[str, list[dict[str, Any]]]:
    reasons: list[dict[str, Any]] = []
    if chain_source in {"mock", "fallback", "none"}:
        reasons.append(rule("OPT-CHAIN-001", f"Option chain source is {chain_source}", "reject"))
        return "reject", reasons
    if scanner_status in {"stale", "partial", "failed", "idle"}:
        reasons.append(rule("OPT-CHAIN-001", f"Option chain scanner status is {scanner_status}", "reject"))
        return "reject", reasons
    if data_status in {"stale", "partial", "unavailable", "disconnected"}:
        reasons.append(rule("OPT-CHAIN-001", f"Option chain data status is {data_status}", "reject"))
        return "reject", reasons
    return "allow", [rule("OPT-CHAIN-000", "Option chain snapshot quality OK", "allow")]


def apply_risk_rules(
    *,
    strategy_type: str,
    dte: int,
    spread_pct: float,
    open_interest: int,
    volume: int,
    max_loss: float,
    reward_risk: float,
    probability_profit: float,
    gamma_label: str,
    iv_percentile: float,
    reconciliation_mismatch_active: bool,
    thresholds: dict[str, float],
) -> tuple[str, list[dict[str, Any]]]:
    """
    Returns (risk_status, rule_reasons) where risk_status is:
    - allow
    - reject
    - override_required
    """
    reasons: list[dict[str, Any]] = []
    status = "allow"

    if reconciliation_mismatch_active:
        reasons.append(rule("OPT-REC-001", "Reconciliation mismatch active; no new entries", "reject"))
        return "reject", reasons

    if dte < int(thresholds["min_dte"]):
        reasons.append(rule("OPT-DTE-001", f"DTE {dte} below minimum {int(thresholds['min_dte'])}", "reject"))
        status = "reject"

    if spread_pct > thresholds["max_spread_pct"]:
        reasons.append(rule("OPT-LIQ-002", f"Bid/ask spread {spread_pct:.2%} exceeds threshold", "reject"))
        status = "reject"

    if open_interest < int(thresholds["min_open_interest"]):
        reasons.append(rule("OPT-LIQ-001", f"Open interest {open_interest} below threshold", "reject"))
        status = "reject"

    if volume < int(thresholds["min_option_volume"]):
        reasons.append(rule("OPT-LIQ-003", f"Volume {volume} below threshold", "reject"))
        status = "reject"

    if max_loss > thresholds["max_loss_per_trade_usd"]:
        reasons.append(rule("OPT-EXP-001", f"Max loss ${max_loss:.2f} exceeds budget", "reject"))
        status = "reject"

    if reward_risk < thresholds["min_reward_risk"]:
        reasons.append(rule("OPT-RR-001", f"Reward/risk {reward_risk:.2f} below minimum", "reject"))
        status = "reject"

    if probability_profit < thresholds["min_probability_profit"]:
        reasons.append(
            rule(
                "OPT-POP-001",
                f"Probability of profit {probability_profit:.1%} below minimum",
                "reject",
            )
        )
        status = "reject"

    if gamma_label in {"high", "very_high"} and status != "reject":
        reasons.append(rule("OPT-GRK-001", f"Gamma risk is {gamma_label}; override required", "override_required"))
        status = "override_required"

    if iv_percentile >= thresholds["high_iv_percentile"] and strategy_type in {"long_call", "long_put"}:
        reasons.append(
            rule(
                "OPT-IV-001",
                "IV percentile is high; prefer debit spread over naked long option",
                "reject",
            )
        )
        status = "reject"

    if not reasons:
        reasons.append(rule("OPT-PASS-000", "All hard rules passed", "allow"))

    return status, reasons

