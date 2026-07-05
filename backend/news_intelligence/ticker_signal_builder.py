"""Aggregates `news_events` clusters into per-symbol `ticker_news_signals`
rows (Part 7). Only clusters with `primary_ticker_score >= 60` (the
"qualifying" set) count toward bias/catalyst/risk — weak or ambiguous
attributions are tracked in counts but never surface as the top catalyst."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from news_intelligence.news_config import (
    NEWS_BIAS_BEARISH_THRESHOLD,
    NEWS_BIAS_BULLISH_THRESHOLD,
    NEWS_BIAS_MIXED_MIN_MAGNITUDE,
    PRIMARY_TICKER_MIN_FOR_CATALYST,
)

NO_CATALYST_MESSAGE = "No high-quality ticker-specific catalyst"


def _bias(bullish_sum: float, bearish_sum: float, net: float) -> str:
    if net > NEWS_BIAS_BULLISH_THRESHOLD:
        return "Bullish"
    if net < NEWS_BIAS_BEARISH_THRESHOLD:
        return "Bearish"
    if bullish_sum > NEWS_BIAS_MIXED_MIN_MAGNITUDE and abs(bearish_sum) > NEWS_BIAS_MIXED_MIN_MAGNITUDE:
        return "Mixed"
    return "Neutral"


def _confidence(qualifying_count: int, source_diversity: int) -> str:
    if qualifying_count >= 3 and source_diversity >= 2:
        return "High"
    if qualifying_count >= 1:
        return "Medium"
    return "Low"


def build_ticker_signals(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for c in clusters:
        by_symbol.setdefault(c["symbol"], []).append(c)

    signals: list[dict[str, Any]] = []
    now = datetime.now(UTC)

    for symbol, events in by_symbol.items():
        qualifying = [e for e in events if e["primary_ticker_score"] >= PRIMARY_TICKER_MIN_FOR_CATALYST]

        bullish = [e for e in qualifying if e["impact_score"] > 0]
        bearish = [e for e in qualifying if e["impact_score"] < 0]
        neutral_qualifying = [e for e in qualifying if e["impact_score"] == 0]

        bullish_sum = sum(e["impact_score"] for e in bullish)
        bearish_sum = sum(e["impact_score"] for e in bearish)
        net = max(-100.0, min(100.0, bullish_sum + bearish_sum))

        top_catalyst_event = max(bullish, key=lambda e: e["impact_score"], default=None)
        top_risk_event = min(bearish, key=lambda e: e["impact_score"], default=None)

        quality = sum(e["source_quality_score"] for e in events) / len(events) if events else 0.0
        source_diversity = len({s for e in events for s in (e.get("sources_json") or [])})
        catalyst_strength = max((abs(e["impact_score"]) for e in qualifying), default=0.0)

        latest_times = [e["latest_time"] for e in events if e.get("latest_time")]
        last_updated = max(latest_times) if latest_times else now

        bias = _bias(bullish_sum, bearish_sum, net)
        confidence = _confidence(len(qualifying), source_diversity)

        if bias == "Bullish":
            summary = f"{len(bullish)} bullish catalyst(s) outweigh {len(bearish)} risk event(s)."
        elif bias == "Bearish":
            summary = f"{len(bearish)} risk event(s) outweigh {len(bullish)} bullish catalyst(s)."
        elif bias == "Mixed":
            summary = f"Mixed signals: {len(bullish)} bullish vs {len(bearish)} bearish qualifying catalysts."
        elif events:
            summary = f"{NO_CATALYST_MESSAGE} ({len(events)} lower-confidence item(s) tracked)."
        else:
            summary = "No recent news."

        signals.append(
            {
                "symbol": symbol,
                "news_bias": bias,
                "news_quality_score": round(quality * 100, 1),
                "catalyst_strength_score": round(catalyst_strength, 2),
                "net_impact_score": round(net, 2),
                "bullish_count": len(bullish),
                "bearish_count": len(bearish),
                "neutral_count": len(neutral_qualifying) + max(0, len(events) - len(qualifying)),
                "top_catalyst": top_catalyst_event["title"] if top_catalyst_event else None,
                "top_risk": top_risk_event["title"] if top_risk_event else None,
                "llm_summary": summary,
                "confidence": confidence,
                "last_updated": last_updated,
            }
        )

    return signals
