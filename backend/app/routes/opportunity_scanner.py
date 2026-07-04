"""Opportunity Scanner API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.services.opportunity_scanner.opportunity_scanner_service import OpportunityScannerService

router = APIRouter(prefix="/api/opportunity-scanner", tags=["opportunity-scanner"])

_service: OpportunityScannerService | None = None


def set_opportunity_scanner_service(service: OpportunityScannerService) -> None:
    global _service
    _service = service


def get_service() -> OpportunityScannerService:
    if _service is None:
        raise RuntimeError("OpportunityScannerService not initialized")
    return _service


class RefreshIn(BaseModel):
    refresh_news: bool = False


@router.get("/latest")
def get_latest(svc: OpportunityScannerService = Depends(get_service)) -> dict[str, Any]:
    return svc.get_latest()


@router.post("/refresh")
def post_refresh(
    body: RefreshIn | None = None,
    svc: OpportunityScannerService = Depends(get_service),
) -> dict[str, Any]:
    refresh_news = body.refresh_news if body else False
    return svc.scan(refresh_news=refresh_news)


@router.get("/export")
def export_scanner(svc: OpportunityScannerService = Depends(get_service)) -> PlainTextResponse:
    return PlainTextResponse(content=svc.export_json(), media_type="application/json")


@router.get("/symbol/{symbol}")
def get_symbol(symbol: str, svc: OpportunityScannerService = Depends(get_service)) -> dict[str, Any]:
    row = svc.get_symbol(symbol.strip().upper())
    if not row:
        raise HTTPException(status_code=404, detail=f"No scan result for {symbol}")
    return row
