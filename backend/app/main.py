from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import get_engine, init_db
from app.models import HealthResponse
from app.routes.market_intelligence import router as market_intelligence_router, set_market_intelligence_service
from app.routes.news_intelligence import router as news_intelligence_router
from app.routes.market_regime import router as market_regime_router, set_market_regime_service
from app.routes.paper_trading import (
    router as paper_trading_router,
    set_ibkr_sync_service,
    set_paper_trade_service,
)
from app.routes.spread_analyzer import _qqq_analysis_path, router as spread_analyzer_router
from app.routes.opportunity_scanner import router as opportunity_scanner_router, set_opportunity_scanner_service
from app.routes.ai_report import router as ai_report_router, set_ai_report_service
from app.routes.trade_decision import router as trade_decision_router, set_trade_decision_engine
from app.routes.global_refresh import router as global_refresh_router, set_global_refresh_service
from app.repositories.watchlist_repository import WatchlistRepository
from app.services.ibkr.ibkr_sync_service import IBKRSyncService
from app.services.ibkr.position_sync_job import PositionSyncJob
from app.services.market_regime.market_regime_service import MarketRegimeService
from app.services.paper_trade_service import PaperTradeService
from app.services.market_intelligence.market_intelligence_service import MarketIntelligenceService
from app.services.opportunity_scanner.opportunity_scanner_service import OpportunityScannerService
from app.services.ai_report_service import AiReportService
from app.services.trade_decision.trade_decision_engine import TradeDecisionEngine
from app.services.global_refresh_service import GlobalRefreshService

_engine = None
_paper_service: PaperTradeService | None = None
_ibkr_sync: IBKRSyncService | None = None
_position_sync_job: PositionSyncJob | None = None
_market_regime_service: MarketRegimeService | None = None
_trade_decision_engine: TradeDecisionEngine | None = None
_market_intelligence_service: MarketIntelligenceService | None = None
_opportunity_scanner_service: OpportunityScannerService | None = None
_ai_report_service: AiReportService | None = None
_global_refresh_service: GlobalRefreshService | None = None
_ibkr_news_client = None


def get_position_sync_job() -> PositionSyncJob | None:
    return _position_sync_job


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine, _paper_service, _ibkr_sync, _position_sync_job, _market_regime_service, _trade_decision_engine, _market_intelligence_service, _opportunity_scanner_service, _ai_report_service, _global_refresh_service, _ibkr_news_client
    db_url = settings.database_url
    if db_url.startswith("sqlite:///./"):
        rel = db_url.replace("sqlite:///./", "")
        db_path = Path(__file__).resolve().parent.parent / rel
        db_url = f"sqlite:///{db_path}"
    _engine = get_engine(db_url)
    init_db(_engine)
    _paper_service = PaperTradeService(_engine, analysis_dir_fn=_qqq_analysis_path)
    set_paper_trade_service(_paper_service)
    _ibkr_sync = IBKRSyncService(_engine, _paper_service)
    set_ibkr_sync_service(_ibkr_sync)
    _market_regime_service = MarketRegimeService(_engine, analysis_dir_fn=_qqq_analysis_path)
    set_market_regime_service(_market_regime_service)
    _trade_decision_engine = TradeDecisionEngine(_engine)
    set_trade_decision_engine(_trade_decision_engine)

    # Initialize IBKR News client (optional)
    if settings.ibkr_news_enabled:
        try:
            from app.services.news_intelligence.ibkr_news_client import IbkrNewsClient
            _ibkr_news_client = IbkrNewsClient(
                host=settings.tws_host,
                port=settings.tws_port,
                client_id=settings.ibkr_news_client_id,
                cache_ttl=settings.ibkr_news_cache_ttl_seconds,
            )
        except Exception:
            _ibkr_news_client = None

    _market_intelligence_service = MarketIntelligenceService(
        _engine,
        market_regime_service=_market_regime_service,
        ibkr_news_client=_ibkr_news_client,
    )
    set_market_intelligence_service(_market_intelligence_service)
    _opportunity_scanner_service = OpportunityScannerService(
        _engine,
        analysis_dir_fn=_qqq_analysis_path,
        market_regime_service=_market_regime_service,
        market_intelligence_service=_market_intelligence_service,
    )
    set_opportunity_scanner_service(_opportunity_scanner_service)
    _ai_report_service = AiReportService(
        _engine,
        analysis_dir_fn=_qqq_analysis_path,
        market_regime_service=_market_regime_service,
        market_intelligence_service=_market_intelligence_service,
        opportunity_scanner_service=_opportunity_scanner_service,
        paper_trade_service=_paper_service,
        trade_decision_engine=_trade_decision_engine,
        ibkr_sync_service=_ibkr_sync,
    )
    set_ai_report_service(_ai_report_service)
    _global_refresh_service = GlobalRefreshService(
        market_intelligence_service=_market_intelligence_service,
        market_regime_service=_market_regime_service,
        opportunity_scanner_service=_opportunity_scanner_service,
    )
    set_global_refresh_service(_global_refresh_service)
    WatchlistRepository(_engine).seed_defaults_if_empty()
    _position_sync_job = PositionSyncJob(
        sync_fn=_ibkr_sync.sync_from_ibkr,
        interval_seconds=settings.ibkr_auto_sync_seconds,
    )
    _position_sync_job.start()
    yield
    if _position_sync_job:
        _position_sync_job.stop()
    if _ibkr_news_client:
        try:
            _ibkr_news_client.disconnect()
        except Exception:
            pass


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(spread_analyzer_router)
app.include_router(paper_trading_router)
app.include_router(market_regime_router)
app.include_router(trade_decision_router)
app.include_router(news_intelligence_router)
app.include_router(market_intelligence_router)
app.include_router(opportunity_scanner_router)
app.include_router(ai_report_router)
app.include_router(global_refresh_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    now = datetime.now(UTC)
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        timestamp=now,
        as_of=now,
        execution_mode="paper_only",
        data_status="live",
    )
