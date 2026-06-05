from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.engine import Engine

from app.engines.paper_trade_engine import simulate_paper_trade
from app.engines.review_engine import infer_review_flags
from app.models import PaperTradeRunOut
from app.services.decision_store import get_decision, link_paper_trade, patch_decision
from app.services.event_store import append_event


def run_paper_for_decision(
    *,
    engine: Engine,
    decision: dict[str, Any],
    scenario_return: float,
    trace_fn,
) -> tuple[PaperTradeRunOut, dict[str, Any]]:
    if decision.get("risk_status") == "reject":
        raise ValueError("Cannot paper trade a rejected decision")
    if decision.get("current_status") == "rejected":
        raise ValueError("Decision was rejected")
    ticker = str(decision["symbol"]).upper()
    direction = str(decision.get("direction", "bullish"))
    candidate = {
        "strategy_type": decision.get("strategy_type"),
        "direction": direction,
        "debit_or_credit": float(decision.get("max_loss") or 1.0),
        "max_profit": float(decision.get("max_profit") or 0.0),
        "max_loss": float(decision.get("max_loss") or 0.0),
        "legs": decision.get("legs") or [],
    }
    signal_id = str(decision.get("signal_id") or f"paper_sig_{decision['decision_id']}")
    simulation = simulate_paper_trade(
        signal_id=signal_id,
        ticker=ticker,
        candidate=candidate,
        scenario_return=scenario_return,
    )
    decision_id = str(decision["decision_id"])
    corr, caus = trace_fn()
    lifecycle = ["OrderIntentCreated", "PaperOrderCreated", "FillEvent", "PositionOpened", "PositionClosed"]

    intent_payload = {
        "order_intent_id": simulation.order_intent_id,
        "signal_id": signal_id,
        "decision_id": decision_id,
        "ticker": ticker,
        "broker_route": "PAPER",
        "execution_config_version": "paper_exec_v1",
        "trading_mode": "paper",
        "structure_label": decision.get("strategy_type"),
        "legs_summary": [str(leg) for leg in decision.get("legs") or []],
        "fees_usd": simulation.fees_usd,
        "slippage_vs_expected_usd": simulation.slippage_usd,
    }
    append_event(
        engine=engine,
        event_type="OrderIntentCreated",
        aggregate_type="order_intent",
        aggregate_id=simulation.order_intent_id,
        producer="paper_trade_engine",
        payload=intent_payload,
        schema_ref="st.events.order_intent_created.v1",
        idempotency_key=f"paper_trade_engine:OrderIntentCreated:{simulation.order_intent_id}",
        correlation_id=corr,
        causation_id=caus,
    )
    for status in ("CREATED", "SENT", "ACK", "FILLED"):
        append_event(
            engine=engine,
            event_type="BrokerOrderEvent",
            aggregate_type="order_intent",
            aggregate_id=simulation.order_intent_id,
            producer="paper_trade_engine",
            payload={
                "broker_event_id": f"paper_{status.lower()}_{simulation.order_intent_id}",
                "order_intent_id": simulation.order_intent_id,
                "decision_id": decision_id,
                "broker_order_id": f"paper_order_{simulation.order_intent_id}",
                "status": status,
                "reason": None,
                "event_time": datetime.now(UTC).isoformat(),
            },
            schema_ref="st.events.broker_order_event.v1",
            idempotency_key=f"paper_trade_engine:BrokerOrderEvent:{simulation.order_intent_id}:{status}",
            correlation_id=corr,
            causation_id=caus,
        )
    append_event(
        engine=engine,
        event_type="FillEvent",
        aggregate_type="order_intent",
        aggregate_id=simulation.order_intent_id,
        producer="paper_trade_engine",
        payload={
            "fill_event_id": f"paper_fill_{simulation.order_intent_id}",
            "order_intent_id": simulation.order_intent_id,
            "decision_id": decision_id,
            "broker_order_id": f"paper_order_{simulation.order_intent_id}",
            "qty": 1,
            "price": simulation.entry_price,
            "commission_usd": simulation.fees_usd,
            "fees_usd": 0.0,
            "occurred_at": simulation.opened_at.isoformat(),
        },
        schema_ref="st.events.fill_event.v1",
        idempotency_key=f"paper_trade_engine:FillEvent:{simulation.order_intent_id}",
        correlation_id=corr,
        causation_id=caus,
    )
    append_event(
        engine=engine,
        event_type="PositionOpened",
        aggregate_type="position",
        aggregate_id=simulation.position_event_id,
        producer="paper_trade_engine",
        payload={
            "position_event_id": simulation.position_event_id,
            "signal_id": signal_id,
            "decision_id": decision_id,
            "ticker": ticker,
            "strategy_label": decision.get("strategy_type"),
            "qty_opened": 1.0,
            "avg_entry_price": simulation.entry_price,
            "open_order_intent_id": simulation.order_intent_id,
            "opened_at": simulation.opened_at.isoformat(),
        },
        schema_ref="st.events.position_opened.v1",
        idempotency_key=f"paper_trade_engine:PositionOpened:{simulation.position_event_id}",
        correlation_id=corr,
        causation_id=caus,
    )
    pnl_pct = round((simulation.realized_pnl_after_costs_usd / max(1.0, abs(simulation.entry_price * 100))) * 100.0, 2)
    max_dd = min(0.0, simulation.realized_pnl_after_costs_usd * 0.35)
    append_event(
        engine=engine,
        event_type="PositionClosed",
        aggregate_type="position",
        aggregate_id=simulation.close_event_id,
        producer="paper_trade_engine",
        payload={
            "position_event_id": simulation.position_event_id,
            "signal_id": signal_id,
            "decision_id": decision_id,
            "ticker": ticker,
            "realized_pnl_after_costs_usd": simulation.realized_pnl_after_costs_usd,
            "closed_at": simulation.closed_at.isoformat(),
        },
        schema_ref="st.events.position_closed.v1",
        idempotency_key=f"paper_trade_engine:PositionClosed:{simulation.close_event_id}",
        correlation_id=corr,
        causation_id=caus,
    )

    extra = dict(decision.get("extra") or {})
    extra.update(
        {
            "entry_price": simulation.entry_price,
            "exit_price": simulation.exit_price,
        }
    )
    flags = infer_review_flags(decision={**decision, "extra": extra}, realized_pnl=simulation.realized_pnl_after_costs_usd, scenario_return=scenario_return)
    extra.update(flags)
    updated = link_paper_trade(
        engine,
        decision_id=decision_id,
        paper_order_id=simulation.order_intent_id,
        paper_position_id=simulation.position_event_id,
        paper_pnl=simulation.realized_pnl_after_costs_usd,
        paper_pnl_percent=pnl_pct,
        max_drawdown=max_dd,
        current_status="position_closed",
        closed_at=simulation.closed_at,
    )
    patch_decision(engine, decision_id, {"extra": extra, "final_outcome": flags["final_outcome"]})

    out = PaperTradeRunOut(
        mode="decision",
        decision_id=decision_id,
        ticker=ticker,
        direction=direction,  # type: ignore[arg-type]
        signal_id=signal_id,
        order_intent_id=simulation.order_intent_id,
        position_event_id=simulation.position_event_id,
        close_event_id=simulation.close_event_id,
        entry_price=simulation.entry_price,
        exit_price=simulation.exit_price,
        realized_pnl_after_costs_usd=simulation.realized_pnl_after_costs_usd,
        realized_pnl_percent=pnl_pct,
        max_drawdown=max_dd,
        fees_usd=simulation.fees_usd,
        slippage_usd=simulation.slippage_usd,
        lifecycle=lifecycle,
        as_of=datetime.now(UTC),
        data_status=decision.get("data_status", "mock"),  # type: ignore[arg-type]
    )
    return out, updated or decision
