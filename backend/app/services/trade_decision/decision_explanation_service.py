"""Decision explanation service."""

from __future__ import annotations

from typing import Any


class DecisionExplanationService:
    def why_not(self, analysis: dict[str, Any], strategy_filter: str) -> list[str]:
        reasons: list[str] = []
        daily = analysis.get("daily_indicators") or {}
        if daily.get("macd_line") is not None and daily.get("macd_signal") is not None:
            if daily["macd_line"] < daily["macd_signal"]:
                reasons.append("Daily MACD below signal.")
        resistance = (analysis.get("resistance_levels") or [{}])[0] if analysis.get("resistance_levels") else None
        if resistance and daily.get("close", 0) < resistance.get("price", 0):
            reasons.append("Resistance overhead.")
        if daily.get("macd_expanding"):
            reasons.append("ATR expanding.")
        accepted = [c for c in analysis.get("spread_candidates", []) if c.get("status") == "Accepted"]
        if not accepted:
            reasons.append("Spread liquidity below threshold.")
        if strategy_filter == "WAIT":
            reasons.append("Market regime strategy filter is WAIT.")
        for note in analysis.get("risk_notes") or []:
            if "fed" in note.lower() or "fomc" in note.lower():
                reasons.append("Fed meeting noted in risk flags.")
                break
        return reasons[:8]

    def summary_paragraph(self, decision: str, reasons: list[str]) -> str:
        parts = reasons[:3]
        if decision == "WAIT":
            parts.append("No high-quality spread currently satisfies liquidity and technical filters.")
            parts.append("Wait for confirmation above resistance or breakdown below support.")
        return "\n\n".join(parts)
