"""API tests for Opportunity Scanner."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.routes import opportunity_scanner as os_routes

client = TestClient(app)

MOCK_PAYLOAD = {
    "timestamp": "2026-07-03T12:00:00+00:00",
    "header": {
        "last_updated": "2026-07-03T12:00:00+00:00",
        "symbols_scanned": 2,
        "data_freshness": "Partial",
    },
    "summary": {
        "best_bullish": {"symbol": "NVDA", "direction_candidate": "Bullish", "opportunity_score": 78},
        "best_bearish": None,
        "highest_opportunity": {"symbol": "NVDA", "opportunity_score": 78},
        "highest_risk": {"symbol": "TSLA", "risk_score": 55},
        "symbols_scanned": 2,
        "data_quality": "Mixed",
        "bullish_count": 1,
        "bearish_count": 0,
        "neutral_count": 1,
    },
    "results": [
        {
            "rank": 1,
            "symbol": "NVDA",
            "direction_candidate": "Bullish",
            "opportunity_score": 78,
            "bull_score": 82,
            "bear_score": 40,
            "confidence_score": 65,
            "risk_score": 30,
            "news_score": 70,
            "technical_score": 75,
            "liquidity_score": 60,
            "reason": "Bull score leads",
            "reason_json": {"summary": "Bull score leads", "bull_evidence": ["Price above EMA20"]},
            "has_analyzer_snapshot": True,
            "has_options_data": True,
            "has_news_data": True,
        },
    ],
    "disclaimer": "Direction Candidate only",
}


def _with_svc(svc: MagicMock):
    os_routes._service = svc
    app.dependency_overrides[os_routes.get_service] = lambda: svc


def _clear_svc():
    os_routes._service = None
    app.dependency_overrides.pop(os_routes.get_service, None)


def test_latest():
    svc = MagicMock()
    svc.get_latest.return_value = MOCK_PAYLOAD
    _with_svc(svc)
    try:
        res = client.get("/api/opportunity-scanner/latest")
        assert res.status_code == 200
        body = res.json()
        assert body["results"][0]["symbol"] == "NVDA"
        assert body["results"][0]["direction_candidate"] == "Bullish"
        assert "Bull Call" not in body["disclaimer"]
    finally:
        _clear_svc()


def test_refresh():
    svc = MagicMock()
    svc.scan.return_value = MOCK_PAYLOAD
    _with_svc(svc)
    try:
        res = client.post("/api/opportunity-scanner/refresh", json={"refresh_news": False})
        assert res.status_code == 200
        svc.scan.assert_called_once_with(refresh_news=False)
    finally:
        _clear_svc()


def test_symbol_detail():
    svc = MagicMock()
    svc.get_symbol.return_value = MOCK_PAYLOAD["results"][0]
    _with_svc(svc)
    try:
        res = client.get("/api/opportunity-scanner/symbol/NVDA")
        assert res.status_code == 200
        assert res.json()["symbol"] == "NVDA"
    finally:
        _clear_svc()


def test_direction_not_final_decision():
    """Scanner must not emit final strategy labels."""
    svc = MagicMock()
    svc.get_latest.return_value = MOCK_PAYLOAD
    _with_svc(svc)
    try:
        text = client.get("/api/opportunity-scanner/latest").text
        assert "Bull Call Spread" not in text
        assert "Bear Put Spread" not in text
        assert "final_decision" not in text.lower()
    finally:
        _clear_svc()
