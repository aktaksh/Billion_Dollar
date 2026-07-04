"""API tests for AI Report generation endpoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.routes import ai_report as ai_report_routes

client = TestClient(app)

MOCK_REPORT = {
    "report_meta": {
        "generated_at": "2026-07-04T00:00:00+00:00",
        "app": "Billion Dollar",
        "version": "1.0.0",
        "mode": "research_only",
        "data_status": "partial",
    },
    "module_freshness": {},
    "final_decision_context": {
        "single_authority": "Trade Decision Engine",
        "note": "Only TDE produces final strategy recommendations.",
        "current_decision_qqq": None,
        "current_decision_extra": None,
        "recent_decisions_qqq": [],
        "recent_decisions_extra": None,
        "conflicts_detected": [],
        "blocking_conditions": ["No analyzer snapshot — cannot evaluate spreads"],
    },
    "qqq_spread_analyzer": {"data_unavailable": True, "reason": "No analyzer snapshot for QQQ. Run analysis."},
    "options_spread_strategy": "no_symbol_specified",
    "market_regime": {"data_unavailable": True, "reason": "Market Regime service returned no data"},
    "market_intelligence": {"data_unavailable": True, "reason": "Market Intelligence unavailable"},
    "opportunity_scanner": {"data_unavailable": True, "reason": "Opportunity Scanner has no results"},
    "paper_trading": {"summary": "data_unavailable", "analytics": "data_unavailable", "open_positions": [], "open_count": 0},
    "ibkr_status": "data_unavailable",
    "warnings": [],
    "errors": [],
}


def _make_mock_service():
    mock = MagicMock()
    mock.generate.return_value = MOCK_REPORT
    mock.write_files.return_value = ("/tmp/report.json", "/tmp/report.md")
    return mock


class TestAiReportGenerate:
    def setup_method(self):
        self._mock = _make_mock_service()
        ai_report_routes.set_ai_report_service(self._mock)

    def teardown_method(self):
        ai_report_routes._service = None

    def test_generate_returns_report(self):
        res = client.post("/api/ai-report/generate", json={})
        assert res.status_code == 200
        data = res.json()
        assert data["report_meta"]["app"] == "Billion Dollar"
        assert data["report_meta"]["mode"] == "research_only"
        self._mock.generate.assert_called_once()
        self._mock.write_files.assert_called_once_with(MOCK_REPORT)

    def test_generate_with_symbol(self):
        res = client.post("/api/ai-report/generate", json={"symbol": "NVDA"})
        assert res.status_code == 200
        self._mock.generate.assert_called_once_with(symbol="NVDA")

    def test_download_not_found_when_no_file(self):
        import tempfile
        from app.routes import ai_report as route_mod
        fake_dir = Path(tempfile.mkdtemp()) / "empty_reports"
        orig = route_mod.REPORTS_DIR
        route_mod.REPORTS_DIR = fake_dir
        try:
            res = client.get("/api/ai-report/download/json")
            assert res.status_code == 404
        finally:
            route_mod.REPORTS_DIR = orig

    def test_download_invalid_format(self):
        res = client.get("/api/ai-report/download/csv")
        assert res.status_code == 400
        assert "Invalid format" in res.text
