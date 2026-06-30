from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.config import settings
from app.engines.greek_risk_engine import gamma_risk_label, gamma_safety_score
from app.engines.setup_confirmation import (
    apply_breakeven_gate,
    apply_regime_gate,
    apply_setup_conflict_gate,
    breakeven_distance_score,
    evaluate_setup_status,
    setup_confirmation_score,
)
from app.engines.probability_engine import (
    probability_profit_debit_spread_breakeven,
    probability_profit_long_call,
    probability_profit_long_put,
)

Direction = Literal["bullish", "bearish"]
StrategyType = Literal["long_call", "long_put", "bull_call_debit_spread", "bear_put_debit_spread"]

ALLOWED_SPREAD_WIDTHS = {5.0, 10.0, 15.0, 20.0, 25.0, 30.0}
WIDTH_TOLERANCE = 0.01


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
    directional_bias = 5.0 if direction == "bullish" else 3.0
    raw = (0.5 * trend) + (0.2 * sector) + (news * 10.0) + directional_bias - overextended_penalty
    return max(0.0, min(100.0, raw))


def _beta_score(feature: dict[str, Any]) -> float:
    beta_spy = abs(float(feature.get("beta_to_spy", 1.0)))
    beta_qqq = abs(float(feature.get("beta_to_qqq", 1.0)))
    penalty = max(0.0, (beta_spy - 1.4) * 18.0) + max(0.0, (beta_qqq - 1.6) * 15.0)
    return max(0.0, min(100.0, 82.0 - penalty))


def _liquidity_score(spread_pct: float, oi: int, volume: int) -> float:
    spread_score = max(0.0, min(100.0, 100.0 - (spread_pct * 1000.0)))
    oi_score = max(0.0, min(100.0, (oi / 2000.0) * 100.0))
    vol_score = max(0.0, min(100.0, (volume / 500.0) * 100.0))
    return (0.45 * spread_score) + (0.30 * oi_score) + (0.25 * vol_score)


def _trend_score(feature: dict[str, Any]) -> float:
    return max(0.0, min(100.0, float(feature.get("trend_score", 50.0))))


def _iv_score(iv_percentile: float) -> float:
    return max(0.0, min(100.0, 100.0 - abs(iv_percentile - 55.0) * 1.0))


def _swing_strategy_score(
    *,
    setup_score: float,
    breakeven_score: float,
    liquidity_score: float,
    reward_risk_score: float,
    probability_profit_score: float,
    iv_score: float,
) -> float:
    return (
        (0.30 * setup_score)
        + (0.20 * breakeven_score)
        + (0.15 * liquidity_score)
        + (0.15 * reward_risk_score)
        + (0.10 * probability_profit_score)
        + (0.10 * iv_score)
    )


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


def _width_allowed(width: float) -> bool:
    return any(abs(width - allowed) <= WIDTH_TOLERANCE for allowed in ALLOWED_SPREAD_WIDTHS)


def _spread_iv(buy_leg: OptionLeg, sell_leg: OptionLeg) -> float:
    values = [v for v in (buy_leg.iv, sell_leg.iv) if v > 0]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _valid_spread_payoff(*, debit: float, width: float, max_loss: float, max_profit: float) -> bool:
    if debit <= 0 or width <= 0 or max_profit <= 0 or max_loss <= 0:
        return False
    return True


def _calc_long_call(symbol: str, underlying: float, leg: OptionLeg, feature: dict[str, Any]) -> dict[str, Any] | None:
    debit = leg.ask
    if debit <= 0:
        return None
    max_loss = debit * 100.0
    breakeven = leg.strike + debit
    target_price = underlying + (2.0 * float(feature.get("atr_14", 3.0)))
    max_profit = (target_price - breakeven) * 100.0
    if max_profit <= 0:
        return None
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
        "spread_width": 0.0,
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


