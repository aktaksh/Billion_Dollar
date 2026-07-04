"""Global refresh API routes — Market Open Refresh + Analyze Top N."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services.global_refresh_service import GlobalRefreshService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/global", tags=["global-refresh"])

_service: GlobalRefreshService | None = None
_analyze_top_n_lock = threading.Lock()
_analyze_top_n_job: dict[str, Any] | None = None


def set_global_refresh_service(svc: GlobalRefreshService) -> None:
    global _service
    _service = svc


def get_service() -> GlobalRefreshService:
    if _service is None:
        raise RuntimeError("GlobalRefreshService not initialized")
    return _service


class AnalyzeTopNIn(BaseModel):
    n: int = 5


# ---------------------------------------------------------------------------
# Market Open Refresh
# ---------------------------------------------------------------------------


@router.post("/market-open-refresh")
def market_open_refresh() -> dict[str, Any]:
    """Lightweight morning refresh — NO IBKR, NO option chains."""
    svc = get_service()
    result = svc.market_open_refresh()
    return result.to_dict()


@router.get("/market-open-refresh/status")
def market_open_refresh_status() -> dict[str, Any]:
    """Return last Market Open Refresh result (if any)."""
    svc = get_service()
    last = svc.last_result
    if not last:
        return {"status": "never_run", "timestamps": None, "modules": []}
    return last.to_dict()


# ---------------------------------------------------------------------------
# Analyze Top N
# ---------------------------------------------------------------------------


def _qqq_analyzer_project_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "qqq_spread_analyzer"


def _run_sequential_analysis(symbols: list[str], job: dict[str, Any]) -> None:
    """Run analysis subprocess for each symbol sequentially."""
    completed: list[dict[str, Any]] = []
    project_dir = _qqq_analyzer_project_dir()

    for i, sym in enumerate(symbols):
        with _analyze_top_n_lock:
            job["current_index"] = i
            job["current_symbol"] = sym
            job["progress"] = f"Analyzing {i + 1}/{len(symbols)} {sym}"

        cmd = [
            settings.qqq_analyzer_poetry,
            "run",
            "python",
            "-m",
            "src.main",
            "--symbol",
            sym,
            "--mode",
            "analyze",
        ]
        t0 = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )
            elapsed = int((time.time() - t0) * 1000)
            completed.append({
                "symbol": sym,
                "status": "done" if result.returncode == 0 else "failed",
                "duration_ms": elapsed,
                "error": (result.stderr or "")[:500] if result.returncode != 0 else None,
            })
            if result.returncode != 0:
                logger.warning("Analyze Top N: %s failed (exit %d)", sym, result.returncode)
        except subprocess.TimeoutExpired:
            elapsed = int((time.time() - t0) * 1000)
            completed.append({"symbol": sym, "status": "timeout", "duration_ms": elapsed, "error": "Timeout (300s)"})
            logger.warning("Analyze Top N: %s timed out", sym)
        except Exception as exc:
            elapsed = int((time.time() - t0) * 1000)
            completed.append({"symbol": sym, "status": "error", "duration_ms": elapsed, "error": str(exc)[:500]})
            logger.exception("Analyze Top N: %s raised exception", sym)
            with _analyze_top_n_lock:
                job["status"] = "stopped"
                job["error"] = f"IBKR unavailable or connection error: {str(exc)[:200]}"
                job["completed_symbols"] = completed
                job["finished_at"] = datetime.now(UTC).isoformat()
            return

    with _analyze_top_n_lock:
        job["status"] = "done"
        job["completed_symbols"] = completed
        job["finished_at"] = datetime.now(UTC).isoformat()
        job["progress"] = f"Completed {len(completed)}/{len(symbols)}"


@router.post("/analyze-top-n")
def analyze_top_n(body: AnalyzeTopNIn | None = None) -> dict[str, Any]:
    """Run full IBKR analysis sequentially for top N symbols by Market Opportunity Score."""
    global _analyze_top_n_job
    svc = get_service()
    n = body.n if body else 5

    with _analyze_top_n_lock:
        if _analyze_top_n_job and _analyze_top_n_job.get("status") == "running":
            return {
                "status": "already_running",
                "job": _analyze_top_n_job,
            }

    last = svc.last_result
    if not last or not last.scanner_payload:
        raise HTTPException(
            status_code=400,
            detail="Run Market Open Refresh first to rank symbols.",
        )

    results = last.scanner_payload.get("results") or []
    sorted_results = sorted(results, key=lambda r: -r.get("market_opportunity_score", r.get("opportunity_score", 0)))
    symbols = [r["symbol"] for r in sorted_results[:n]]

    if not symbols:
        raise HTTPException(status_code=400, detail="No symbols to analyze.")

    job_id = uuid4().hex
    job: dict[str, Any] = {
        "job_id": job_id,
        "status": "running",
        "symbols": symbols,
        "n": n,
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
        "current_index": 0,
        "current_symbol": symbols[0],
        "progress": f"Analyzing 1/{len(symbols)} {symbols[0]}",
        "completed_symbols": [],
        "error": None,
    }

    with _analyze_top_n_lock:
        _analyze_top_n_job = job

    thread = threading.Thread(target=_run_sequential_analysis, args=(symbols, job), daemon=True)
    thread.start()

    return {"status": "started", "job": job}


@router.get("/analyze-top-n/status")
def analyze_top_n_status() -> dict[str, Any]:
    """Get current Analyze Top N job status."""
    with _analyze_top_n_lock:
        if not _analyze_top_n_job:
            return {"status": "no_job"}
        return {"status": _analyze_top_n_job["status"], "job": dict(_analyze_top_n_job)}
