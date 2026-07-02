from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import HealthResponse
from app.routes.spread_analyzer import router as spread_analyzer_router

app = FastAPI(title=settings.app_name, version=settings.app_version)

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