def _calc_long_put(symbol: str, underlying: float, leg: OptionLeg, feature: dict[str, Any]) -> dict[str, Any] | None:
    debit = leg.ask
    if debit <= 0:
        return None
    max_loss = debit * 100.0
    breakeven = leg.strike - debit
    max_profit = (breakeven - max(0.0, underlying - (2.0 * float(feature.get("atr_14", 3.0))))) * 100.0
    if max_profit <= 0:
        return None
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
        "spread_width": 0.0,
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
    symbol: str,
    underlying: float,
    buy_leg: OptionLeg,
    sell_leg: OptionLeg,
    feature: dict[str, Any],
    max_loss_budget: float,
) -> dict[str, Any] | None:
    debit = buy_leg.ask - sell_leg.bid
    width = sell_leg.strike - buy_leg.strike
    max_loss = debit * 100.0
    max_profit = (width - debit) * 100.0
    if not _valid_spread_payoff(
        debit=debit,
        width=width,
        max_loss=max_loss,
        max_profit=max_profit,
    ):
        return None
    breakeven = buy_leg.strike + debit
    reward_risk = max_profit / max_loss if max_loss > 0 else 0.0
    iv = _spread_iv(buy_leg, sell_leg)
    pop = probability_profit_debit_spread_breakeven(
        underlying=underlying,
        breakeven=breakeven,
        dte=buy_leg.dte,
        iv=iv,
        direction="bullish",
        buy_delta=buy_leg.delta,
        sell_delta=sell_leg.delta,
    )
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
        "spread_width": width,
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
    symbol: str,
    underlying: float,
    buy_leg: OptionLeg,
    sell_leg: OptionLeg,
    feature: dict[str, Any],
    max_loss_budget: float,
) -> dict[str, Any] | None:
    debit = buy_leg.ask - sell_leg.bid
    width = buy_leg.strike - sell_leg.strike
    max_loss = debit * 100.0
    max_profit = (width - debit) * 100.0
    if not _valid_spread_payoff(
        debit=debit,
        width=width,
        max_loss=max_loss,
        max_profit=max_profit,
    ):
        return None
    breakeven = buy_leg.strike - debit
    reward_risk = max_profit / max_loss if max_loss > 0 else 0.0
    iv = _spread_iv(buy_leg, sell_leg)
    pop = probability_profit_debit_spread_breakeven(
        underlying=underlying,
        breakeven=breakeven,
        dte=buy_leg.dte,
        iv=iv,
        direction="bearish",
        buy_delta=buy_leg.delta,
        sell_delta=sell_leg.delta,
    )
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
        "spread_width": width,
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


def candidate_unique_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    legs = candidate.get("legs", [])
    buy = next((leg for leg in legs if leg.get("action") == "BUY"), None)
    sell = next((leg for leg in legs if leg.get("action") == "SELL"), None)
    return (
        candidate.get("symbol"),
        candidate.get("direction"),
        candidate.get("strategy_type"),
        candidate.get("expiry"),
        buy.get("strike") if buy else 0.0,
        sell.get("strike") if sell else 0.0,
        buy.get("option_type") if buy else "",
        sell.get("option_type") if sell else "",
    )


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[dict[str, Any]] = []
    for candidate in candidates:
        key = candidate_unique_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _generate_bull_call_debit_spreads(
    symbol: str,
    underlying: float,
    calls: list[OptionLeg],
    feature: dict[str, Any],
    max_loss_budget: float,
) -> list[dict[str, Any]]:
    spreads: list[dict[str, Any]] = []
    buy_low = underlying * 0.97
    buy_high = underlying * 1.05
    sell_max = underlying * 1.10
    by_expiry: dict[str, list[OptionLeg]] = {}
    for leg in calls:
        by_expiry.setdefault(leg.expiry, []).append(leg)
    for same_expiry in by_expiry.values():
        same_expiry.sort(key=lambda x: x.strike)
        for buy_leg in same_expiry:
            if buy_leg.strike < buy_low or buy_leg.strike > buy_high:
                continue
            for sell_leg in same_expiry:
                if sell_leg.strike <= buy_leg.strike or sell_leg.strike > sell_max:
                    continue
                width = sell_leg.strike - buy_leg.strike
                if not _width_allowed(width):
                    continue
                spread = _calc_bull_call_spread(symbol, underlying, buy_leg, sell_leg, feature, max_loss_budget)
                if spread is not None:
                    spreads.append(spread)
    return spreads


