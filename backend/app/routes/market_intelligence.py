from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.services.market_intelligence.market_intelligence_service import MarketIntelligenceService

router = APIRouter(prefix="/api/market-intelligence", tags=["market-intelligence"])

_service: MarketIntelligenceService | None = None


def set_market_intelligence_service(service: MarketIntelligenceService) -> None:
    global _service
    _service = service


def get_service() -> MarketIntelligenceService:
    if _service is None:
        raise RuntimeError("MarketIntelligenceService not initialized")
    return _service


class RefreshIn(BaseModel):
    mode: str = Field(default="standard", pattern="^(quick|standard|deep)$")


class WatchlistPatchIn(BaseModel):
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=99)


@router.get("/dashboard")
def get_dashboard(svc: MarketIntelligenceService = Depends(get_service)) -> dict[str, Any]:
    return svc.build_dashboard()


@router.post("/refresh")
def post_refresh(body: RefreshIn, svc: MarketIntelligenceService = Depends(get_service)) -> dict[str, Any]:
    return svc.refresh(body.mode)


@router.get("/export")
def export_dashboard(svc: MarketIntelligenceService = Depends(get_service)) -> PlainTextResponse:
    return PlainTextResponse(content=svc.export_json(), media_type="application/json")


@router.get("/watchlist")
def get_watchlist(svc: MarketIntelligenceService = Depends(get_service)) -> list[dict[str, Any]]:
    return svc._watchlist().list_with_signals()


@router.patch("/watchlist/{symbol}")
def patch_watchlist(
    symbol: str,
    body: WatchlistPatchIn,
    svc: MarketIntelligenceService = Depends(get_service),
) -> dict[str, Any]:
    row = svc._watchlist().update(symbol, enabled=body.enabled, priority=body.priority)
    if not row:
        return {"error": f"Symbol {symbol} not found"}
    return row


@router.post("/watchlist/reset")
def reset_watchlist(svc: MarketIntelligenceService = Depends(get_service)) -> dict[str, Any]:
    count = svc._watchlist().reset()
    return {"reset": True, "count": count}


@router.get("/signal/{symbol}")
def get_signal(symbol: str, svc: MarketIntelligenceService = Depends(get_service)) -> dict[str, Any]:
    return svc.get_latest_signal(symbol.strip().upper())
