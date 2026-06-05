from __future__ import annotations


def gamma_risk_label(gamma: float, dte: int) -> str:
    # Near expiry gamma is inherently more dangerous.
    scaled = abs(gamma) * (1.5 if dte <= 14 else 1.0)
    if scaled >= 0.08:
        return "very_high"
    if scaled >= 0.05:
        return "high"
    if scaled >= 0.025:
        return "medium"
    return "low"


def gamma_safety_score(gamma: float, dte: int) -> float:
    label = gamma_risk_label(gamma, dte)
    if label == "low":
        return 90.0
    if label == "medium":
        return 70.0
    if label == "high":
        return 45.0
    return 15.0

