"""Expiry Spread Orchestrator — coordinates expiry search + spread search, enforces WAIT rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.config import Settings, get_settings
from src.expiry_search_engine import ExpirySearchEngine, ExpirySearchResult, ExpiryScore
from src.options_chain import OptionQuote
from src.scoring import Action
from src.spread_builder import SpreadCandidate
from src.spread_search_engine import SpreadSearchEngine, SpreadSearchResult, ScoredSpread


@dataclass
class ExpirySpreadResult:
    expiry_search: ExpirySearchResult
    spread_search: SpreadSearchResult
    final_candidates: list[SpreadCandidate]
    force_wait: bool
    wait_reason: str | None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def has_candidates(self) -> bool:
        return len(self.final_candidates) > 0


class ExpirySpreadOrchestrator:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._expiry_engine = ExpirySearchEngine(self._settings)
        self._spread_engine = SpreadSearchEngine(self._settings)

    def run(
        self,
        all_quotes: list[OptionQuote],
        liquid_quotes: list[OptionQuote],
        spot: float,
        action: Action,
        *,
        confidence: str = "Medium",
        volatility: str = "Medium",
        earnings_date: str | None = None,
    ) -> ExpirySpreadResult:
        expiry_result = self._expiry_engine.search(
            all_quotes,
            spot,
            confidence=confidence,
            volatility=volatility,
            earnings_date=earnings_date,
        )

        spread_result = self._spread_engine.search(
            liquid_quotes,
            expiry_result,
            action,
            spot,
            limit=5,
        )

        final_candidates: list[SpreadCandidate] = []
        force_wait = False
        wait_reason: str | None = None

        if action == "no_trade":
            force_wait = True
            wait_reason = "Direction is Neutral — no spread search performed."
        elif spread_result.total_found == 0:
            force_wait = True
            reasons = spread_result.rejection_reasons[:3]
            direction_label = "bullish" if action == "bull_call_spread" else "bearish"
            bucket_range = f"{self._settings.dte_buckets[0][0]}-{self._settings.dte_buckets[-1][1]}"
            wait_reason = (
                f"Directional setup is {direction_label}, but no valid spread passed "
                f"expiry/liquidity/risk filters across {bucket_range} DTE. "
                + "; ".join(reasons)
            )
        else:
            final_candidates = [s.candidate for s in spread_result.top_spreads]

        diagnostics = {
            "buckets_scanned": expiry_result.buckets_scanned,
            "expiries_scanned": expiry_result.expiries_scanned,
            "total_expiries_available": expiry_result.total_expiries_available,
            "best_expiry": expiry_result.best_expiry.expiry if expiry_result.best_expiry else None,
            "best_bucket": expiry_result.best_bucket,
            "valid_spreads_count": spread_result.total_found,
            "rejected_expiries_count": len(expiry_result.rejected),
            "spread_direction": spread_result.direction,
            "force_wait": force_wait,
            "no_candidate_reasons": spread_result.rejection_reasons if force_wait else [],
        }

        return ExpirySpreadResult(
            expiry_search=expiry_result,
            spread_search=spread_result,
            final_candidates=final_candidates,
            force_wait=force_wait,
            wait_reason=wait_reason,
            diagnostics=diagnostics,
        )

    def export_dict(self, result: ExpirySpreadResult) -> dict[str, Any]:
        """Serializable dict for JSON export."""
        expiry_rankings = []
        for e in result.expiry_search.rankings:
            expiry_rankings.append({
                "expiry": e.expiry,
                "dte": e.dte,
                "bucket": e.bucket,
                "score": e.score,
                "liquidity": e.liquidity,
                "valid_strikes": e.valid_strikes,
                "liquid_quotes": e.liquid_quotes,
                "event_risk": e.has_event_risk,
                "status": e.status,
                "reason": e.reason,
            })

        rejected_expiries = []
        for e in result.expiry_search.rejected:
            rejected_expiries.append({
                "expiry": e.expiry,
                "dte": e.dte,
                "bucket": e.bucket,
                "score": e.score,
                "status": e.status,
                "reason": e.reason,
            })

        top_spreads = []
        for s in result.spread_search.top_spreads:
            top_spreads.append({
                "rank": s.rank,
                "expiry": s.candidate.expiry,
                "dte": s.candidate.dte,
                "spread_type": s.candidate.spread_type,
                "buy_strike": s.candidate.buy_strike,
                "sell_strike": s.candidate.sell_strike,
                "net_debit": s.candidate.net_debit,
                "max_profit": s.candidate.max_profit,
                "max_loss": s.candidate.max_loss,
                "breakeven": s.candidate.breakeven,
                "reward_risk": s.candidate.reward_risk,
                "liquidity_score": s.candidate.liquidity_score,
                "spread_score": s.spread_score,
            })

        return {
            "buckets_scanned": result.expiry_search.buckets_scanned,
            "expiries_scanned": result.expiry_search.expiries_scanned,
            "best_expiry": result.expiry_search.best_expiry.expiry if result.expiry_search.best_expiry else None,
            "best_bucket": result.expiry_search.best_bucket,
            "expiry_rankings": expiry_rankings,
            "rejected_expiries": rejected_expiries,
            "valid_spreads_count": result.spread_search.total_found,
            "top_spreads": top_spreads,
            "force_wait": result.force_wait,
            "wait_reason": result.wait_reason,
            "no_candidate_reasons": result.spread_search.rejection_reasons,
        }
