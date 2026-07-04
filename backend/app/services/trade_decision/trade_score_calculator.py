"""Trade score calculator — weighted component scores."""

from __future__ import annotations

from typing import Any

DEFAULT_WEIGHTS = {
    "trend": 30,
    "momentum": 20,
    "market_regime": 15,
    "volatility": 10,
    "liquidity": 10,
    "risk_reward": 5,
    "macro": 5,
    "news": 5,
    "paper_statistics": 5,
}


class TradeScoreCalculator:
    def __init__(self, weights: dict[str, int] | None = None) -> None:
        self.weights = weights or dict(DEFAULT_WEIGHTS)

    def component_scores(self, analysis: dict[str, Any], regime_scores: dict[str, Any]) -> dict[str, float]:
        daily = analysis.get("daily_indicators") or {}
        checks = (analysis.get("score") or {}).get("daily_checks") or {}
        bullish = analysis.get("bullish_score", 0)
        bearish = analysis.get("bearish_score", 0)

        trend_keys = ["close_gt_ema20", "ema20_gt_ema50", "ema50_gt_sma200", "rsi_gt_50"]
        avail = [k for k in trend_keys if k in checks]
        trend = (sum(1 for k in avail if checks[k]) / len(avail) * 100) if avail else (
            bullish / max(bullish + bearish, 1) * 100
        )

        momentum = 50.0
        if daily.get("macd_line") is not None and daily.get("macd_signal") is not None:
            momentum += 25 if daily["macd_line"] > daily["macd_signal"] else -25

        final_regime = regime_scores.get("final", 0)
        regime = max(0.0, min(100.0, (final_regime + 60) / 120 * 100))

        candidates = [c for c in analysis.get("spread_candidates", []) if c.get("status") == "Accepted"]
        liquidity = max((c.get("liquidity_score", 0) for c in candidates), default=20)
        rr = 40.0
        if candidates:
            best_rr = max(c.get("reward_risk", 0) for c in candidates)
            rr = 90.0 if best_rr >= 2 else 75.0 if best_rr >= 1.5 else 60.0 if best_rr >= 1 else 40.0

        return {
            "trend": round(trend, 1),
            "momentum": round(max(0, min(100, momentum)), 1),
            "market_regime": round(regime, 1),
            "volatility": 55.0,
            "liquidity": round(float(liquidity), 1),
            "risk_reward": rr,
            "macro": 50.0,
            "news": 70.0,
            "paper_statistics": 50.0,
        }

    def weighted_total(self, components: dict[str, float]) -> float:
        key_map = {
            "trend": "trend",
            "momentum": "momentum",
            "market_regime": "market_regime",
            "volatility": "volatility",
            "liquidity": "liquidity",
            "risk_reward": "risk_reward",
            "macro": "macro",
            "news": "news",
            "paper_statistics": "paper_statistics",
        }
        total = 0.0
        for wkey, weight in self.weights.items():
            ckey = key_map.get(wkey, wkey)
            score = components.get(ckey, 50.0)
            total += score * weight / 100
        return round(total, 1)

    def breakdown_rows(self, components: dict[str, float]) -> list[dict[str, Any]]:
        labels = {
            "trend": "Trend",
            "momentum": "Momentum",
            "market_regime": "Market Regime",
            "volatility": "Volatility",
            "liquidity": "Options Liquidity",
            "risk_reward": "Risk/Reward",
            "macro": "Macro Events",
            "news": "News",
            "paper_statistics": "Paper Trading Statistics",
        }
        rows = []
        for key, weight in self.weights.items():
            score = components.get(key, 50.0)
            rows.append({
                "key": key,
                "label": labels.get(key, key),
                "score": round(score),
                "weight": weight,
                "contribution": round(score * weight / 100, 1),
            })
        return rows