def _generate_bear_put_debit_spreads(
    symbol: str,
    underlying: float,
    puts: list[OptionLeg],
    feature: dict[str, Any],
    max_loss_budget: float,
) -> list[dict[str, Any]]:
    spreads: list[dict[str, Any]] = []
    buy_low = underlying * 0.95
    buy_high = underlying * 1.03
    sell_min = underlying * 0.90
    by_expiry: dict[str, list[OptionLeg]] = {}
    for leg in puts:
        by_expiry.setdefault(leg.expiry, []).append(leg)
    for same_expiry in by_expiry.values():
        same_expiry.sort(key=lambda x: x.strike, reverse=True)
        for buy_leg in same_expiry:
            if buy_leg.strike < buy_low or buy_leg.strike > buy_high:
                continue
            for sell_leg in same_expiry:
                if sell_leg.strike >= buy_leg.strike or sell_leg.strike < sell_min:
                    continue
                width = buy_leg.strike - sell_leg.strike
                if not _width_allowed(width):
                    continue
                spread = _calc_bear_put_spread(symbol, underlying, buy_leg, sell_leg, feature, max_loss_budget)
                if spread is not None:
                    spreads.append(spread)
    return spreads


def _generate_long_calls(
    symbol: str,
    underlying: float,
    calls: list[OptionLeg],
    feature: dict[str, Any],
    max_loss_budget: float,
) -> list[dict[str, Any]]:
    longs: list[dict[str, Any]] = []
    strike_low = underlying * 0.97
    strike_high = underlying * 1.05
    for leg in calls:
        if leg.strike < strike_low or leg.strike > strike_high:
            continue
        candidate = _calc_long_call(symbol, underlying, leg, feature)
        if candidate is None:
            continue
        if candidate["max_loss"] > max_loss_budget:
            continue
        longs.append(candidate)
    return longs


def _generate_long_puts(
    symbol: str,
    underlying: float,
    puts: list[OptionLeg],
    feature: dict[str, Any],
    max_loss_budget: float,
) -> list[dict[str, Any]]:
    longs: list[dict[str, Any]] = []
    strike_low = underlying * 0.95
    strike_high = underlying * 1.03
    for leg in puts:
        if leg.strike < strike_low or leg.strike > strike_high:
            continue
        candidate = _calc_long_put(symbol, underlying, leg, feature)
        if candidate is None:
            continue
        if candidate["max_loss"] > max_loss_budget:
            continue
        longs.append(candidate)
    return longs


