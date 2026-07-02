from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DataStatus = Literal["live", "stale", "mock", "degraded", "disconnected"]
ExecutionMode = Literal["paper_only", "read_only", "manual_approval", "close_only", "halted"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    version: str
    timestamp: datetime
    as_of: datetime
    execution_mode: ExecutionMode = "paper_only"
    data_status: DataStatus = "live"


class QqqSpreadRunIn(BaseModel):
    symbol: str = "QQQ"
    no_cache: bool = False


class QqqSpreadRunOut(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    started_at: datetime
    message: str = ""


class QqqSpreadRunStatusOut(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    started_at: datetime
    finished_at: datetime | None = None
    exit_code: int | None = None
    error: str | None = None
    symbol: str = "QQQ"


class AnalyzerChainRefreshOut(BaseModel):
    as_of: datetime
    symbol: str
    enqueued: bool
    message: str
    job_id: str | None = None
    status: Literal["queued", "running", "done", "failed"] = "queued"


class OptionsSpreadStrategyRunIn(BaseModel):
    symbol: str
    no_cache: bool = False
