"""AI Report generation API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from app.services.ai_report_service import AiReportService, REPORTS_DIR, JSON_FILENAME, MD_FILENAME

router = APIRouter(prefix="/api/ai-report", tags=["ai-report"])

_service: AiReportService | None = None


def set_ai_report_service(service: AiReportService) -> None:
    global _service
    _service = service


def get_service() -> AiReportService:
    if _service is None:
        raise RuntimeError("AiReportService not initialized")
    return _service


class GenerateIn(BaseModel):
    symbol: str | None = None


@router.post("/generate")
def generate_report(
    body: GenerateIn | None = None,
    svc: AiReportService = Depends(get_service),
) -> dict[str, Any]:
    symbol = body.symbol if body else None
    report = svc.generate(symbol=symbol)
    json_path, md_path = svc.write_files(report)
    report["_files"] = {
        "json": str(json_path),
        "md": str(md_path),
        "download_json": "/api/ai-report/download/json",
        "download_md": "/api/ai-report/download/md",
    }
    return report


@router.get("/latest")
def get_latest(svc: AiReportService = Depends(get_service)) -> dict[str, Any]:
    json_path = REPORTS_DIR / JSON_FILENAME
    if json_path.is_file():
        import json
        return json.loads(json_path.read_text(encoding="utf-8"))
    report = svc.generate()
    svc.write_files(report)
    return report


@router.get("/download/{fmt}")
def download_report(fmt: str):
    if fmt == "json":
        path = REPORTS_DIR / JSON_FILENAME
        media = "application/json"
        filename = JSON_FILENAME
    elif fmt in ("md", "markdown"):
        path = REPORTS_DIR / MD_FILENAME
        media = "text/markdown"
        filename = MD_FILENAME
    else:
        return PlainTextResponse("Invalid format. Use 'json' or 'md'.", status_code=400)

    if not path.is_file():
        return PlainTextResponse("No report generated yet. POST /api/ai-report/generate first.", status_code=404)

    return FileResponse(path=str(path), media_type=media, filename=filename)
