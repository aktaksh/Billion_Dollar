from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.indicators import IndicatorSnapshot
from src.levels import LevelSet


Bias = Literal["Bullish", "Bearish", "Neutral"]
Confidence = Literal["High", "Medium", "Low"]
Action = Literal["bull_call_spread", "bear_put_spread", "no_trade"]


@dataclass
class ScoreResult:
    bullish_score: int
    bearish_score: int
    intraday_timing_bull: int
    intraday_timing_bear: int
    bias: Bias
    confidence: Confidence
    action: Action
    invalid_conditions: list[str] = field(default_factory=list)
    daily_checks: dict[str, bool] = field(default_factory=dict)
    intraday_checks: dict[str, bool] = field(default_factory=dict)


def _near_support(price: float, supports: list[float], tol_pct: float = 0.01) -> bool:
    if not supports:
        return False
    return any(abs(price - s) / price <= tol_pct or price > s for s in supports if s > 0)


def _rejects_resistance(price: float, resistances: list[float], tol_pct: float = 0.01) -> bool:
    if not resistances:
        return False
    nearest = min(resistances, key=lambda r: abs(r - price))
    return price < nearest and abs(nearest - price) / price <= tol_pct


def score_setup(
    daily: IndicatorSnapshot,
    intraday: IndicatorSnapshot,
    levels: LevelSet,
) -> ScoreResult:
    invalid: list[str] = []
    daily_checks: dict[str, bool] = {}
    intraday_checks: dict[str, bool] = {}

    def _chk(name: str, cond: bool, checks: dict[str, bool]) -> bool:
        checks[name] = cond
        return cond

    bull = 0
    if _chk("close_gt_ema20", daily.ema20 is not None and daily.close > daily.ema20, daily_checks):
        bull += 1
    if _chk("ema20_gt_ema50", daily.ema20 is not None and daily.ema50 is not None and daily.ema20 > daily.ema50, daily_checks):
        bull += 1
    if _chk("ema50_gt_sma200", daily.ema50 is not None and daily.sma200 is not None and daily.ema50 > daily.sma200, daily_checks):
        bull += 1
    if _chk("rsi_gt_50", daily.rsi14 is not None and daily.rsi14 > 50, daily_checks):
        bull += 1
    if _chk("macd_gt_signal", daily.macd_line is not None and daily.macd_signal is not None and daily.macd_line > daily.macd_signal, daily_checks):
        bull += 1
    if _chk("macd_expanding", daily.macd_expanding, daily_checks):
        bull += 1
    above_week = levels.prev_week_high is not None and daily.close > levels.prev_week_high
    hold_support = _near_support(daily.close, levels.supports)
    if _chk("above_week_high_or_support", above_week or hold_support, daily_checks):
        bull += 1

    bear = 0
    if _chk("close_lt_ema20", daily.ema20 is not None and daily.close < daily.ema20, daily_checks):
        bear += 1
    if _chk("ema20_lt_ema50", daily.ema20 is not None and daily.ema50 is not None and daily.ema20 < daily.ema50, daily_checks):
        bear += 1
    if _chk("rsi_lt_50", daily.rsi14 is not None and daily.rsi14 < 50, daily_checks):
        bear += 1
    if _chk("macd_lt_signal", daily.macd_line is not None and daily.macd_signal is not None and daily.macd_line < daily.macd_signal, daily_checks):
        bear += 1
    if _chk("macd_weakening", daily.macd_weakening, daily_checks):
        bear += 1
    reject_res = _rejects_resistance(daily.close, levels.resistances)
    below_week = levels.prev_week_low is not None and daily.close < levels.prev_week_low
    if _chk("reject_res_or_break_support", reject_res or below_week, daily_checks):
        bear += 1

    it_bull = 0
    if _chk("ema9_gt_ema21", intraday.ema9 is not None and intraday.ema21 is not None and intraday.ema9 > intraday.ema21, intraday_checks):
        it_bull += 1
    if _chk("close_gt_ema21", intraday.ema21 is not None and intraday.close > intraday.ema21, intraday_checks):
        it_bull += 1
    if _chk("intra_rsi_gt_50", intraday.rsi14 is not None and intraday.rsi14 > 50, intraday_checks):
        it_bull += 1
    if _chk("intra_macd_improving", intraday.macd_expanding, intraday_checks):
        it_bull += 1

    it_bear = 0
    if intraday.ema9 is not None and intraday.ema21 is not None and intraday.ema9 < intraday.ema21:
        it_bear += 1
    if intraday.ema21 is not None and intraday.close < intraday.ema21:
        it_bear += 1
    if intraday.rsi14 is not None and intraday.rsi14 < 50:
        it_bear += 1
    if intraday.macd_weakening:
        it_bear += 1

    bullish_setup = bull >= 7 and bear <= 3 and it_bull >= 3
    bearish_setup = bear >= 6 and bull <= 4 and it_bear >= 3

    if bullish_setup and bearish_setup:
        bias: Bias = "Neutral"
        action: Action = "no_trade"
        invalid.append("Mixed bullish and bearish daily signals")
    elif bullish_setup:
        bias = "Bullish"
        action = "bull_call_spread"
    elif bearish_setup:
        bias = "Bearish"
        action = "bear_put_spread"
    else:
        bias = "Neutral"
        action = "no_trade"
        if bull >= 5 and bear >= 5:
            invalid.append("Mixed signal — scores too close")

    margin = abs(bull - bear)
    if action != "no_trade":
        confidence: Confidence = "High" if margin >= 3 else "Medium"
    else:
        confidence = "Low" if margin <= 1 else "Medium"

    return ScoreResult(
        bullish_score=bull,
        bearish_score=bear,
        intraday_timing_bull=it_bull,
        intraday_timing_bear=it_bear,
        bias=bias,
        confidence=confidence,
        action=action,
        invalid_conditions=invalid,
        daily_checks=daily_checks,
        intraday_checks=intraday_checks,
    )
