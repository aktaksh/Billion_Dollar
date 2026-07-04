from __future__ import annotations

from typing import Any


def generate_trade_review(trade: dict[str, Any], *, last_mark_snapshot: dict[str, Any] | None = None) -> dict[str, str]:
    realized = float(trade.get("realized_pnl") or trade.get("unrealized_pnl") or 0.0)
    max_profit = float(trade.get("max_profit") or 0.0)
    max_loss = float(trade.get("max_loss") or 0.0)
    bias = str(trade.get("market_bias") or "Neutral")
    strategy = str(trade.get("strategy_type") or "")

    right: list[str] = []
    wrong: list[str] = []

    if realized > 0:
        right.append(f"Trade closed profitable at ${realized:.2f} ({trade.get('percent_return', 0):.1f}% of max loss).")
    elif realized < 0:
        wrong.append(f"Trade closed at a loss of ${realized:.2f}.")
    else:
        wrong.append("Trade closed near breakeven.")

    if max_profit > 0 and realized >= max_profit * 0.5:
        right.append("Captured a meaningful portion of theoretical max profit.")
    elif max_profit > 0 and realized < 0:
        wrong.append(f"Lost money despite max profit potential of ${max_profit:.2f}.")

    entry_rsi = trade.get("entry_rsi")
    if entry_rsi is not None:
        if strategy.startswith("Bull") and float(entry_rsi) < 40 and realized > 0:
            right.append("Bullish structure worked with oversold RSI at entry.")
        if strategy.startswith("Bear") and float(entry_rsi) > 60 and realized > 0:
            right.append("Bearish structure worked with elevated RSI at entry.")

    indicators = f"Entry bias was {bias} with confidence {trade.get('confidence', 'unknown')}."
    if trade.get("entry_rsi") is not None or trade.get("entry_macd") is not None:
        indicators += f" RSI={trade.get('entry_rsi')}, MACD={trade.get('entry_macd')}."

    regime = f"Strategy type: {strategy}. Exit reason: {trade.get('exit_reason') or 'n/a'}."
    if last_mark_snapshot and last_mark_snapshot.get("snapshot_json"):
        snap = last_mark_snapshot["snapshot_json"]
        if isinstance(snap, dict) and snap.get("bias"):
            regime += f" Last marked bias: {snap.get('bias')}."

    would_recommend = "Unclear — insufficient post-exit analysis."
    if realized > 0:
        would_recommend = f"Yes — {strategy} worked under {bias} conditions at entry."
    elif realized <= -max_loss * 0.5:
        would_recommend = f"No — {strategy} underperformed; review entry timing and liquidity."

    return {
        "what_went_right": " ".join(right) if right else "No clear positive factors identified.",
        "what_went_wrong": " ".join(wrong) if wrong else "No major issues identified.",
        "indicators_agreed": indicators,
        "regime_change": regime,
        "would_recommend_again": would_recommend,
    }
