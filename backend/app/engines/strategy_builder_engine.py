from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from app.engines.greek_risk_engine import gamma_risk_label, gamma_safety_score
from app.engines.options_risk_rules import apply_risk_rules
from app.engines.probability_engine import (
    probability_profit_bear_put_spread,
    probability_profit_bull_call_spread,
    probability_profit_long_call,
    probability_profit_long_put,
)

Direction = Literal["bullish", "bearish"]
StrategyType = Literal["long_call", "long_put", "bull_call_debit_spread", "bear_put_debit_spread"]


@dataclass
class OptionLeg:
    expiry: str
    dte: int
    option_type: Literal["call", "put"]
    strike: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    delta: float
    gamma: float
    theta: float
    vega: float
    iv: float

    @property
    def spread_pct(self) -> float:
        mid = (self.bid + self.ask) / 2 if (self.bid > 0 and self.ask > 0) else 0.0
        if mid <= 0:
            return 1.0
        return max(0.0, (self.ask - self.bid) / mid)


def _alpha_score(feature: dict[str, Any], direction: Direction) -> float:
    trend = float(feature.get("trend_score", 50.0))
    news = float(feature.get("news_score", 0.0))
    sector = float(feature.get("sector_strength_score", 50.0))
    overextended_penalty = float(feature.get("overextended_penalty", 0.0))

    # Direction-aware alpha tilt.
    directional_bias = 5.0 if direction == "bullish" else 3.0
    raw = (0.5 * trend) + (0.2 * sector) + (news * 10.0) + directional_bias - overextended_penalty
    return max(0.0, min(100.0, raw))


def _beta_score(feature: dict[str, Any]) -> float:
    beta_spy = abs(float(feature.get("beta_to_spy", 1.0)))
    beta_qqq = abs(float(feature.get("beta_to_qqq", 1.0)))
    # Prefer moderate beta for stable swing setups.
    penalty = max(0.0, (beta_spy - 1.4) * 18.0) + max(0.0, (beta_qqq - 1.6) * 15.0)
    return max(0.0, min(100.0, 82.0 - penalty))


def _liquidity_score(spread_pct: float, oi: int, volume: int) -> float:
    spread_score = max(0.0, min(100.0, 100.0 - (spread_pct * 1000.0)))
    oi_score = max(0.0, min(100.0, (oi / 2000.0) * 100.0))
    vol_score = max(0.0, min(100.0, (volume / 500.0) * 100.0))
    return (0.45 * spread_score) + (0.30 * oi_score) + (0.25 * vol_score)


def _trend_score(feature: dict[str, Any]) -> float:
    return max(0.0, min(100.0, float(feature.get("trend_score", 50.0))))


def _iv_score(iv_percentile: float, strategy_type: StrategyType) -> float:
    # Long options prefer cheaper IV; debit spreads tolerate higher IV better.
    if strategy_type in {"long_call", "long_put"}:
        return max(0.0, min(100.0, 100.0 - abs(iv_percentile - 35.0) * 1.6))
    return max(0.0, min(100.0, 100.0 - abs(iv_percentile - 55.0) * 1.0))


def _rr_score(reward_risk: float) -> float:
    return max(0.0, min(100.0, reward_risk * 40.0))


def _pop_score(probability_profit: float) -> float:
    return max(0.0, min(100.0, probability_profit * 100.0))


def _strategy_score(
    *,
    alpha_score: float,
    trend_score: float,
    liquidity_score: float,
    probability_profit_score: float,
    reward_risk_score: float,
    iv_score: float,
    greek_safety_score: float,
) -> float:
    return (
        (0.25 * alpha_score)
        + (0.15 * trend_score)
        + (0.15 * liquidity_score)
        + (0.15 * probability_profit_score)
        + (0.10 * reward_risk_score)
        + (0.10 * iv_score)
        + (0.10 * greek_safety_score)
    )


