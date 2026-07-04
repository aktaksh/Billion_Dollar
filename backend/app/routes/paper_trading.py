from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.services.ibkr.ibkr_sync_service import IBKRSyncService
from app.services.paper_trade_service import PaperTradeService

router = APIRouter(prefix="/api/paper-trading", tags=["paper-trading"])

_service: PaperTradeService | None = None
_ibkr_sync: IBKRSyncService | None = None


def set_paper_trade_service(service: PaperTradeService) -> None:
    global _service
    _service = service


def get_service() -> PaperTradeService:
    if _service is None:
        raise HTTPException(status_code=503, detail="Paper trading service not initialized")
    return _service


def set_ibkr_sync_service(service: IBKRSyncService) -> None:
    global _ibkr_sync
    _ibkr_sync = service


def get_ibkr_sync() -> IBKRSyncService:
    if _ibkr_sync is None:
        raise HTTPException(status_code=503, detail="IBKR sync service not initialized")
    return _ibkr_sync


class CreatePaperTradeIn(BaseModel):
    analysis: dict[str, Any]
    candidate: dict[str, Any]
    notes: str = ""
    quantity: int = Field(default=1, ge=1)


class BulkCreatePaperTradesIn(BaseModel):
    analysis: dict[str, Any]
    notes: str = ""


class UpdatePaperTradeIn(BaseModel):
    notes: str | None = None


class ClosePaperTradeIn(BaseModel):
    exit_reason: str = "Manual close"


class PaperTradeOut(BaseModel):
    id: str
    created_date: datetime
    symbol: str
    underlying_price_at_entry: float
    strategy_type: str
    expiry_date: str
    days_to_entry_dte: int
    long_strike: float
    short_strike: float
    long_option_type: str
    short_option_type: str
    entry_debit: float | None
    entry_credit: float | None
    quantity: int
    max_profit: float
    max_loss: float
    breakeven: float
    entry_delta_long: float | None = None
    entry_delta_short: float | None = None
    entry_iv: float | None = None
    entry_atr: float | None = None
    entry_rsi: float | None = None
    entry_macd: float | None = None
    market_bias: str | None = None
    confidence: str | None = None
    reason_for_trade: str | None = None
    notes: str | None = None
    status: Literal["OPEN", "CLOSED", "EXPIRED"]
    exit_date: datetime | None = None
    exit_reason: str | None = None
    current_underlying_price: float | None = None
    current_spread_value: float | None = None
    realized_pnl: float | None = None
    unrealized_pnl: float | None = None
    percent_return: float | None = None
    highest_profit_seen: float | None = None
    largest_drawdown: float | None = None
    last_marked_at: datetime | None = None
    execution_enabled: bool = False
    broker_order_id: str | None = None
    broker_status: str | None = None
    source: str | None = "manual"
    ibkr_sync_key: str | None = None
    long_con_id: int | None = None
    short_con_id: int | None = None
    average_cost: float | None = None
    market_value: float | None = None
    today_pnl: float | None = None
    long_bid: float | None = None
    long_ask: float | None = None
    long_mid: float | None = None
    short_bid: float | None = None
    short_ask: float | None = None
    short_mid: float | None = None
    max_profit_remaining: float | None = None
    progress_pct: float | None = None
    breakeven_distance: float | None = None
    distance_to_long_strike: float | None = None
    distance_to_short_strike: float | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class PaperTradeDetailOut(PaperTradeOut):
    snapshots: list[dict[str, Any]] = []
    review: dict[str, Any] | None = None
    entry_snapshot_json: dict[str, Any] | None = None


class BulkCreateOut(BaseModel):
    created: list[PaperTradeOut]
    count: int


class MarkToMarketOut(BaseModel):
    symbol: str
    updated: int


@router.post("/trades", response_model=PaperTradeOut)
def create_trade(body: CreatePaperTradeIn, svc: PaperTradeService = Depends(get_service)) -> dict[str, Any]:
    return svc.create_from_spread_candidate(
        body.analysis,
        body.candidate,
        notes=body.notes,
        quantity=body.quantity,
    )


