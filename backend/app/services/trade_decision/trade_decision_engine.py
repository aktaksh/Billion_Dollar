"""Trade decision engine — persist and evaluate decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.engine import Engine

from app.repositories.decision_repository import DecisionRepository
from app.services.trade_decision.trade_decision_calculator import TradeDecisionCalculator


class TradeDecisionEngine:
    VERSION = "1.0.0"

    def __init__(self, engine: Engine) -> None:
        self._repo = DecisionRepository(engine)
        self._calculator = TradeDecisionCalculator()

    def record(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        row = {
            "timestamp": now,
            "symbol": str(payload.get("symbol", "QQQ")).upper(),
            "decision": payload.get("decision", "WAIT"),
            "trade_score": float(payload.get("trade_score", 0)),
            "confidence": payload.get("confidence", "Medium"),
            "market_regime": payload.get("market_regime"),
            "strategy": payload.get("strategy"),
            "reason": payload.get("reason"),
            "entry_price": payload.get("entry_price"),
            "entry_trigger": payload.get("entry_trigger"),
            "target": payload.get("target"),
            "stop": payload.get("stop"),
            "risk_level": payload.get("risk_level", "Medium"),
            "probability": payload.get("probability"),
            "summary": payload.get("summary"),
            "analysis_timestamp": payload.get("analysis_timestamp"),
            "summary_json": payload.get("summary_json"),
        }
        saved = self._repo.insert(row)
        return {"id": saved["id"], "saved": True}

    def evaluate_from_analysis(
        self,
        analysis: dict[str, Any],
        *,
        regime_label: str = "Sideways",
        regime_scores: dict[str, Any] | None = None,
        strategy_filter: str = "WAIT",
    ) -> dict[str, Any]:
        return self._calculator.evaluate(
            analysis,
            regime_label=regime_label,
            regime_scores=regime_scores or {"final": 0},
            strategy_filter=strategy_filter,
        )

    def list_recent(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._repo.list_recent(symbol, limit=limit)