def _calc_long_call(symbol: str, underlying: float, leg: OptionLeg, feature: dict[str, Any]) -> dict[str, Any]:
    debit = leg.ask
    max_loss = debit * 100.0
    breakeven = leg.strike + debit
    target_price = underlying + (2.0 * float(feature.get("atr_14", 3.0)))
    max_profit = max(0.0, (target_price - breakeven) * 100.0)
    reward_risk = max_profit / max_loss if max_loss > 0 else 0.0
    pop = probability_profit_long_call(leg.delta, debit, underlying, leg.strike)
    expected_value = (pop * max_profit) - ((1.0 - pop) * max_loss)
    return {
        "symbol": symbol,
        "strategy_type": "long_call",
        "direction": "bullish",
        "expiry": leg.expiry,
        "dte": leg.dte,
        "legs": [{"action": "BUY", "option_type": "call", "strike": leg.strike, "qty": 1}],
        "debit_or_credit": debit,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven": breakeven,
        "probability_profit": pop,
        "expected_value": expected_value,
        "spread_pct": leg.spread_pct,
        "open_interest": leg.open_interest,
        "option_volume": leg.volume,
        "gamma": leg.gamma,
        "reward_risk": reward_risk,
    }


def _calc_long_put(symbol: str, underlying: float, leg: OptionLeg, feature: dict[str, Any]) -> dict[str, Any]:
    debit = leg.ask
    max_loss = debit * 100.0
    breakeven = leg.strike - debit
    max_profit = max(0.0, (breakeven - max(0.0, underlying - (2.0 * float(feature.get("atr_14", 3.0))))) * 100.0)
    reward_risk = max_profit / max_loss if max_loss > 0 else 0.0
    pop = probability_profit_long_put(leg.delta, debit, underlying, leg.strike)
    expected_value = (pop * max_profit) - ((1.0 - pop) * max_loss)
    return {
        "symbol": symbol,
        "strategy_type": "long_put",
        "direction": "bearish",
        "expiry": leg.expiry,
        "dte": leg.dte,
        "legs": [{"action": "BUY", "option_type": "put", "strike": leg.strike, "qty": 1}],
        "debit_or_credit": debit,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven": breakeven,
        "probability_profit": pop,
        "expected_value": expected_value,
        "spread_pct": leg.spread_pct,
        "open_interest": leg.open_interest,
        "option_volume": leg.volume,
        "gamma": leg.gamma,
        "reward_risk": reward_risk,
    }


def _calc_bull_call_spread(
    symbol: str, underlying: float, buy_leg: OptionLeg, sell_leg: OptionLeg, feature: dict[str, Any]
) -> dict[str, Any]:
    debit = max(0.01, buy_leg.ask - sell_leg.bid)
    width = max(0.01, sell_leg.strike - buy_leg.strike)
    max_loss = debit * 100.0
    max_profit = max(0.0, (width - debit) * 100.0)
    breakeven = buy_leg.strike + debit
    reward_risk = max_profit / max_loss if max_loss > 0 else 0.0
    pop = probability_profit_bull_call_spread(buy_leg.delta, sell_leg.delta)
    expected_value = (pop * max_profit) - ((1.0 - pop) * max_loss)
    spread_pct = max(buy_leg.spread_pct, sell_leg.spread_pct)
    return {
        "symbol": symbol,
        "strategy_type": "bull_call_debit_spread",
        "direction": "bullish",
        "expiry": buy_leg.expiry,
        "dte": buy_leg.dte,
        "legs": [
            {"action": "BUY", "option_type": "call", "strike": buy_leg.strike, "qty": 1},
            {"action": "SELL", "option_type": "call", "strike": sell_leg.strike, "qty": 1},
        ],
        "debit_or_credit": debit,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven": breakeven,
        "probability_profit": pop,
        "expected_value": expected_value,
        "spread_pct": spread_pct,
        "open_interest": min(buy_leg.open_interest, sell_leg.open_interest),
        "option_volume": min(buy_leg.volume, sell_leg.volume),
        "gamma": max(abs(buy_leg.gamma), abs(sell_leg.gamma)),
        "reward_risk": reward_risk,
        "iv_percentile_hint": float(feature.get("iv_percentile", 50.0)),
    }