@router.post("/trades/bulk", response_model=BulkCreateOut)
def bulk_create_trades(body: BulkCreatePaperTradesIn, svc: PaperTradeService = Depends(get_service)) -> dict[str, Any]:
    created = svc.bulk_create_from_analysis(body.analysis, notes=body.notes)
    return {"created": created, "count": len(created)}


@router.get("/trades", response_model=list[PaperTradeOut])
def list_trades(
    symbol: str | None = None,
    strategy_type: str | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    profit_only: bool | None = None,
    loss_only: bool | None = None,
    svc: PaperTradeService = Depends(get_service),
) -> list[dict[str, Any]]:
    return svc.list_trades(
        symbol=symbol,
        strategy_type=strategy_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        profit_only=profit_only,
        loss_only=loss_only,
    )


@router.get("/trades/{trade_id}", response_model=PaperTradeDetailOut)
def get_trade(trade_id: str, svc: PaperTradeService = Depends(get_service)) -> dict[str, Any]:
    trade = svc.get_trade(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


@router.patch("/trades/{trade_id}", response_model=PaperTradeDetailOut)
def update_trade(
    trade_id: str,
    body: UpdatePaperTradeIn,
    svc: PaperTradeService = Depends(get_service),
) -> dict[str, Any]:
    trade = svc.update_trade(trade_id, notes=body.notes)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


@router.post("/trades/{trade_id}/close", response_model=PaperTradeDetailOut)
def close_trade(
    trade_id: str,
    body: ClosePaperTradeIn,
    svc: PaperTradeService = Depends(get_service),
) -> dict[str, Any]:
    trade = svc.close_trade(trade_id, body.exit_reason)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


@router.get("/summary")
def get_summary(svc: PaperTradeService = Depends(get_service)) -> dict[str, Any]:
    return svc.get_summary()


@router.get("/analytics")
def get_analytics(svc: PaperTradeService = Depends(get_service)) -> dict[str, Any]:
    return svc.get_analytics()


@router.get("/export")
def export_trades(
    format: Literal["csv", "json"] = Query("json", alias="format"),
    symbol: str | None = None,
    status: str | None = None,
    svc: PaperTradeService = Depends(get_service),
) -> Response:
    media, filename, content = svc.export_trades(format, symbol=symbol, status=status)
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class AutoSyncIn(BaseModel):
    interval_seconds: int = Field(ge=0, description="0=manual only, 60/300/900 for auto sync")


@router.post("/ibkr/fetch-positions")
def ibkr_fetch_positions(sync: IBKRSyncService = Depends(get_ibkr_sync)) -> dict[str, Any]:
    return sync.fetch_open_positions()


@router.post("/ibkr/refresh-prices")
def ibkr_refresh_prices(sync: IBKRSyncService = Depends(get_ibkr_sync)) -> dict[str, Any]:
    return sync.refresh_market_prices()


@router.post("/ibkr/recalculate")
def ibkr_recalculate(sync: IBKRSyncService = Depends(get_ibkr_sync)) -> dict[str, Any]:
    return sync.recalculate_all()


@router.post("/ibkr/sync")
def ibkr_sync(sync: IBKRSyncService = Depends(get_ibkr_sync)) -> dict[str, Any]:
    return sync.sync_from_ibkr()


@router.get("/ibkr/status")
def ibkr_status(sync: IBKRSyncService = Depends(get_ibkr_sync)) -> dict[str, Any]:
    return sync.get_sync_status()


@router.post("/ibkr/auto-sync")
def ibkr_auto_sync(body: AutoSyncIn) -> dict[str, Any]:
    from app.main import get_position_sync_job

    job = get_position_sync_job()
    if job is None:
        raise HTTPException(status_code=503, detail="Position sync job not initialized")
    job.set_interval(body.interval_seconds)
    return {"interval_seconds": job.interval_seconds, "running": job.interval_seconds > 0}


@router.post("/mark/{symbol}", response_model=MarkToMarketOut)
def mark_symbol(symbol: str, svc: PaperTradeService = Depends(get_service)) -> dict[str, Any]:
    sym = symbol.strip().upper()
    updated = svc.mark_to_market_for_symbol(sym)
    return {"symbol": sym, "updated": updated}
