from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.services.market_regime.market_regime_service import MarketRegimeService

router = APIRouter(prefix="/api/market-regime", tags=["market-regime"])

_service: MarketRegimeService | None = None


def set_market_regime_service(service: MarketRegimeService) -> None:
    global _service
    _service = service


def get_service() -> MarketRegimeService:
    if _service is None:
        raise RuntimeError("MarketRegimeService not initialized")
    return _service


@router.get("/latest")
def get_latest(service: MarketRegimeService = Depends(get_service)) -> dict[str, Any]:
    return service.get_cached_or_build()


@router.post("/refresh")
def refresh_regime(service: MarketRegimeService = Depends(get_service)) -> dict[str, Any]:
    return service.build_dashboard()


@router.post("/refresh-all")
def refresh_all_market_data(service: MarketRegimeService = Depends(get_service)) -> dict[str, Any]:
    return service.build_dashboard(refresh_all=True)


@router.post("/save-snapshot")
def save_snapshot(service: MarketRegimeService = Depends(get_service)) -> dict[str, Any]:
    dashboard = service.build_dashboard(refresh_all=True)
    return service.save_snapshot(dashboard)


@router.get("/history")
def get_history(
    days: int = Query(30, ge=1, le=365),
    service: MarketRegimeService = Depends(get_service),
) -> list[dict[str, Any]]:
    return service.history(days=days)


@router.get("/export")
def export_regime(service: MarketRegimeService = Depends(get_service)) -> PlainTextResponse:
    body = service.export_json()
    return PlainTextResponse(content=body, media_type="application/json")