def _swing_score_candidate(
    candidate: dict[str, Any],
    feature: dict[str, Any],
    *,
    setup_status: str,
    breakeven_distance_pct: float,
) -> tuple[float, float, float, float]:
    direction = candidate["direction"]
    iv_percentile = float(feature.get("iv_percentile", candidate.get("iv_percentile_hint", 50.0)))
    alpha = _alpha_score(feature, direction)  # type: ignore[arg-type]
    beta = _beta_score(feature)
    liq = _liquidity_score(float(candidate["spread_pct"]), int(candidate["open_interest"]), int(candidate["option_volume"]))
    score = _swing_strategy_score(
        setup_score=setup_confirmation_score(setup_status),  # type: ignore[arg-type]
        breakeven_score=breakeven_distance_score(breakeven_distance_pct),
        liquidity_score=liq,
        reward_risk_score=_rr_score(float(candidate["reward_risk"])),
        probability_profit_score=_pop_score(float(candidate["probability_profit"])),
        iv_score=_iv_score(iv_percentile),
    )
    return score, alpha, beta, liq


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
        iv_score=_iv_score(iv_percentile),
        greek_safety_score=gamma_s,
    )
    return score, alpha, beta, liq


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda x: (float(x["strategy_score"]), float(x["reward_risk"]), float(x["expected_value"])),
        reverse=True,
    )


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
        "min_dte": float(settings.options_chain.min_dte),
        "max_spread_pct": settings.options_chain.max_spread_pct,
        "min_open_interest": float(settings.options_chain.min_open_interest),
        "min_option_volume": float(settings.options_chain.min_volume),
        "max_loss_per_trade_usd": 500.0,
        "min_reward_risk": 0.60,
        "min_probability_profit": 0.40,
        "high_iv_percentile": 70.0,
        "max_breakeven_distance_pct": 0.06,
    }
    if thresholds:
        cfg.update(thresholds)

    regime = str(feature.get("regime") or "neutral").strip().lower()
    setup_eval = evaluate_setup_status(
        direction=direction,
        price=last_price,
        vwap=float(feature.get("vwap", last_price)),
        ema_20=float(feature.get("ema_20", last_price)),
        ema_20_slope=float(feature.get("ema_20_slope", 0.0)),
        rsi_14=float(feature.get("rsi_14", 50.0)),
    )
    setup_status = setup_eval.setup_status

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

    max_loss_budget = float(cfg["max_loss_per_trade_usd"])
    now_iso = datetime.now(UTC).isoformat()
    calls = [x for x in legs if x.option_type == "call"]
    puts = [x for x in legs if x.option_type == "put"]

    raw_candidates: list[dict[str, Any]] = []
    if direction == "bullish":
        raw_candidates.extend(_generate_bull_call_debit_spreads(symbol, last_price, calls, feature, max_loss_budget))
    else:
        raw_candidates.extend(_generate_bear_put_debit_spreads(symbol, last_price, puts, feature, max_loss_budget))

    candidates = dedupe_candidates(raw_candidates)
    for candidate in candidates:
        candidate["created_at"] = now_iso

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
        breakeven_distance_pct = abs(float(c["breakeven"]) - last_price) / last_price if last_price > 0 else 1.0
        risk_status, reasons = apply_setup_conflict_gate(
            risk_status=risk_status,
            setup_status=setup_status,
            reasons=reasons,
        )
        risk_status, reasons = apply_regime_gate(
            risk_status=risk_status,
            direction=direction,
            regime=regime,
            setup_status=setup_status,
            reasons=reasons,
        )
        risk_status, reasons = apply_breakeven_gate(
            risk_status=risk_status,
            breakeven_distance_pct=breakeven_distance_pct,
            max_breakeven_distance_pct=float(cfg["max_breakeven_distance_pct"]),
            reasons=reasons,
        )
        score, alpha, beta, liq = _swing_score_candidate(
            c,
            feature,
            setup_status=setup_status,
            breakeven_distance_pct=breakeven_distance_pct,
        )
        c.update(
            {
                "alpha_score": round(alpha, 2),
                "beta_score": round(beta, 2),
                "gamma_score": round(gamma_safety_score(float(c["gamma"]), int(c["dte"])), 2),
                "liquidity_score": round(liq, 2),
                "strategy_score": round(score, 2),
                "risk_status": risk_status,
                "rule_reasons": reasons,
                "setup_status": setup_status,
                "breakeven_distance_pct": round(breakeven_distance_pct, 4),
            }
        )
        scored.append(c)

    allowed = [x for x in scored if x["risk_status"] == "allow"]
    override_required = [x for x in scored if x["risk_status"] == "override_required"]
    watch_only = [x for x in scored if x["risk_status"] == "watch_only"]
    rejected = [x for x in scored if x["risk_status"] == "reject"]
    return (
        rank_candidates(allowed)
        + rank_candidates(override_required)
        + rank_candidates(watch_only)
        + rank_candidates(rejected)
    )
