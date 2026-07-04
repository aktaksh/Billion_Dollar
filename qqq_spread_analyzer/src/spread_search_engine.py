"""Spread Search Engine — builds and scores spreads across multiple ranked expiries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.config import Settings, get_settings
from src.expiry_search_engine import ExpiryScore, ExpirySearchResult
from src.options_chain import OptionQuote
from src.scoring import Action
from src.spread_builder import SpreadCandidate, _build_bull_spreads, _build_bear_spreads, _liquidity_score


@dataclass
class ScoredSpread:
    candidate: SpreadCandidate
    spread_score: float
    liquidity_component: float
    delta_fit_component: float
    risk_reward_component: float
    breakeven_component: float
    expiry_component: float
    event_risk_component: float
    rank: int = 0

    @property
    def expiry(self) -> str:
        return self.candidate.expiry

    @property
    def dte(self) -> int:
        return self.candidate.dte


@dataclass
class SpreadSearchResult:
    top_spreads: list[ScoredSpread]
    by_expiry: dict[str, list[ScoredSpread]]
    total_found: int
    total_rejected: int
    rejection_reasons: list[str]
    direction: str  # "bullish", "bearish", "neutral"


SPREAD_WEIGHTS = {
    "liquidity": 30,
    "delta_fit": 20,
    "risk_reward": 20,
    "breakeven": 10,
    "expiry": 10,
    "event_risk": 10,
}


def _delta_fit_score(candidate: SpreadCandidate, settings: Settings) -> float:
    if candidate.spread_type == "bull_call_spread":
        buy_mid = (settings.buy_call_delta_min + settings.buy_call_delta_max) / 2
        sell_mid = (settings.sell_call_delta_min + settings.sell_call_delta_max) / 2
        buy_dist = abs(candidate.buy_delta - buy_mid) / 0.05
        sell_dist = abs(candidate.sell_delta - sell_mid) / 0.05
    else:
        buy_mid = (settings.buy_put_delta_min + settings.buy_put_delta_max) / 2
        sell_mid = (settings.sell_put_delta_min + settings.sell_put_delta_max) / 2
        buy_dist = abs(candidate.buy_delta - buy_mid) / 0.05
        sell_dist = abs(candidate.sell_delta - sell_mid) / 0.05
    return max(0, 100 - (buy_dist + sell_dist) * 20)


def _risk_reward_score(candidate: SpreadCandidate) -> float:
    rr = candidate.reward_risk
    if rr >= 2.5:
        return 100
    if rr >= 2.0:
        return 90
    if rr >= 1.5:
        return 75
    if rr >= 1.0:
        return 60
    if rr >= 0.8:
        return 40
    return 20


def _breakeven_score(candidate: SpreadCandidate, spot: float) -> float:
    if spot <= 0:
        return 50
    dist_pct = abs(candidate.breakeven - spot) / spot * 100
    if candidate.spread_type == "bull_call_spread":
        if candidate.breakeven <= spot:
            return 95
        if dist_pct <= 1.0:
            return 80
        if dist_pct <= 2.0:
            return 65
        return max(20, 65 - (dist_pct - 2) * 10)
    else:
        if candidate.breakeven >= spot:
            return 95
        if dist_pct <= 1.0:
            return 80
        if dist_pct <= 2.0:
            return 65
        return max(20, 65 - (dist_pct - 2) * 10)


class SpreadSearchEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def search(
        self,
        quotes: list[OptionQuote],
        expiry_result: ExpirySearchResult,
        action: Action,
        spot: float,
        *,
        limit: int = 5,
    ) -> SpreadSearchResult:
        if action == "no_trade":
            return SpreadSearchResult(
                top_spreads=[],
                by_expiry={},
                total_found=0,
                total_rejected=0,
                rejection_reasons=["Direction is neutral — no spread search performed"],
                direction="neutral",
            )

        direction = "bullish" if action == "bull_call_spread" else "bearish"
        ranked_expiries = expiry_result.rankings
        expiry_scores: dict[str, float] = {e.expiry: e.score for e in ranked_expiries}

        quotes_by_expiry: dict[str, list[OptionQuote]] = {}
        for q in quotes:
            quotes_by_expiry.setdefault(q.expiry, []).append(q)

        all_scored: list[ScoredSpread] = []
        by_expiry: dict[str, list[ScoredSpread]] = {}
        rejection_reasons: list[str] = []
        total_rejected = 0

        eligible_expiries = [e.expiry for e in ranked_expiries]

        for expiry in eligible_expiries:
            expiry_quotes = quotes_by_expiry.get(expiry, [])
            if not expiry_quotes:
                rejection_reasons.append(f"{expiry}: no quotes available")
                continue

            if action == "bull_call_spread":
                raw = _build_bull_spreads(expiry_quotes, self._settings)
            else:
                raw = _build_bear_spreads(expiry_quotes, self._settings)

            if not raw:
                rejection_reasons.append(f"{expiry}: no spreads passed delta/width/debit filters")
                total_rejected += 1
                continue

            expiry_info = next((e for e in ranked_expiries if e.expiry == expiry), None)
            expiry_base_score = expiry_scores.get(expiry, 50)
            event_risk_val = (expiry_info.event_risk if expiry_info else 100)

            for candidate in raw:
                liq = candidate.liquidity_score
                delta_fit = _delta_fit_score(candidate, self._settings)
                rr = _risk_reward_score(candidate)
                be = _breakeven_score(candidate, spot)
                exp_sc = expiry_base_score
                ev_risk = event_risk_val

                total = (
                    liq * SPREAD_WEIGHTS["liquidity"]
                    + delta_fit * SPREAD_WEIGHTS["delta_fit"]
                    + rr * SPREAD_WEIGHTS["risk_reward"]
                    + be * SPREAD_WEIGHTS["breakeven"]
                    + exp_sc * SPREAD_WEIGHTS["expiry"]
                    + ev_risk * SPREAD_WEIGHTS["event_risk"]
                ) / 100

                scored = ScoredSpread(
                    candidate=candidate,
                    spread_score=round(total, 1),
                    liquidity_component=round(liq, 1),
                    delta_fit_component=round(delta_fit, 1),
                    risk_reward_component=round(rr, 1),
                    breakeven_component=round(be, 1),
                    expiry_component=round(exp_sc, 1),
                    event_risk_component=round(ev_risk, 1),
                )
                all_scored.append(scored)
                by_expiry.setdefault(expiry, []).append(scored)

        all_scored.sort(key=lambda s: s.spread_score, reverse=True)
        for i, s in enumerate(all_scored):
            s.rank = i + 1

        for expiry in by_expiry:
            by_expiry[expiry].sort(key=lambda s: s.spread_score, reverse=True)

        top = all_scored[:limit]

        return SpreadSearchResult(
            top_spreads=top,
            by_expiry=by_expiry,
            total_found=len(all_scored),
            total_rejected=total_rejected,
            rejection_reasons=rejection_reasons,
            direction=direction,
        )