def _calc_bear_put_spread(
    symbol: str, underlying: float, buy_leg: OptionLeg, sell_leg: OptionLeg, feature: dict[str, Any]
) -> dict[str, Any]:
    debit = max(0.01, buy_leg.ask - sell_leg.bid)
    width = max(0.01, buy_leg.strike - sell_leg.strike)
    max_loss = debit * 100.0
    max_profit = max(0.0, (width - debit) * 100.0)
    breakeven = buy_leg.strike - debit
    reward_risk = max_profit / max_loss if max_loss > 0 else 0.0
    pop = probability_profit_bear_put_spread(buy_leg.delta, sell_leg.delta)
    expected_value = (pop * max_profit) - ((1.0 - pop) * max_loss)
    spread_pct = max(buy_leg.spread_pct, sell_leg.spread_pct)
    return {
        "symbol": symbol,
        "strategy_type": "bear_put_debit_spread",
        "direction": "bearish",
        "expiry": buy_leg.expiry,
        "dte": buy_leg.dte,
        "legs": [
            {"action": "BUY", "option_type": "put", "strike": buy_leg.strike, "qty": 1},
            {"action": "SELL", "option_type": "put", "strike": sell_leg.strike, "qty": 1},
        ],
        "debit_or_credit": debit,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven": breakeven,
        "probability_profit": pop,
        "expected_value": expected_value,
        "spread_pct": spread_pct,
        "open_interest": min(buy_leg.open_interest, sell_leg.open_interest),
        "option_volume": min(buy_leg.volume, sell_leg.volume),
        "gamma": max(abs(buy_leg.gamma), abs(sell_leg.gamma)),
        "reward_risk": reward_risk,
        "iv_percentile_hint": float(feature.get("iv_percentile", 50.0)),
    }


def _score_candidate(candidate: dict[str, Any], feature: dict[str, Any]) -> tuple[float, float, float, float]:
    direction = candidate["direction"]
    strategy_type = candidate["strategy_type"]
    iv_percentile = float(feature.get("iv_percentile", candidate.get("iv_percentile_hint", 50.0)))
    alpha = _alpha_score(feature, direction)  # type: ignore[arg-type]
    beta = _beta_score(feature)
    gamma_s = gamma_safety_score(float(candidate["gamma"]), int(candidate["dte"]))
    liq = _liquidity_score(float(candidate["spread_pct"]), int(candidate["open_interest"]), int(candidate["option_volume"]))
    score = _strategy_score(
        alpha_score=alpha,
        trend_score=_trend_score(feature),
        liquidity_score=liq,
        probability_profit_score=_pop_score(float(candidate["probability_profit"])),
        reward_risk_score=_rr_score(float(candidate["reward_risk"])),
        iv_score=_iv_score(iv_percentile, strategy_type),  # type: ignore[arg-type]
        greek_safety_score=gamma_s,
    )
    return score, alpha, beta, liq


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(candidates, key=lambda x: (float(x["strategy_score"]), float(x["expected_value"])), reverse=True)


