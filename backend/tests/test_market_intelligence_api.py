"""API tests for Market Intelligence Center."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.routes import market_intelligence as mi_routes

client = TestClient(app)

MOCK_DASHBOARD = {
    "timestamp": "2026-07-03T10:00:00+00:00",
    "header": {"last_updated": None, "api_status": "Online"},
    "summary": {
        "overall_sentiment": "Neutral",
        "news_score_0_to_100": 52,
        "critical_events_count": 1,
        "high_impact_events_count": 3,
        "upcoming_earnings_count": 2,
        "api_health": "Online",
    },
    "regime_context": {"available": True, "current_regime": "Bull Trend"},
    "watchlist": [{"symbol": "NVDA", "enabled": True, "priority": 1}],
    "critical_events": [],
    "catalyst_calendar": [],
    "sec_filings": [],
    "sentiment_analytics": {
        "split": {"bullish": 1, "bearish": 0, "neutral": 5},
        "trend": [],
        "most_positive": [],
        "most_negative": [],
    },
    "api_budget": {
        "finnhub": {"used": 5, "limit": 1000},
        "planned_calls": 3,
        "skipped_calls": 0,
        "skip_reasons": [],
    },
    "activity_log": [],
    "news_signal_output": {"primary": {"symbol": "QQQ"}, "watchlist_signals": [], "consumers": []},
    "comments": [],
}


def _with_svc(svc: MagicMock):
    mi_routes._service = svc
    app.dependency_overrides[mi_routes.get_service] = lambda: svc


def _clear_svc():
    mi_routes._service = None
    app.dependency_overrides.pop(mi_routes.get_service, None)


def test_dashboard():
    svc = MagicMock()
    svc.build_dashboard.return_value = MOCK_DASHBOARD
    _with_svc(svc)
    try:
        res = client.get("/api/market-intelligence/dashboard")
        assert res.status_code == 200
        assert res.json()["summary"]["news_score_0_to_100"] == 52
    finally:
        _clear_svc()


def test_refresh_modes():
    svc = MagicMock()
    svc.refresh.return_value = {**MOCK_DASHBOARD, "refresh_result": {"status": "ok", "refresh_mode": "quick"}}
    _with_svc(svc)
    try:
        for mode in ("quick", "standard", "deep"):
            res = client.post("/api/market-intelligence/refresh", json={"mode": mode})
            assert res.status_code == 200
            svc.refresh.assert_called_with(mode)
    finally:
        _clear_svc()


def test_export():
    svc = MagicMock()
    svc.export_json.return_value = '{"ok": true}'
    _with_svc(svc)
    try:
        res = client.get("/api/market-intelligence/export")
        assert res.status_code == 200
        assert "ok" in res.text
    finally:
        _clear_svc()


def test_watchlist_patch():
    svc = MagicMock()
    wl = MagicMock()
    wl.update.return_value = {"symbol": "NVDA", "enabled": False, "priority": 2}
    svc._watchlist.return_value = wl
    _with_svc(svc)
    try:
        res = client.patch("/api/market-intelligence/watchlist/NVDA", json={"enabled": False})
        assert res.status_code == 200
    finally:
        _clear_svc()


def test_news_intelligence_delegates():
    svc = MagicMock()
    svc.quick_refresh_for_symbol.return_value = {"status": "ok", "newsSignal": {"symbol": "QQQ"}}
    _with_svc(svc)
    try:
        res = client.post("/api/news-intelligence/quick-refresh", json={"symbol": "QQQ"})
        assert res.status_code == 200
        svc.quick_refresh_for_symbol.assert_called_once_with("QQQ")
    finally:
        _clear_svc()


def test_get_signal_delegates():
    svc = MagicMock()
    svc.get_latest_signal.return_value = {"status": "ok", "newsSignal": {"symbol": "QQQ"}}
    _with_svc(svc)
    try:
        res = client.get("/api/news-intelligence/signal/QQQ")
        assert res.status_code == 200
        svc.get_latest_signal.assert_called_once_with("QQQ")
    finally:
        _clear_svc()


def test_ticker_signals_endpoint():
    svc = MagicMock()
    svc.list_ticker_signals.return_value = [
        {
            "symbol": "NVDA",
            "news_bias": "Bullish",
            "news_quality_score": 88.0,
            "catalyst_strength_score": 45.0,
            "net_impact_score": 38.0,
            "bullish_count": 3,
            "bearish_count": 1,
            "neutral_count": 0,
            "top_catalyst": "NVDA beats earnings estimates",
            "top_risk": None,
            "llm_summary": "3 bullish catalyst(s) outweigh 1 risk event(s).",
            "confidence": "High",
            "last_updated": "2026-07-05T10:00:00+00:00",
        }
    ]
    _with_svc(svc)
    try:
        res = client.get("/api/market-intelligence/ticker-signals")
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 1
        assert body[0]["symbol"] == "NVDA"
        assert body[0]["news_bias"] == "Bullish"
        svc.list_ticker_signals.assert_called_once()
    finally:
        _clear_svc()
