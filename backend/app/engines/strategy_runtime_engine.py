from __future__ import annotations

from typing import Any

from app.engines.strategy_builder_engine import build_and_rank_candidates


def run_strategy_runtime(
    *,
    ticker: str,
    direction: str,
    market_snapshot: dict[str, Any],
    feature_snapshot: dict[str, Any],
    option_chain_snapshot: list[dict[str, Any]],
    reconciliation_mismatch_active: bool,
    thresholds: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    return build_and_rank_candidates(
        symbol=ticker.upper(),
        direction=direction,  # type: ignore[arg-type]
        last_price=float(feature_snapshot.get("last_price", market_snapshot.get("last", 100.0))),
        feature=feature_snapshot,
        option_chain=option_chain_snapshot,
        reconciliation_mismatch_active=reconciliation_mismatch_active,
        thresholds=thresholds,
    )
