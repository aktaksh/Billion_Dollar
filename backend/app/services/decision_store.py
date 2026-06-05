from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.engine import Engine

from app.db import new_decision_id, trade_decisions


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)


def insert_decision(engine: Engine, payload: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC)
    decision_id = payload.get("decision_id") or new_decision_id()
    record = {
        "decision_id": decision_id,
        "created_at": now,
        "updated_at": now,
        **payload,
    }
    if "extra" not in record or record["extra"] is None:
        record["extra"] = {}
    with engine.begin() as conn:
        conn.execute(trade_decisions.insert().values(**record))
    return get_decision(engine, decision_id) or record


def get_decision(engine: Engine, decision_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(trade_decisions).where(trade_decisions.c.decision_id == decision_id)
        ).first()
    return _row_to_dict(row) if row else None


def list_decisions(
    engine: Engine,
    *,
    symbol: str | None = None,
    review_status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    stmt = select(trade_decisions).order_by(desc(trade_decisions.c.created_at)).limit(limit)
    if symbol:
        stmt = stmt.where(trade_decisions.c.symbol == symbol.upper())
    if review_status:
        stmt = stmt.where(trade_decisions.c.review_status == review_status)
    with engine.begin() as conn:
        rows = conn.execute(stmt).all()
    return [_row_to_dict(r) for r in rows]


def patch_decision(engine: Engine, decision_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {c.name for c in trade_decisions.columns} - {"decision_id", "created_at"}
    clean = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not clean:
        return get_decision(engine, decision_id)
    clean["updated_at"] = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(update(trade_decisions).where(trade_decisions.c.decision_id == decision_id).values(**clean))
    return get_decision(engine, decision_id)


def link_paper_trade(
    engine: Engine,
    *,
    decision_id: str,
    paper_order_id: str,
    paper_position_id: str,
    paper_pnl: float,
    paper_pnl_percent: float,
    max_drawdown: float,
    current_status: str = "position_closed",
    closed_at: datetime | None = None,
) -> dict[str, Any] | None:
    return patch_decision(
        engine,
        decision_id,
        {
            "paper_order_id": paper_order_id,
            "paper_position_id": paper_position_id,
            "paper_pnl": paper_pnl,
            "paper_pnl_percent": paper_pnl_percent,
            "max_drawdown": max_drawdown,
            "current_status": current_status,
            "review_status": "ready_for_review",
            "closed_at": closed_at or datetime.now(UTC),
        },
    )


def dashboard_summary(engine: Engine) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    rows = list_decisions(engine, limit=500)
    today_rows = [r for r in rows if r.get("created_at") and _as_date(r["created_at"]) == today]
    paper_closed = [r for r in rows if r.get("paper_pnl") is not None]
    open_positions = [r for r in rows if r.get("current_status") == "position_open"]
    ready_review = [r for r in rows if r.get("review_status") == "ready_for_review"]
    reviewed = [r for r in rows if r.get("review_status") == "reviewed"]
    wins = [r for r in paper_closed if float(r.get("paper_pnl") or 0) > 0]
    win_rate = (len(wins) / len(paper_closed)) if paper_closed else 0.0
    avg_pnl_pct = (
        sum(float(r.get("paper_pnl_percent") or 0) for r in paper_closed) / len(paper_closed) if paper_closed else 0.0
    )
    avg_dd = (
        sum(float(r.get("max_drawdown") or 0) for r in paper_closed) / len(paper_closed) if paper_closed else 0.0
    )
    strategy_pnl: dict[str, list[float]] = {}
    reject_reasons: dict[str, int] = {}
    for r in rows:
        st = str(r.get("strategy_type", "unknown"))
        if r.get("paper_pnl") is not None:
            strategy_pnl.setdefault(st, []).append(float(r["paper_pnl"]))
        if r.get("risk_status") == "reject":
            for reason in r.get("rule_reasons") or []:
                code = str(reason.get("rule_code", reason.get("message", "unknown")))
                reject_reasons[code] = reject_reasons.get(code, 0) + 1
    best_strategy = "n/a"
    worst_strategy = "n/a"
    if strategy_pnl:
        ranked = sorted(strategy_pnl.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True)
        best_strategy = ranked[0][0]
        worst_strategy = ranked[-1][0]
    most_common_reject = "n/a"
    if reject_reasons:
        most_common_reject = max(reject_reasons.items(), key=lambda x: x[1])[0]
    correct = [r for r in reviewed if r.get("final_outcome") == "correct"]
    engine_accuracy = (len(correct) / len(reviewed)) if reviewed else 0.0
    return {
        "total_decisions_today": len(today_rows),
        "paper_trades_opened": len([r for r in rows if r.get("paper_order_id")]),
        "open_paper_positions": len(open_positions),
        "decisions_ready_for_review": len(ready_review),
        "reviewed_decisions": len(reviewed),
        "win_rate": round(win_rate, 4),
        "avg_paper_pnl_percent": round(avg_pnl_pct, 4),
        "avg_max_drawdown": round(avg_dd, 4),
        "best_strategy": best_strategy,
        "worst_strategy": worst_strategy,
        "most_common_reject_reason": most_common_reject,
        "engine_accuracy": round(engine_accuracy, 4),
    }


def _as_date(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).date()
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).date()
    return today_fallback()


def today_fallback():
    return datetime.now(UTC).date()


def decision_by_paper_order(engine: Engine, paper_order_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(trade_decisions).where(trade_decisions.c.paper_order_id == paper_order_id)
        ).first()
    return _row_to_dict(row) if row else None
