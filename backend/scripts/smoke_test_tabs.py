#!/usr/bin/env python3
"""Run all tab endpoints and print a console summary (no pytest required).

Usage:
  cd backend
  PYTHONPATH=. ../pyenv_global/bin/python scripts/smoke_test_tabs.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Ensure backend root on path when run as script
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class _MockBroker:
    name = "mock"

    def is_available(self) -> tuple[bool, str]:
        return False, "mock broker (smoke script)"

    def list_option_positions(self) -> list[dict[str, Any]]:
        return []

    def fetch_quotes_for_trades(self, trades: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
        return {}

    def fetch_underlying_price(self, symbol: str) -> float:
        return 0.0

    def enrich_spreads_with_quotes(self, spreads: list[Any]) -> int:
        return 0


def _analysis_fixture(symbol: str) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "symbol": symbol,
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


def _detail(method: str, path: str, params: dict[str, str] | None, res) -> str:
    if res.status_code >= 400:
        return res.text[:100].replace("\n", " ")
    try:
        body = res.json()
    except Exception:
        return res.text[:80]
    if path == "/health":
        return f"app={body.get('app')} status={body.get('status')}"
    if "qqq-spread-analyzer" in path or "options-spread-strategy" in path:
        return f"symbol={body.get('symbol')} price={body.get('underlying_price')}"
    if "paper-trading/summary" in path:
        return f"open={body.get('open_count', 0)} closed={body.get('closed_count', 0)}"
    if "market-regime" in path:
        s = body.get("summary") or {}
        return f"regime={s.get('regime_name')} score={s.get('regime_score')}"
    if "market-intelligence/dashboard" in path:
        s = body.get("summary") or {}
        return f"news_score={s.get('news_score_0_to_100')} watchlist={len(body.get('watchlist') or [])}"
    if "opportunity-scanner" in path:
        return f"results={len(body.get('results') or [])}"
    if "ai-report" in path:
        return f"modules={len(body.get('module_freshness') or {})}" if body else "no report"
    return json.dumps(body)[:80]


def main() -> int:
    from fastapi.testclient import TestClient

    from app.config import settings

    settings.ibkr_news_enabled = False

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        for sym in ("QQQ", "NVDA", "SPY"):
            (data_dir / f"latest_analysis_{sym}.json").write_text(
                json.dumps(_analysis_fixture(sym)), encoding="utf-8"
            )
        settings.qqq_analyzer_data_dir = str(data_dir)

        import app.routes.spread_analyzer as sa

        def _path(sym: str) -> Path:
            return data_dir / f"latest_analysis_{sym.strip().upper()}.json"

        sa._qqq_analysis_path = _path

        mock = _MockBroker()
        patches = [
            patch("app.services.broker.broker_provider.get_broker_provider", return_value=mock),
            patch("app.services.market_regime.data_adapters.get_broker_provider", return_value=mock),
        ]
        for p in patches:
            p.start()

        try:
            from app.main import app

            with TestClient(app) as client:
                tabs: list[tuple[str, str, str, dict[str, str] | None]] = [
                ("Health", "GET", "/health", None),
                ("QQQ Spread Analyzer", "GET", "/api/qqq-spread-analyzer/latest", {"symbol": "QQQ"}),
                ("Options Spread Strategy", "GET", "/api/options-spread-strategy/latest", {"symbol": "NVDA"}),
                ("Paper Trading Lab", "GET", "/api/paper-trading/summary", None),
                ("Market Regime", "GET", "/api/market-regime/latest", None),
                ("Market Intelligence", "GET", "/api/market-intelligence/dashboard", None),
                ("Opportunity Scanner", "GET", "/api/opportunity-scanner/latest", None),
                ("Global Refresh", "GET", "/api/global/market-open-refresh/status", None),
                ("AI Report", "GET", "/api/ai-report/latest", None),
                ("News Signal QQQ", "GET", "/api/market-intelligence/signal/QQQ", None),
                ]

                print("=" * 72)
                print("Billion Dollar — Tab Smoke Test")
                print("=" * 72)

                failed = 0
                for label, method, path, params in tabs:
                    res = client.get(path, params=params) if method == "GET" else client.post(path, params=params)
                    ok = 200 <= res.status_code < 300 or (label == "AI Report" and res.status_code == 404)
                    icon = "OK" if ok else "FAIL"
                    if not ok:
                        failed += 1
                    detail = _detail(method, path, params, res)
                    print(f"  [{icon}] {label:<28} HTTP {res.status_code}  {detail}")

                print("=" * 72)
                if failed:
                    print(f"FAILED: {failed} tab(s)")
                    return 1
                print("All tabs responded successfully.")
                return 0
        finally:
            for p in patches:
                p.stop()


if __name__ == "__main__":
    raise SystemExit(main())
