"""Smoke tests for every top-level tab + global toolbar endpoints.

Run with visible console output:
  cd backend
  PYTHONPATH=. ../pyenv_global/bin/python -m pytest tests/test_all_tabs_smoke.py -v -s
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import settings


def _qqq_analysis_fixture() -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "symbol": "QQQ",
        "underlying_price": 500.0,
        "bias": "Neutral",
        "confidence": "Medium",
        "suggested_action": "No trade / wait",
        "bullish_score": 6,
        "bearish_score": 1,
        "spread_candidates": [],
        "daily_indicators": {
            "close": 500.0,
            "ema20": 495.0,
            "ema50": 490.0,
            "sma200": 480.0,
            "rsi14": 55.0,
            "macd_line": 1.5,
            "macd_signal": 1.0,
            "bb_upper": 510.0,
            "bb_mid": 500.0,
            "bb_lower": 490.0,
            "atr14": 5.0,
        },
        "intraday_indicators": {
            "close": 501.0,
            "ema21": 499.0,
            "rsi14": 52.0,
            "macd_line": 0.5,
            "macd_signal": 0.3,
        },
        "score": {"intraday_timing_bull": 3, "daily_checks": {}, "intraday_checks": {}},
        "support_levels": [],
        "resistance_levels": [],
        "diagnostics": {"intraday_timeframe": "2H"},
    }


@pytest.fixture
def analysis_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "analysis"
    data_dir.mkdir()
    for sym in ("QQQ", "NVDA", "SPY"):
        payload = _qqq_analysis_fixture()
        payload["symbol"] = sym
        (data_dir / f"latest_analysis_{sym}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    return data_dir


@pytest.fixture
def tab_client(client: TestClient, analysis_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "qqq_analyzer_data_dir", str(analysis_dir))

    import app.routes.spread_analyzer as sa

    def _path(sym: str) -> Path:
        return analysis_dir / f"latest_analysis_{sym.strip().upper()}.json"

    monkeypatch.setattr(sa, "_qqq_analysis_path", _path)
    return client


def _print_smoke(label: str, status: int, detail: str) -> None:
    icon = "OK" if 200 <= status < 300 else "FAIL"
    print(f"  [{icon}] {label:<28} HTTP {status}  {detail}")


def test_health(tab_client: TestClient) -> None:
    res = tab_client.get("/health")
    body = res.json()
    detail = f"app={body.get('app')} status={body.get('status')}"
    _print_smoke("Health", res.status_code, detail)
    assert res.status_code == 200
    assert body["status"] == "ok"


def test_qqq_spread_analyzer_tab(tab_client: TestClient) -> None:
    res = tab_client.get("/api/qqq-spread-analyzer/latest", params={"symbol": "QQQ"})
    detail = "no snapshot"
    if res.status_code == 200:
        body = res.json()
        detail = f"symbol={body.get('symbol')} price={body.get('underlying_price')}"
    _print_smoke("QQQ Spread Analyzer", res.status_code, detail)
    assert res.status_code == 200


def test_options_spread_strategy_tab(tab_client: TestClient) -> None:
    res = tab_client.get("/api/options-spread-strategy/latest", params={"symbol": "NVDA"})
    detail = "no snapshot"
    if res.status_code == 200:
        body = res.json()
        detail = f"symbol={body.get('symbol')} candidates={len(body.get('spread_candidates') or [])}"
    _print_smoke("Options Spread Strategy", res.status_code, detail)
    assert res.status_code == 200


def test_paper_trading_lab_tab(tab_client: TestClient) -> None:
    trades = tab_client.get("/api/paper-trading/trades")
    summary = tab_client.get("/api/paper-trading/summary")
    detail = f"trades={len(trades.json()) if trades.status_code == 200 else '?'} summary={summary.status_code}"
    _print_smoke("Paper Trading Lab", summary.status_code, detail)
    assert trades.status_code == 200
    assert summary.status_code == 200


def test_market_regime_tab(tab_client: TestClient) -> None:
    res = tab_client.get("/api/market-regime/latest")
    detail = res.text[:80]
    if res.status_code == 200:
        body = res.json()
        detail = f"regime={body.get('summary', {}).get('regime_name')} score={body.get('summary', {}).get('regime_score')}"
    _print_smoke("Market Regime", res.status_code, detail)
    assert res.status_code == 200
    assert "summary" in res.json()


def test_market_intelligence_tab(tab_client: TestClient) -> None:
    res = tab_client.get("/api/market-intelligence/dashboard")
    detail = res.text[:80]
    if res.status_code == 200:
        body = res.json()
        score = body.get("summary", {}).get("news_score_0_to_100")
        wl = len(body.get("watchlist") or [])
        detail = f"news_score={score} watchlist={wl} ibkr={body.get('ibkr_news_status', {}).get('available')}"
    _print_smoke("Market Intelligence", res.status_code, detail)
    assert res.status_code == 200
    assert "summary" in res.json()


def test_opportunity_scanner_tab(tab_client: TestClient) -> None:
    res = tab_client.get("/api/opportunity-scanner/latest")
    detail = res.text[:80]
    if res.status_code == 200:
        body = res.json()
        n = len(body.get("results") or [])
        detail = f"symbols_scanned={body.get('header', {}).get('symbols_scanned')} results={n}"
    _print_smoke("Opportunity Scanner", res.status_code, detail)
    assert res.status_code == 200


def test_global_refresh_status(tab_client: TestClient) -> None:
    res = tab_client.get("/api/global/market-open-refresh/status")
    detail = "no prior refresh" if res.status_code == 200 else res.text[:60]
    _print_smoke("Global Refresh Status", res.status_code, detail)
    assert res.status_code == 200


def test_ai_report_latest(tab_client: TestClient) -> None:
    res = tab_client.get("/api/ai-report/latest")
    detail = "no report yet" if res.status_code == 404 else "report exists"
    if res.status_code == 200:
        body = res.json()
        detail = f"modules={len(body.get('module_freshness') or {})}"
    _print_smoke("AI Report (toolbar)", res.status_code, detail)
    assert res.status_code in (200, 404)


def test_news_intelligence_signal(tab_client: TestClient) -> None:
    res = tab_client.get("/api/market-intelligence/signal/QQQ")
    detail = res.text[:80]
    if res.status_code == 200:
        sig = res.json().get("newsSignal") or {}
        detail = f"label={sig.get('label')} score={sig.get('news_score_0_to_100')}"
    _print_smoke("News Signal QQQ", res.status_code, detail)
    assert res.status_code == 200


@pytest.fixture(autouse=True)
def _smoke_banner() -> None:
    print("\n" + "=" * 72)
    print("Billion Dollar — All Tabs Smoke Test")
    print("=" * 72)
