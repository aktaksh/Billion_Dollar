from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.engines.option_leg_filter import filter_usable_legs
from app.engines.strategy_builder_engine import build_and_rank_candidates

logger = logging.getLogger(__name__)


def run_strategy_runtime(
    *,
    ticker: str,
    direction: str,
    market_snapshot: dict[str, Any],
    feature_snapshot: dict[str, Any],
    option_chain_snapshot: list[dict[str, Any]],
    reconciliation_mismatch_active: bool,
    thresholds: dict[str, float] | None = None,
    underlying_price: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    last_price = float(
        underlying_price
        if underlying_price is not None and underlying_price > 0
        else feature_snapshot.get("last_price", market_snapshot.get("last", 100.0))
    )
    cfg = settings.options_chain
    max_spread_pct = float((thresholds or {}).get("max_spread_pct", cfg.max_spread_pct))
    filtered_chain, leg_diag = filter_usable_legs(
        option_chain_snapshot,
        underlying_price=last_price,
        max_spread_pct=max_spread_pct,
        strikes_below=cfg.strikes_below,
        strikes_above=cfg.strikes_above,
        strike_interval=cfg.strike_interval,
    )
    logger.info(
        "strategy_runtime leg_filter symbol=%s %s",
        ticker.upper(),
        leg_diag.as_dict(),
    )
    candidates = build_and_rank_candidates(
        symbol=ticker.upper(),
        direction=direction,  # type: ignore[arg-type]
        last_price=last_price,
        feature=feature_snapshot,
        option_chain=filtered_chain,
        reconciliation_mismatch_active=reconciliation_mismatch_active,
        thresholds=thresholds,
    )
    return candidates, leg_diag.as_dict()
