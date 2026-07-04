"""Market Regime orchestration service."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.engine import Engine

from app.repositories.regime_history_repository import RegimeHistoryRepository
from app.services.market_regime.catalyst_calendar_service import CatalystCalendarService
from app.services.market_regime.data_adapters import INDEX_SYMBOLS, MarketDataAdapters
from app.services.market_regime.macro_risk_calculator import MacroRiskCalculator
from app.services.market_regime.market_breadth_calculator import MarketBreadthCalculator
from app.services.market_regime.market_regime_calculator import MarketRegimeCalculator
from app.services.market_regime.strategy_matrix_engine import StrategyMatrixEngine
from app.services.market_regime.volatility_regime_calculator import VolatilityRegimeCalculator


class MarketRegimeService:
    def __init__(self, engine: Engine, analysis_dir_fn: Callable[[str], Path]) -> None:
        self._adapters = MarketDataAdapters(analysis_dir_fn)
        self._breadth = MarketBreadthCalculator()
        self._volatility = VolatilityRegimeCalculator()
        self._macro = MacroRiskCalculator()
        self._calculator = MarketRegimeCalculator()
        self._strategy = StrategyMatrixEngine()
        self._catalysts = CatalystCalendarService()
        self._history = RegimeHistoryRepository(engine)
        self._cache: dict[str, Any] | None = None

    def build_dashboard(self, *, refresh_all: bool = False) -> dict[str, Any]:
        instruments: dict[str, dict[str, Any]] = {}
        for sym in (*INDEX_SYMBOLS, "VIX"):
            instruments[sym] = self._adapters.instrument_snapshot(sym)

        macro_quotes = {
            "TNX": self._adapters.macro_stub("TNX"),
            "US2Y": self._adapters.macro_stub("US2Y"),
            "DXY": self._adapters.macro_stub("DXY"),
        }
        vix_snap = instruments.get("VIX", {})
        vix_level = vix_snap.get("price")

        qqq = instruments.get("QQQ", {})
        qqq_daily = qqq.get("daily_indicators") or {}
        qqq_intraday = qqq.get("intraday_indicators") or {}

        breadth = self._breadth.compute(instruments)
        vol_panel = self._volatility.compute(qqq_daily=qqq_daily, vix_level=vix_level)
        macro_panel = self._macro.compute(macro_quotes)
        catalyst_list = self._catalysts.upcoming()
        news_score = self._catalysts.news_catalyst_score(catalyst_list)

        scores = self._calculator.compute_scores(
            qqq_daily=qqq_daily,
            qqq_intraday=qqq_intraday,
            breadth_score=breadth["breadth_score"],
            volatility_score=vol_panel["volatility_score"],
            macro_score=macro_panel["macro_score"],
            news_catalyst_score=news_score,
            vix_level=vix_level,
        )

        regime_name = scores["regime_name"]
        preferred = self._strategy.preferred_strategy(regime_name)

        instrument_cards = []
        for sym in ("QQQ", "SPY", "IWM", "DIA", "VIX", "TNX", "DXY", "SMH", "SOXX"):
            snap = instruments.get(sym, {})
            if sym == "TNX":
                instrument_cards.append({
                    "symbol": "10Y Treasury Yield",
                    "price": macro_panel.get("ten_year_yield"),
                    "daily_pct": None,
                    "trend_badge": "Unavailable",
                    "risk_badge": "Macro",
                    "available": macro_panel.get("available", False),
                })
                continue
            if sym == "DXY" and sym not in instruments:
                instrument_cards.append({
                    "symbol": "DXY",
                    "price": macro_panel.get("dxy"),
                    "daily_pct": None,
                    "trend_badge": "Unavailable",
                    "risk_badge": "Macro",
                    "available": False,
                })
                continue
            instrument_cards.append({
                "symbol": sym,
                "price": snap.get("price"),
                "daily_pct": snap.get("daily_pct"),
                "trend_badge": snap.get("trend_badge", "Unavailable"),
                "risk_badge": snap.get("risk_badge", "Unknown"),
                "available": snap.get("available", False),
            })

        ai = self._calculator.ai_summary(
            regime_name=regime_name,
            regime_score=scores["regime_score"],
            preferred_strategy=preferred,
            scores=scores,
            breadth=breadth,
            volatility=vol_panel,
            catalysts=catalyst_list,
        )

        now = datetime.now(UTC)
        dashboard: dict[str, Any] = {
            "timestamp": now.isoformat(),
            "data_source": {
                "ibkr": self._adapters.broker_status(),
                "analyzer": self._adapters.analyzer_status(),
                "macro": macro_panel.get("source", "unavailable"),
            },
            "summary": {
                "regime_name": regime_name,
                "regime_score": scores["regime_score"],
                "confidence": scores["confidence"],
                "risk_level": scores["risk_level"],
                "preferred_strategy": preferred,
            },
            "instruments": instrument_cards,
            "score_breakdown": {
                **scores,
                "final_score": scores["regime_score"],
            },
            "multi_timeframe": self._calculator.multi_timeframe(instruments),
            "breadth": breadth,
            "volatility": vol_panel,
            "macro": macro_panel,
            "strategy_matrix": self._strategy.full_matrix(),
            "strategy_matrix_highlight": self._strategy.build(regime_name),
            "catalysts": catalyst_list,
            "ai_summary": ai,
            "market_regime": {
                "regime_score": scores["regime_score"],
                "regime_name": regime_name,
                "confidence": scores["confidence"],
                "preferred_strategy": preferred,
                "risk_level": scores["risk_level"],
            },
        }
        self._cache = dashboard
        return dashboard

    def get_cached_or_build(self) -> dict[str, Any]:
        if self._cache:
            return self._cache
        return self.build_dashboard()

    def save_snapshot(self, dashboard: dict[str, Any] | None = None) -> dict[str, Any]:
        data = dashboard or self.get_cached_or_build()
        now = datetime.now(UTC)
        snap_date = now.date().isoformat()
        summary = data.get("summary", {})
        scores = data.get("score_breakdown", {})
        prices = {c["symbol"]: c.get("price") for c in data.get("instruments", [])}

        row = {
            "timestamp": now,
            "snapshot_date": snap_date,
            "symbol": "MARKET",
            "regime_name": summary.get("regime_name", "Sideways Range"),
            "regime_score": summary.get("regime_score", 0),
            "confidence": summary.get("confidence", "Low"),
            "risk_level": summary.get("risk_level", "Medium"),
            "preferred_strategy": summary.get("preferred_strategy", "Wait"),
            "trend_score": scores.get("trend_score", 0),
            "momentum_score": scores.get("momentum_score", 0),
            "volatility_score": scores.get("volatility_score", 0),
            "breadth_score": scores.get("breadth_score", 0),
            "macro_score": scores.get("macro_score", 0),
            "news_catalyst_score": scores.get("news_catalyst_score", 0),
            "qqq_price": prices.get("QQQ"),
            "spy_price": prices.get("SPY"),
            "iwm_price": prices.get("IWM"),
            "dia_price": prices.get("DIA"),
            "vix_level": prices.get("VIX"),
            "ten_year_yield": data.get("macro", {}).get("ten_year_yield"),
            "dxy_value": data.get("macro", {}).get("dxy"),
            "summary_json": data,
        }
        saved = self._history.upsert_daily_snapshot(row)
        return {"saved": True, "snapshot_date": snap_date, "id": saved.get("id")}

    def history(self, days: int = 30) -> list[dict[str, Any]]:
        rows = self._history.list_history(days=days)
        return [
            {
                "timestamp": r["timestamp"].isoformat() if hasattr(r["timestamp"], "isoformat") else r["timestamp"],
                "regime_score": r["regime_score"],
                "confidence": r["confidence"],
                "risk_level": r["risk_level"],
                "regime_name": r["regime_name"],
            }
            for r in rows
        ]

    def export_json(self, dashboard: dict[str, Any] | None = None) -> str:
        return json.dumps(dashboard or self.get_cached_or_build(), indent=2, default=str)
