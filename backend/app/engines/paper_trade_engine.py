from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class PaperTradeResult:
    order_intent_id: str
    position_event_id: str
    close_event_id: str
    entry_price: float
    exit_price: float
    realized_pnl_after_costs_usd: float
    fees_usd: float
    slippage_usd: float
    opened_at: datetime
    closed_at: datetime


def simulate_paper_trade(
    *,
    signal_id: str,
    ticker: str,
    candidate: dict[str, Any],
    scenario_return: float,
) -> PaperTradeResult:
    now = datetime.now(timezone.utc)
    opened_at = now
    closed_at = now + timedelta(days=7)
    entry_debit = float(candidate.get("debit_or_credit", 1.0))
    max_profit = float(candidate.get("max_profit", 0.0))
    max_loss = float(candidate.get("max_loss", 0.0))
    directional = 1.0 if str(candidate.get("direction")) == "bullish" else -1.0
    alignment = max(0.0, min(1.0, 0.5 + (directional * scenario_return * 9.0)))
    gross_pnl = (alignment * max_profit) - ((1.0 - alignment) * max_loss)
    fees = max(1.0, abs(entry_debit) * 0.8)
    slippage = max(0.5, abs(entry_debit) * 0.4)
    realized = round(gross_pnl - fees - slippage, 2)
    exit_price = round(max(0.05, entry_debit + (realized / 100.0)), 4)
    stamp = now.strftime("%Y%m%d%H%M%S")
    return PaperTradeResult(
        order_intent_id=f"paper_intent_{stamp}_{ticker}",
        position_event_id=f"paper_pos_open_{stamp}_{ticker}",
        close_event_id=f"paper_pos_close_{stamp}_{ticker}",
        entry_price=round(entry_debit, 4),
        exit_price=exit_price,
        realized_pnl_after_costs_usd=realized,
        fees_usd=round(fees, 2),
        slippage_usd=round(slippage, 2),
        opened_at=opened_at,
        closed_at=closed_at,
    )
