from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.routes.market_intelligence import get_service

router = APIRouter(prefix="/api/news-intelligence", tags=["news-intelligence"])


class QuickRefreshIn(BaseModel):
    symbol: str = Field(default="QQQ", max_length=16)


@router.post("/quick-refresh")
def post_quick_refresh(body: QuickRefreshIn | None = None) -> dict:
    symbol = (body.symbol if body else "QQQ").strip().upper()
    return get_service().quick_refresh_for_symbol(symbol)


@router.get("/signal/{symbol}")
def get_signal(symbol: str) -> dict:
    return get_service().get_latest_signal(symbol.strip().upper())
