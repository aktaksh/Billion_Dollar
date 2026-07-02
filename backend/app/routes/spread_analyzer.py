from __future__ import annotations

import json
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.models import (
    AnalyzerChainRefreshOut,
    OptionsSpreadStrategyRunIn,
    QqqSpreadRunIn,
    QqqSpreadRunOut,
    QqqSpreadRunStatusOut,
)

router = APIRouter()

_qqq_spread_jobs: dict[str, dict[str, Any]] = {}
_qqq_spread_jobs_lock = threading.Lock()
_spread_strategy_jobs: dict[str, dict[str, Any]] = {}
_spread_strategy_jobs_lock = threading.Lock()


def _qqq_analyzer_data_dir() -> Path:
    if settings.qqq_analyzer_data_dir:
        return Path(settings.qqq_analyzer_data_dir)
    return Path(__file__).resolve().parents[3] / "qqq_spread_analyzer" / "data"


def _qqq_analyzer_project_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "qqq_spread_analyzer"


def _qqq_analysis_path(symbol: str) -> Path:
    sym = symbol.strip().upper()
    return _qqq_analyzer_data_dir() / f"latest_analysis_{sym}.json"


def _analyzer_last_run_log_path() -> Path:
    return _qqq_analyzer_data_dir() / "analyzer_last_run.log"


def _write_analyzer_run_log(
    *,
    symbol: str,
    mode: str,
    job_id: str,
    cmd: list[str],
    cwd: Path,
    result: subprocess.CompletedProcess[str] | None = None,
    exc: BaseException | None = None,
) -> None:
    path = _analyzer_last_run_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"started_at={datetime.now(UTC).isoformat()}",
        f"job_id={job_id}",
        f"symbol={symbol.strip().upper()}",
        f"mode={mode}",
        f"cwd={cwd}",
        f"command={' '.join(cmd)}",
        "",
    ]
    if result is not None:
        lines.extend([
            f"finished_at={datetime.now(UTC).isoformat()}",
            f"exit_code={result.returncode}",
            "",
            "=== stdout ===",
            result.stdout or "(empty)",
            "",
            "=== stderr ===",
            result.stderr or "(empty)",
        ])
    if exc is not None:
        lines.extend([
            f"finished_at={datetime.now(UTC).isoformat()}",
            "exit_code=-1",
            "",
            "=== exception ===",
            str(exc),
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _build_analyzer_cmd(symbol: str, mode: str, *, no_cache: bool = False) -> list[str]:
    sym = symbol.strip().upper()
    cmd = [
        settings.qqq_analyzer_poetry,
        "run",
        "python",
        "-m",
        "src.main",
        "--symbol",
        sym,
        "--mode",
        mode,
    ]
    if no_cache:
        cmd.append("--no-cache")
    return cmd


def _run_analyzer_subprocess(
    jobs: dict[str, dict[str, Any]],
    lock: threading.Lock,
    job_id: str,
    symbol: str,
    *,
    mode: str,
    no_cache: bool = False,
) -> None:
    sym = symbol.strip().upper()
    cmd = _build_analyzer_cmd(sym, mode, no_cache=no_cache)
    project_dir = _qqq_analyzer_project_dir()
    log_path = _analyzer_last_run_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")
    try:
        with lock:
            if job_id in jobs:
                jobs[job_id]["status"] = "running"
        result = subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=600,
        )
        _write_analyzer_run_log(
            symbol=sym,
            mode=mode,
            job_id=job_id,
            cmd=cmd,
            cwd=project_dir,
            result=result,
        )
        finished = datetime.now(UTC)
        with lock:
            if job_id not in jobs:
                return
            err_tail = (result.stderr or result.stdout or "").strip()
            log_hint = f" See {log_path} for full output."
            jobs[job_id].update({
                "status": "done" if result.returncode == 0 else "failed",
                "finished_at": finished,
                "exit_code": result.returncode,
                "error": (err_tail[:2000] + log_hint) if result.returncode != 0 else None,
                "log_path": str(log_path),
            })
    except Exception as exc:
        _write_analyzer_run_log(
            symbol=sym,
            mode=mode,
            job_id=job_id,
            cmd=cmd,
            cwd=project_dir,
            exc=exc,
        )
        with lock:
            if job_id in jobs:
                jobs[job_id].update({
                    "status": "failed",
                    "finished_at": datetime.now(UTC),
                    "exit_code": -1,
                    "error": f"{str(exc)[:2000]} See {log_path} for full output.",
                    "log_path": str(log_path),
                })


def _enqueue_analyzer_job(
    jobs: dict[str, dict[str, Any]],
    lock: threading.Lock,
    symbol: str,
    *,
    mode: str,
    message: str,
    no_cache: bool = False,
) -> AnalyzerChainRefreshOut:
    sym = symbol.strip().upper()
    project_dir = _qqq_analyzer_project_dir()
    if not project_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"Analyzer project not found at {project_dir}")
    with lock:
        for existing_id, job in list(jobs.items()):
            if job.get("symbol") == sym and job.get("status") in ("queued", "running"):
                return AnalyzerChainRefreshOut(
                    as_of=datetime.now(UTC),
                    symbol=sym,
                    enqueued=False,
                    message="Scan already in progress for this symbol",
                    job_id=existing_id,
                    status=job["status"],
                )
    job_id = uuid4().hex
    started_at = datetime.now(UTC)
    with lock:
        jobs[job_id] = {
            "job_id": job_id,
            "symbol": sym,
            "status": "queued",
            "started_at": started_at,
            "finished_at": None,
            "exit_code": None,
            "error": None,
            "mode": mode,
            "no_cache": no_cache,
        }
    thread = threading.Thread(
        target=_run_analyzer_subprocess,
        args=(jobs, lock, job_id, sym),
        kwargs={"mode": mode, "no_cache": no_cache},
        daemon=True,
    )
    thread.start()
    return AnalyzerChainRefreshOut(
        as_of=datetime.now(UTC),
        symbol=sym,
        enqueued=True,
        message=message,
        job_id=job_id,
        status="queued",
    )


