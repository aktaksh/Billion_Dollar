from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.indicators import IndicatorSnapshot
from src.levels import LevelSet
from src.options_chain import OptionQuote
from src.report import AnalysisReport
from src.spread_builder import SpreadCandidate

ACTION_LABELS = {
    "bull_call_spread": "Bull call spread",
    "bear_put_spread": "Bear put spread",
    "no_trade": "No trade / wait",
}

STRATEGY_LABELS = {
    "bull_call_spread": "Bull call spread",
    "bear_put_spread": "Bear put spread",
}


def _indicator_dict(snap: IndicatorSnapshot) -> dict[str, Any]:
    data = asdict(snap)
    data["macd_expanding"] = snap.macd_expanding
    data["macd_weakening"] = snap.macd_weakening
    return data


def _level_row(price: float, spot: float, *, kind: str, side: str) -> dict[str, Any]:
    dist = price - spot
    pct = (dist / spot * 100.0) if spot > 0 else 0.0
    return {
        "price": price,
        "kind": kind,
        "side": side,
        "distance_abs": round(dist, 2),
        "distance_pct": round(pct, 2),
    }


def _support_rows(levels: LevelSet, spot: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if levels.prev_week_low is not None:
        rows.append(_level_row(levels.prev_week_low, spot, kind="prev_week_low", side="support"))
    if levels.prev_month_low is not None:
        rows.append(_level_row(levels.prev_month_low, spot, kind="prev_month_low", side="support"))
    for px in levels.swing_lows:
        rows.append(_level_row(px, spot, kind="swing_low", side="support"))
    for px in levels.gap_levels:
        if px <= spot:
            rows.append(_level_row(px, spot, kind="gap_support", side="support"))
    rows.sort(key=lambda r: abs(r["distance_abs"]))
    return rows


def _resistance_rows(levels: LevelSet, spot: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if levels.prev_week_high is not None:
        rows.append(_level_row(levels.prev_week_high, spot, kind="prev_week_high", side="resistance"))
    if levels.prev_month_high is not None:
        rows.append(_level_row(levels.prev_month_high, spot, kind="prev_month_high", side="resistance"))
    for px in levels.swing_highs:
        rows.append(_level_row(px, spot, kind="swing_high", side="resistance"))
    for px in levels.gap_levels:
        if px > spot:
            rows.append(_level_row(px, spot, kind="gap_resistance", side="resistance"))
    rows.sort(key=lambda r: abs(r["distance_abs"]))
    return rows


def _option_quote_row(q: OptionQuote, *, liquid: bool) -> dict[str, Any]:
    return {
        "expiry": q.expiry,
        "dte": q.dte,
        "option_type": q.option_type,
        "strike": q.strike,
        "bid": q.bid,
        "ask": q.ask,
        "last": q.last,
        "mid": round(q.mid, 4),
        "spread_pct": round(q.spread_pct, 4),
        "volume": q.volume,
        "open_interest": q.open_interest,
        "delta": round(q.delta, 4),
        "gamma": round(q.gamma, 4),
        "theta": round(q.theta, 4),
        "vega": round(q.vega, 4),
        "iv": round(q.iv, 4),
        "liquid": liquid,
    }


def _sort_option_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    type_order = {"call": 0, "put": 1}
    return sorted(
        rows,
        key=lambda r: (r["expiry"], type_order.get(r["option_type"], 2), r["strike"]),
    )


def _spread_row(spread: SpreadCandidate) -> dict[str, Any]:
    return {
        "strategy": STRATEGY_LABELS.get(spread.spread_type, spread.spread_type),
        "spread_type": spread.spread_type,
        "expiry": spread.expiry,
        "dte": spread.dte,
        "long_leg": f"{spread.buy_strike:.0f} (δ{spread.buy_delta:.2f})",
        "short_leg": f"{spread.sell_strike:.0f} (δ{spread.sell_delta:.2f})",
        "buy_strike": spread.buy_strike,
        "sell_strike": spread.sell_strike,
        "net_debit": spread.net_debit,
        "max_loss": spread.max_loss,
        "max_profit": spread.max_profit,
        "breakeven": spread.breakeven,
        "reward_risk": spread.reward_risk,
        "probability_of_profit": None,
        "combined_delta": spread.combined_delta,
        "combined_gamma": spread.combined_gamma,
        "combined_theta": spread.combined_theta,
        "combined_vega": spread.combined_vega,
        "bid_ask_quality": spread.bid_ask_quality,
        "open_interest": None,
        "volume": None,
        "liquidity_score": spread.liquidity_score,
        "status": "Accepted",
        "rejection_reason": None,
    }


def _build_reason_summary(report: AnalysisReport) -> str:
    score = report.score
    parts: list[str] = []

    if score.bias == "Bullish":
        parts.append("Trend leans bullish")
    elif score.bias == "Bearish":
        parts.append("Trend leans bearish")
    else:
        parts.append("Trend is mixed / neutral")

    dc = score.daily_checks
    if dc.get("close_gt_ema20") and dc.get("ema20_gt_ema50") and dc.get("ema50_gt_sma200"):
        parts.append("price is above EMA20, EMA50, and SMA200")
    elif dc.get("close_lt_ema20") and dc.get("ema20_lt_ema50"):
        parts.append("price is below key moving averages")

    if dc.get("macd_gt_signal"):
        parts.append("MACD is above signal")
    elif dc.get("macd_lt_signal"):
        parts.append("MACD is below signal")

    if not report.spreads:
        parts.append("no spread passed liquidity filters")

    if score.invalid_conditions:
        parts.append("mixed signals: " + "; ".join(score.invalid_conditions[:2]))

    return ". ".join(parts).capitalize() + "."


def report_to_dict(
    report: AnalysisReport,
    *,
    diagnostics: dict[str, Any] | None = None,
    liquid_options: list[OptionQuote] | None = None,
    raw_options: list[OptionQuote] | None = None,
    expiry_search: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spot = report.underlying_price
    score = report.score
    support_levels = _support_rows(report.levels, spot)
    resistance_levels = _resistance_rows(report.levels, spot)

    liquid_keys = {(q.expiry, q.strike, q.option_type) for q in (liquid_options or [])}
    payload: dict[str, Any] = {
        "timestamp": report.timestamp.isoformat(),
        "symbol": report.symbol,
        "underlying_price": report.underlying_price,
        "bias": score.bias,
        "confidence": score.confidence,
        "suggested_action": ACTION_LABELS.get(score.action, score.action),
        "action": score.action,
        "bullish_score": score.bullish_score,
        "bearish_score": score.bearish_score,
        "reason_summary": _build_reason_summary(report),
        "score": {
            "bullish_score": score.bullish_score,
            "bearish_score": score.bearish_score,
            "intraday_timing_bull": score.intraday_timing_bull,
            "intraday_timing_bear": score.intraday_timing_bear,
            "bias": score.bias,
            "confidence": score.confidence,
            "action": score.action,
            "invalid_conditions": score.invalid_conditions,
            "daily_checks": score.daily_checks,
            "intraday_checks": score.intraday_checks,
        },
        "daily_indicators": _indicator_dict(report.daily),
        "intraday_indicators": _indicator_dict(report.intraday),
        "levels": {
            "prev_week_high": report.levels.prev_week_high,
            "prev_week_low": report.levels.prev_week_low,
            "prev_month_high": report.levels.prev_month_high,
            "prev_month_low": report.levels.prev_month_low,
            "swing_highs": report.levels.swing_highs,
            "swing_lows": report.levels.swing_lows,
            "gap_levels": report.levels.gap_levels,
            "supports": report.levels.supports,
            "resistances": report.levels.resistances,
        },
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "spread_candidates": [_spread_row(s) for s in report.spreads],
        "liquid_options": _sort_option_rows([
            _option_quote_row(q, liquid=True) for q in (liquid_options or [])
        ]),
        "raw_options": _sort_option_rows([
            _option_quote_row(
                q,
                liquid=(q.expiry, q.strike, q.option_type) in liquid_keys,
            )
            for q in (raw_options or [])
        ]),
        "risk_notes": list(report.risk_notes or []),
        "positions_count": report.positions_count,
        "open_orders_count": report.open_orders_count,
        "expiry_search": expiry_search or {},
        "backtest": {
            "available": False,
            "message": "Backtest module not yet populated.",
        },
        "diagnostics": diagnostics or {},
    }
    return payload


def write_latest_analysis(
    report: AnalysisReport,
    *,
    diagnostics: dict[str, Any] | None = None,
    liquid_options: list[OptionQuote] | None = None,
    raw_options: list[OptionQuote] | None = None,
    expiry_search: dict[str, Any] | None = None,
    path: Path,
) -> dict[str, Any]:
    payload = report_to_dict(
        report,
        diagnostics=diagnostics,
        liquid_options=liquid_options,
        raw_options=raw_options,
        expiry_search=expiry_search,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
