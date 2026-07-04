from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.services.trade_decision.trade_decision_engine import TradeDecisionEngine

router = APIRouter(prefix="/api/trade-decision", tags=["trade-decision"])

_engine: TradeDecisionEngine | None = None


def set_trade_decision_engine(engine: TradeDecisionEngine) -> None:
    global _engine
    _engine = engine


def get_trade_decision_service() -> TradeDecisionEngine:
    if _engine is None:
        raise RuntimeError("TradeDecisionEngine not initialized")
    return _engine


class RecordDecisionIn(BaseModel):
    symbol: str = "QQQ"
    analysis_timestamp: str | None = None
    decision: str
    trade_score: float
    confidence: str
    market_regime: str | None = None
    strategy: str | None = None
    reason: str | None = None
    entry_price: float | None = None
    entry_trigger: str | None = None
    target: str | None = None
    stop: str | None = None
    risk_level: str = "Medium"
    probability: float | None = None
    summary: str | None = None
    summary_json: dict[str, Any] | None = None


@router.post("/record")
def record_decision(body: RecordDecisionIn, svc: TradeDecisionEngine = Depends(get_trade_decision_service)) -> dict[str, Any]:
    return svc.record(body.model_dump())


@router.get("/recent/{symbol}")
def recent_decisions(symbol: str, svc: TradeDecisionEngine = Depends(get_trade_decision_service)) -> list[dict[str, Any]]:
    return svc.list_recent(symbol)