def _analyzer_job_status(
    jobs: dict[str, dict[str, Any]],
    lock: threading.Lock,
    job_id: str,
    *,
    default_symbol: str = "",
) -> QqqSpreadRunStatusOut:
    with lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return QqqSpreadRunStatusOut(
        job_id=job_id,
        status=job["status"],
        started_at=job["started_at"],
        finished_at=job.get("finished_at"),
        exit_code=job.get("exit_code"),
        error=job.get("error"),
        symbol=str(job.get("symbol") or default_symbol).upper(),
    )


def _run_qqq_spread_analysis_job(job_id: str, symbol: str, *, no_cache: bool) -> None:
    _run_analyzer_subprocess(
        _qqq_spread_jobs,
        _qqq_spread_jobs_lock,
        job_id,
        symbol,
        mode="analyze",
        no_cache=no_cache,
    )


def _read_analysis_json(symbol: str) -> dict[str, Any]:
    path = _qqq_analysis_path(symbol)
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="No analysis yet. Run analysis from dashboard or CLI.",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid analysis JSON: {exc}") from exc


@router.get("/api/qqq-spread-analyzer/latest")
def get_qqq_spread_analysis_latest(symbol: str = Query(default="QQQ")) -> dict[str, Any]:
    return _read_analysis_json(symbol)


@router.post("/api/qqq-spread-analyzer/run", response_model=QqqSpreadRunOut)
def run_qqq_spread_analysis(payload: QqqSpreadRunIn) -> QqqSpreadRunOut:
    sym = payload.symbol.strip().upper()
    if not sym:
        raise HTTPException(status_code=422, detail="symbol is required")
    project_dir = _qqq_analyzer_project_dir()
    if not project_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"Analyzer project not found at {project_dir}")
    job_id = uuid4().hex
    started_at = datetime.now(UTC)
    with _qqq_spread_jobs_lock:
        for existing_id, job in list(_qqq_spread_jobs.items()):
            if job.get("symbol") == sym and job.get("status") in ("queued", "running"):
                return QqqSpreadRunOut(
                    job_id=existing_id,
                    status=job["status"],
                    started_at=job["started_at"],
                    message="Analysis already in progress for this symbol",
                )
        _qqq_spread_jobs[job_id] = {
            "job_id": job_id,
            "symbol": sym,
            "status": "queued",
            "started_at": started_at,
            "finished_at": None,
            "exit_code": None,
            "error": None,
            "no_cache": payload.no_cache,
        }
    thread = threading.Thread(
        target=_run_qqq_spread_analysis_job,
        args=(job_id, sym),
        kwargs={"no_cache": payload.no_cache},
        daemon=True,
    )
    thread.start()
    return QqqSpreadRunOut(
        job_id=job_id,
        status="queued",
        started_at=started_at,
        message=f"Queued QQQ spread analysis for {sym}",
    )


@router.get("/api/qqq-spread-analyzer/run/{job_id}", response_model=QqqSpreadRunStatusOut)
def get_qqq_spread_analysis_run_status(job_id: str) -> QqqSpreadRunStatusOut:
    with _qqq_spread_jobs_lock:
        job = _qqq_spread_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return QqqSpreadRunStatusOut(
        job_id=job_id,
        status=job["status"],
        started_at=job["started_at"],
        finished_at=job.get("finished_at"),
        exit_code=job.get("exit_code"),
        error=job.get("error"),
        symbol=str(job.get("symbol") or "QQQ"),
    )


@router.get("/api/options-spread-strategy/latest")
def get_options_spread_strategy_latest(symbol: str = Query(...)) -> dict[str, Any]:
    sym = symbol.strip().upper()
    if not sym:
        raise HTTPException(status_code=422, detail="symbol is required")
    return _read_analysis_json(sym)


@router.post("/api/options-spread-strategy/run", response_model=QqqSpreadRunOut)
def run_options_spread_strategy(payload: OptionsSpreadStrategyRunIn) -> QqqSpreadRunOut:
    sym = payload.symbol.strip().upper()
    if not sym:
        raise HTTPException(status_code=422, detail="symbol is required")
    out = _enqueue_analyzer_job(
        _spread_strategy_jobs,
        _spread_strategy_jobs_lock,
        sym,
        mode="analyze",
        message=f"Queued spread analysis for {sym}",
        no_cache=payload.no_cache,
    )
    return QqqSpreadRunOut(
        job_id=out.job_id or "",
        status=out.status,
        started_at=out.as_of,
        message=out.message,
    )


@router.get("/api/options-spread-strategy/run/{job_id}", response_model=QqqSpreadRunStatusOut)
def get_options_spread_strategy_run_status(job_id: str) -> QqqSpreadRunStatusOut:
    return _analyzer_job_status(_spread_strategy_jobs, _spread_strategy_jobs_lock, job_id)
