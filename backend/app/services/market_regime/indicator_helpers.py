"""Shared indicator scoring helpers — mirrors frontend/lib/marketRegime.ts (Phase 1)."""

from __future__ import annotations

from typing import Any


def macd_bullish(ind: dict[str, Any]) -> bool:
    line = ind.get("macd_line")
    signal = ind.get("macd_signal")
    return line is not None and signal is not None and line > signal


def count_trend_checks(daily: dict[str, Any]) -> tuple[int, int]:
    bull = bear = 0
    close = daily.get("close") or 0
    if daily.get("ema20") is not None:
        if close > daily["ema20"]:
            bull += 1
        elif close < daily["ema20"]:
            bear += 1
    if daily.get("ema20") is not None and daily.get("ema50") is not None:
        if daily["ema20"] > daily["ema50"]:
            bull += 1
        elif daily["ema20"] < daily["ema50"]:
            bear += 1
    if daily.get("ema50") is not None and daily.get("sma200") is not None:
        if daily["ema50"] > daily["sma200"]:
            bull += 1
        elif daily["ema50"] < daily["sma200"]:
            bear += 1
    if daily.get("rsi14") is not None:
        if daily["rsi14"] > 50:
            bull += 1
        elif daily["rsi14"] < 50:
            bear += 1
    return bull, bear


def trend_score_signed(bull: int, bear: int) -> int:
    if bull >= bear:
        return bull * 10
    return -bear * 10


def momentum_score_signed(daily: dict[str, Any], intraday: dict[str, Any]) -> int:
    score = 0
    if macd_bullish(daily):
        score += 15
    elif daily.get("macd_line") is not None and daily.get("macd_signal") is not None:
        score -= 15
    if daily.get("macd_expanding"):
        score += 5
    if daily.get("macd_weakening"):
        score -= 5
    if macd_bullish(intraday):
        score += 5
    elif intraday.get("macd_line") is not None and intraday.get("macd_signal") is not None:
        score -= 5
    return max(-25, min(25, score))


def scale_to_century(value: float, src_min: float, src_max: float) -> float:
    if src_max <= src_min:
        return 0.0
    ratio = (value - src_min) / (src_max - src_min)
    return max(-100.0, min(100.0, ratio * 200.0 - 100.0))


def trend_label_from_checks(bull: int, bear: int) -> str:
    if bull >= 3:
        return "Bullish"
    if bear >= 3:
        return "Bearish"
    return "Neutral"


def signal_label(ind: dict[str, Any]) -> str:
    if macd_bullish(ind):
        rsi = ind.get("rsi14")
        if rsi is not None and rsi > 50:
            return "Buy bias"
        return "Momentum up"
    if ind.get("macd_line") is not None and ind.get("macd_signal") is not None:
        return "Sell bias"
    return "Neutral"