def build_and_rank_candidates(
    *,
    symbol: str,
    direction: Direction,
    last_price: float,
    feature: dict[str, Any],
    option_chain: list[dict[str, Any]],
    reconciliation_mismatch_active: bool,
    thresholds: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    cfg = {
        "min_dte": 21.0,
        "max_spread_pct": 0.12,
        "min_open_interest": 500.0,
        "min_option_volume": 100.0,
        "max_loss_per_trade_usd": 500.0,
        "min_reward_risk": 0.60,
        "min_probability_profit": 0.40,
        "high_iv_percentile": 70.0,
    }
    if thresholds:
        cfg.update(thresholds)

    legs: list[OptionLeg] = []
    for row in option_chain:
        try:
            legs.append(
                OptionLeg(
                    expiry=str(row["expiry"]),
                    dte=int(row["dte"]),
                    option_type=str(row["option_type"]).lower(),  # type: ignore[arg-type]
                    strike=float(row["strike"]),
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                    volume=int(row.get("volume", 0)),
                    open_interest=int(row.get("open_interest", 0)),
                    delta=float(row.get("delta", 0.0)),
                    gamma=float(row.get("gamma", 0.0)),
                    theta=float(row.get("theta", 0.0)),
                    vega=float(row.get("vega", 0.0)),
                    iv=float(row.get("iv", 0.0)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    candidates: list[dict[str, Any]] = []
    now_iso = datetime.utcnow().isoformat()

    calls = [x for x in legs if x.option_type == "call"]
    puts = [x for x in legs if x.option_type == "put"]

    if direction == "bullish":
        for leg in calls[:40]:
            c = _calc_long_call(symbol, last_price, leg, feature)
            c["created_at"] = now_iso
            candidates.append(c)
        # Bull call spread pairs by same expiry, buy lower strike/sell higher strike.
        by_expiry: dict[str, list[OptionLeg]] = {}
        for leg in calls:
            by_expiry.setdefault(leg.expiry, []).append(leg)
        for same_expiry in by_expiry.values():
            same_expiry.sort(key=lambda x: x.strike)
            for i in range(min(10, len(same_expiry))):
                for j in range(i + 1, min(i + 6, len(same_expiry))):
                    buy_leg = same_expiry[i]
                    sell_leg = same_expiry[j]
                    candidates.append(_calc_bull_call_spread(symbol, last_price, buy_leg, sell_leg, feature))
    else:
        for leg in puts[:40]:
            c = _calc_long_put(symbol, last_price, leg, feature)
            c["created_at"] = now_iso
            candidates.append(c)
        by_expiry = {}
        for leg in puts:
            by_expiry.setdefault(leg.expiry, []).append(leg)
        for same_expiry in by_expiry.values():
            same_expiry.sort(key=lambda x: x.strike, reverse=True)
            for i in range(min(10, len(same_expiry))):
                for j in range(i + 1, min(i + 6, len(same_expiry))):
                    buy_leg = same_expiry[i]
                    sell_leg = same_expiry[j]
                    if buy_leg.strike <= sell_leg.strike:
                        continue
                    candidates.append(_calc_bear_put_spread(symbol, last_price, buy_leg, sell_leg, feature))

    scored: list[dict[str, Any]] = []
    for c in candidates:
        gamma_label = gamma_risk_label(float(c["gamma"]), int(c["dte"]))
        risk_status, reasons = apply_risk_rules(
            strategy_type=str(c["strategy_type"]),
            dte=int(c["dte"]),
            spread_pct=float(c["spread_pct"]),
            open_interest=int(c["open_interest"]),
            volume=int(c["option_volume"]),
            max_loss=float(c["max_loss"]),
            reward_risk=float(c["reward_risk"]),
            probability_profit=float(c["probability_profit"]),
            gamma_label=gamma_label,
            iv_percentile=float(feature.get("iv_percentile", 50.0)),
            reconciliation_mismatch_active=reconciliation_mismatch_active,
            thresholds=cfg,
        )
        score, alpha, beta, liq = _score_candidate(c, feature)
        c.update(
            {
                "alpha_score": round(alpha, 2),
                "beta_score": round(beta, 2),
                "gamma_score": round(gamma_safety_score(float(c["gamma"]), int(c["dte"])), 2),
                "liquidity_score": round(liq, 2),
                "strategy_score": round(score, 2),
                "risk_status": risk_status,
                "rule_reasons": reasons,
            }
        )
        scored.append(c)

    # Hard reject beats score in final list ordering.
    allowed = [x for x in scored if x["risk_status"] == "allow"]
    override_required = [x for x in scored if x["risk_status"] == "override_required"]
    rejected = [x for x in scored if x["risk_status"] == "reject"]
    return rank_candidates(allowed) + rank_candidates(override_required) + rank_candidates(rejected)

