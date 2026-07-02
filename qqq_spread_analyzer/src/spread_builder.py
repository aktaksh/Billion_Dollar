from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.config import Settings, get_settings
from src.options_chain import OptionQuote
from src.scoring import Action

SpreadType = Literal["bull_call_spread", "bear_put_spread"]


@dataclass
class SpreadCandidate:
    spread_type: SpreadType
    expiry: str
    dte: int
    buy_strike: float
    sell_strike: float
    buy_delta: float
    sell_delta: float
    net_debit: float
    max_loss: float
    max_profit: float
    breakeven: float
    reward_risk: float
    combined_delta: float
    combined_gamma: float
    combined_theta: float
    combined_vega: float
    bid_ask_quality: float
    liquidity_score: float


def _liquidity_score(buy: OptionQuote, sell: OptionQuote) -> float:
    spread_penalty = 1.0 - min(1.0, (buy.spread_pct + sell.spread_pct) / 2)
    oi_bonus = min(1.0, (buy.open_interest + sell.open_interest) / 2000) if buy.open_interest or sell.open_interest else 0.5
    vol_bonus = min(1.0, (buy.volume + sell.volume) / 400) if buy.volume or sell.volume else 0.5
    return round((spread_penalty * 0.5 + oi_bonus * 0.25 + vol_bonus * 0.25) * 100, 1)


def _build_bull_spreads(quotes: list[OptionQuote], settings: Settings) -> list[SpreadCandidate]:
    calls = [q for q in quotes if q.option_type == "call" and q.delta > 0]
    out: list[SpreadCandidate] = []
    by_expiry: dict[str, list[OptionQuote]] = {}
    for c in calls:
        by_expiry.setdefault(c.expiry, []).append(c)

    for expiry, legs in by_expiry.items():
        legs.sort(key=lambda x: x.strike)
        for buy in legs:
            if not (settings.buy_call_delta_min <= buy.delta <= settings.buy_call_delta_max):
                continue
            for sell in legs:
                if sell.strike <= buy.strike:
                    continue
                if not (settings.sell_call_delta_min <= sell.delta <= settings.sell_call_delta_max):
                    continue
                width = sell.strike - buy.strike
                if width < 1 or width > 30:
                    continue
                debit = buy.ask - sell.bid
                if debit <= 0:
                    continue
                max_loss = debit * 100
                max_profit = (width - debit) * 100
                if max_profit <= 0:
                    continue
                rr = max_profit / max_loss if max_loss > 0 else 0
                out.append(
                    SpreadCandidate(
                        spread_type="bull_call_spread",
                        expiry=expiry,
                        dte=buy.dte,
                        buy_strike=buy.strike,
                        sell_strike=sell.strike,
                        buy_delta=buy.delta,
                        sell_delta=sell.delta,
                        net_debit=round(debit, 2),
                        max_loss=round(max_loss, 2),
                        max_profit=round(max_profit, 2),
                        breakeven=round(buy.strike + debit, 2),
                        reward_risk=round(rr, 2),
                        combined_delta=round(buy.delta - sell.delta, 3),
                        combined_gamma=round(buy.gamma - sell.gamma, 4),
                        combined_theta=round(buy.theta - sell.theta, 4),
                        combined_vega=round(buy.vega - sell.vega, 4),
                        bid_ask_quality=round((1 - (buy.spread_pct + sell.spread_pct) / 2) * 100, 1),
                        liquidity_score=_liquidity_score(buy, sell),
                    )
                )
    return out


def _build_bear_spreads(quotes: list[OptionQuote], settings: Settings) -> list[SpreadCandidate]:
    puts = [q for q in quotes if q.option_type == "put" and q.delta < 0]
    out: list[SpreadCandidate] = []
    by_expiry: dict[str, list[OptionQuote]] = {}
    for p in puts:
        by_expiry.setdefault(p.expiry, []).append(p)

    for expiry, legs in by_expiry.items():
        legs.sort(key=lambda x: x.strike, reverse=True)
        for buy in legs:
            if not (settings.buy_put_delta_min <= buy.delta <= settings.buy_put_delta_max):
                continue
            for sell in legs:
                if sell.strike >= buy.strike:
                    continue
                if not (settings.sell_put_delta_min <= sell.delta <= settings.sell_put_delta_max):
                    continue
                width = buy.strike - sell.strike
                if width < 1 or width > 30:
                    continue
                debit = buy.ask - sell.bid
                if debit <= 0:
                    continue
                max_loss = debit * 100
                max_profit = (width - debit) * 100
                if max_profit <= 0:
                    continue
                rr = max_profit / max_loss if max_loss > 0 else 0
                out.append(
                    SpreadCandidate(
                        spread_type="bear_put_spread",
                        expiry=expiry,
                        dte=buy.dte,
                        buy_strike=buy.strike,
                        sell_strike=sell.strike,
                        buy_delta=buy.delta,
                        sell_delta=sell.delta,
                        net_debit=round(debit, 2),
                        max_loss=round(max_loss, 2),
                        max_profit=round(max_profit, 2),
                        breakeven=round(buy.strike - debit, 2),
                        reward_risk=round(rr, 2),
                        combined_delta=round(buy.delta - sell.delta, 3),
                        combined_gamma=round(buy.gamma - sell.gamma, 4),
                        combined_theta=round(buy.theta - sell.theta, 4),
                        combined_vega=round(buy.vega - sell.vega, 4),
                        bid_ask_quality=round((1 - (buy.spread_pct + sell.spread_pct) / 2) * 100, 1),
                        liquidity_score=_liquidity_score(buy, sell),
                    )
                )
    return out


def build_spread_candidates(
    quotes: list[OptionQuote],
    action: Action,
    *,
    settings: Settings | None = None,
    limit: int = 10,
) -> list[SpreadCandidate]:
    settings = settings or get_settings()
    if action == "no_trade":
        return []
    candidates = (
        _build_bull_spreads(quotes, settings)
        if action == "bull_call_spread"
        else _build_bear_spreads(quotes, settings)
    )
    candidates.sort(key=lambda c: (c.liquidity_score, c.reward_risk), reverse=True)
    return candidates[:limit]
