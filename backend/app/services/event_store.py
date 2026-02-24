from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, desc, select
from sqlalchemy.engine import Engine

from app.db import event_log
from app.models import (
    ActiveUniverseResponse,
    BlotterRow,
    ExplainFeedItem,
    EventSummary,
    PositionRow,
    PositionsResponse,
    Recommendation,
    ReconcileMismatch,
    RiskStatus,
    StrategyHealthRow,
    TradeCardResponse,
    TradeReviewItem,
    UniverseVersionRow,
    WatchlistOpportunity,
)


def append_event(
    *,
    engine: Engine,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    producer: str,
    payload: dict,
    schema_ref: str | None = None,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> str:
    now = datetime.now(UTC)
    event_id = str(uuid4())
    if not correlation_id:
        correlation_id = str(uuid4())
    if not causation_id:
        causation_id = correlation_id
    record = {
        "event_id": event_id,
        "event_type": event_type,
        "event_version": 1,
        "occurred_at": now,
        "recorded_at": now,
        "producer": producer,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "idempotency_key": idempotency_key,
        "schema_ref": schema_ref,
        "payload": payload,
    }
    with engine.begin() as conn:
        conn.execute(event_log.insert().values(**record))
    return event_id


def get_event_by_aggregate(
    engine: Engine, event_type: str, aggregate_id: str
) -> dict[str, Any] | None:
    stmt = (
        select(event_log)
        .where(event_log.c.event_type == event_type)
        .where(event_log.c.aggregate_id == aggregate_id)
        .order_by(desc(event_log.c.seq_id))
        .limit(1)
    )
    with engine.begin() as conn:
        row = conn.execute(stmt).mappings().first()
    return dict(row) if row else None


def _latest_event_select(event_type: str) -> Select:
    return (
        select(event_log)
        .where(event_log.c.event_type == event_type)
        .order_by(desc(event_log.c.seq_id))
    )


def _latest_events_by_type(engine: Engine, event_type: str, limit: int = 500) -> list[dict[str, Any]]:
    stmt = _latest_event_select(event_type).limit(limit)
    with engine.begin() as conn:
        return [dict(row) for row in conn.execute(stmt).mappings()]


def list_recent_events(engine: Engine, limit: int = 100) -> list[EventSummary]:
    stmt = select(event_log).order_by(desc(event_log.c.seq_id)).limit(limit)
    out: list[EventSummary] = []
    with engine.begin() as conn:
        for row in conn.execute(stmt).mappings():
            payload = row["payload"] or {}
            out.append(
                EventSummary(
                    event_id=row["event_id"],
                    event_type=row["event_type"],
                    occurred_at=row["occurred_at"],
                    aggregate_type=row["aggregate_type"],
                    aggregate_id=row["aggregate_id"],
                    details=payload,
                )
            )
    return out


def get_latest_event_payload(engine: Engine, event_type: str) -> dict[str, Any] | None:
    stmt = _latest_event_select(event_type).limit(1)
    with engine.begin() as conn:
        row = conn.execute(stmt).mappings().first()
    if not row:
        return None
    payload = row["payload"] or {}
    return payload if isinstance(payload, dict) else None


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _format_float(value: Any, digits: int = 2) -> str:
    return f"{_safe_float(value):.{digits}f}"


def _normalize_explain_ticker(payload: dict[str, Any]) -> str | None:
    ticker = str(payload.get("ticker", "")).strip().upper()
    return ticker or None


def _event_to_explain_item(row: dict[str, Any]) -> ExplainFeedItem | None:
    payload = row.get("payload") or {}
    if not isinstance(payload, dict):
        return None

    event_type = str(row.get("event_type", ""))
    occurred_at = row.get("occurred_at")
    ts = occurred_at if isinstance(occurred_at, datetime) else datetime.now(UTC)
    ticker = _normalize_explain_ticker(payload)
    refs: dict[str, Any] = {
        "aggregate_id": row.get("aggregate_id"),
        "snapshot_refs": payload.get("snapshot_refs", {}),
        "rule_codes": payload.get("overrideable_rule_codes", []),
        "determinism_key": payload.get("determinism_key"),
    }

    category = "system"
    severity = "info"
    step = f"{event_type} recorded"

    if event_type == "UniverseUploaded":
        category = "data"
        status = str(payload.get("upload_status", "unknown")).upper()
        total = len(payload.get("tickers_requested", [])) if isinstance(payload.get("tickers_requested"), list) else 0
        step = f"Universe upload processed: {total} tickers, status {status}"
        if status != "VALIDATED":
            severity = "warn"
    elif event_type == "UniverseActivated":
        category = "system"
        step = f"Active universe switched to {payload.get('universe_version_id', 'unknown')}"
    elif event_type == "CandidateSignal":
        category = "signal"
        conf = _format_float(payload.get("confidence_total"), 1)
        regime = str(payload.get("regime_label", "unknown"))
        edge = _format_float(payload.get("expected_edge_after_cost_usd"))
        step = f"Signal detected ({regime}), confidence {conf}/100, post-cost edge ${edge}"
        if _safe_float(payload.get("expected_edge_after_cost_usd")) <= 0:
            severity = "warn"
    elif event_type == "DataHealthEvaluated":
        category = "data"
        decision_obj = payload.get("decision") or {}
        execution = str(decision_obj.get("execution", "ALLOW")).upper() if isinstance(decision_obj, dict) else "ALLOW"
        step = f"Data health evaluated: execution decision {execution}"
        if execution in {"DEGRADE", "WARN"}:
            severity = "warn"
        if execution == "BLOCK":
            severity = "block"
    elif event_type == "StrategyStructureProposed":
        category = "structure"
        label = str(payload.get("strategy_label", "strategy"))
        debit = _format_float(payload.get("net_debit"))
        breakeven = _format_float(payload.get("breakeven_price"))
        step = f"Proposed {label} with debit ${debit} and breakeven {breakeven}"
    elif event_type == "RiskDecision":
        category = "risk"
        status = str(payload.get("status", payload.get("decision", "unknown"))).upper()
        edge = _format_float(payload.get("expected_edge_after_cost_usd"))
        step = f"Risk status {status}, post-cost edge ${edge}"
        if status == "OVERRIDE_REQUIRED":
            severity = "warn"
        elif status == "REJECTED":
            severity = "block"
    elif event_type == "ApprovalRequestCreated":
        category = "approval"
        step = "Awaiting human approval"
    elif event_type == "ApprovalDecision":
        category = "approval"
        decision = str(payload.get("decision", "unknown")).upper()
        step = f"Approval decision: {decision}"
        if decision == "REJECTED":
            severity = "block"
        elif decision == "OVERRIDE":
            severity = "warn"
    elif event_type == "OrderIntentCreated":
        category = "execution"
        route = str(payload.get("broker_route", "IBKR"))
        step = f"Order intent created for broker route {route}"
    elif event_type == "BrokerOrderEvent":
        category = "execution"
        status = str(payload.get("status", "unknown")).upper()
        step = f"Broker order status: {status}"
        if status in {"REJECTED", "EXPIRED"}:
            severity = "block"
    elif event_type == "FillEvent":
        category = "execution"
        qty = _format_float(payload.get("qty"))
        price = _format_float(payload.get("price"))
        step = f"Fill received: qty {qty} @ ${price}"
    elif event_type == "MismatchDetected":
        category = "reconcile"
        reason = str(payload.get("reason", "reconcile mismatch"))
        blocking = bool(payload.get("blocking", True))
        step = f"Reconcile mismatch detected: {reason}"
        severity = "block" if blocking else "warn"
    elif event_type == "ReconcileSnapshot":
        category = "reconcile"
        mismatch_count = int(_safe_float(payload.get("mismatch_count"), 0))
        blocking = bool(payload.get("blocking", False))
        step = f"Reconcile snapshot captured with {mismatch_count} mismatch(es)"
        if blocking:
            severity = "warn"
    elif event_type == "TradingHaltEvent":
        category = "risk"
        severity = "block"
        reason = str(payload.get("reason_code", "HALT"))
        step = f"Trading halt active: {reason}"

    return ExplainFeedItem(
        event_id=str(row.get("event_id", "")),
        correlation_id=str(row.get("correlation_id")) if row.get("correlation_id") else None,
        ts=ts,
        ticker=ticker,
        severity=severity,  # type: ignore[arg-type]
        category=category,  # type: ignore[arg-type]
        step=step,
        refs=refs,
    )


def explain_feed_view(
    engine: Engine,
    *,
    ticker: str | None = None,
    limit: int = 50,
    correlation_id: str | None = None,
    minutes: int | None = None,
) -> list[ExplainFeedItem]:
    stmt = select(event_log).order_by(desc(event_log.c.seq_id)).limit(max(1, min(500, limit * 8)))
    target_ticker = ticker.strip().upper() if ticker else None
    min_ts = datetime.now(UTC) - timedelta(minutes=minutes) if minutes and minutes > 0 else None
    out: list[ExplainFeedItem] = []

    with engine.begin() as conn:
        for row in conn.execute(stmt).mappings():
            mapped = dict(row)
            if correlation_id and str(mapped.get("correlation_id", "")) != correlation_id:
                continue
            item = _event_to_explain_item(mapped)
            if not item:
                continue
            if target_ticker and item.ticker != target_ticker:
                continue
            if min_ts and item.ts < min_ts:
                continue
            out.append(item)
            if len(out) >= limit:
                break
    return out


def list_recommendations_view(engine: Engine) -> list[Recommendation]:
    stmt = _latest_event_select("CandidateSignal")
    out: list[Recommendation] = []
    seen_signals: set[str] = set()
    with engine.begin() as conn:
        for row in conn.execute(stmt).mappings():
            payload = row["payload"] or {}
            signal_id = payload.get("signal_id")
            if not signal_id or signal_id in seen_signals:
                continue
            seen_signals.add(signal_id)
            try:
                out.append(
                    Recommendation(
                        signal_id=payload["signal_id"],
                        ticker=payload["ticker"],
                        strategy_sleeve=payload["strategy_sleeve"],
                        side=payload["side"],
                        trading_mode=payload.get("trading_mode", "paper"),
                        confidence_total=float(payload["confidence_total"]),
                        regime_label=payload.get("regime_label", "unknown"),
                        thesis=payload.get("thesis", ""),
                        entry_zone=payload.get("entry_zone", "n/a"),
                        invalidation=payload.get("invalidation", "n/a"),
                        targets=list(payload.get("targets", [])),
                        data_sources_used=list(payload.get("data_sources_used", [])),
                        quote_type=payload.get("quote_type", "snapshot"),
                        expected_edge_after_cost_usd=float(payload.get("expected_edge_after_cost_usd", 0.0)),
                    )
                )
            except KeyError:
                continue
    return out


def active_universe_view(engine: Engine) -> ActiveUniverseResponse | None:
    activation = get_latest_event_payload(engine, "UniverseActivated")
    if not activation:
        return None

    version_id = str(activation.get("universe_version_id", ""))
    uploaded_row = get_event_by_aggregate(engine, "UniverseUploaded", version_id)
    upload_payload: dict[str, Any] = {}
    if uploaded_row:
        maybe_payload = uploaded_row.get("payload")
        if isinstance(maybe_payload, dict):
            upload_payload = maybe_payload

    tickers = [str(t).upper() for t in upload_payload.get("tickers_requested", []) if str(t).strip()]
    as_of = upload_payload.get("as_of")
    activated_at_raw = activation.get("activated_at")
    if isinstance(activated_at_raw, str):
        activated_at = datetime.fromisoformat(activated_at_raw.replace("Z", "+00:00"))
    elif isinstance(activated_at_raw, datetime):
        activated_at = activated_at_raw
    else:
        activated_at = datetime.now(UTC)
    return ActiveUniverseResponse(
        universe_version_id=version_id,
        universe_id=str(activation.get("universe_id", "unknown")),
        as_of=str(as_of) if as_of else None,
        activated_at=activated_at,
        tickers=tickers,
    )


def universe_versions_view(engine: Engine, limit: int = 50) -> list[UniverseVersionRow]:
    rows = _latest_events_by_type(engine, "UniverseUploaded", limit=limit)
    out: list[UniverseVersionRow] = []
    for row in rows:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        out.append(
            UniverseVersionRow(
                universe_version_id=str(payload.get("universe_version_id", row.get("aggregate_id", "unknown"))),
                universe_id=str(payload.get("universe_id", "unknown")),
                as_of=str(payload.get("as_of", "")),
                upload_status=str(payload.get("upload_status", "failed")),  # type: ignore[arg-type]
                tickers_requested=[str(t) for t in payload.get("tickers_requested", [])],
                uploaded_at=row.get("occurred_at") if isinstance(row.get("occurred_at"), datetime) else datetime.now(UTC),
            )
        )
    return out


def _latest_signal_by_ticker(engine: Engine) -> dict[str, dict[str, Any]]:
    stmt = _latest_event_select("CandidateSignal")
    out: dict[str, dict[str, Any]] = {}
    with engine.begin() as conn:
        for row in conn.execute(stmt).mappings():
            payload = row["payload"] or {}
            if not isinstance(payload, dict):
                continue
            ticker = str(payload.get("ticker", "")).upper()
            if ticker and ticker not in out:
                out[ticker] = payload
    return out


def _latest_data_health_by_ticker(engine: Engine) -> dict[str, tuple[str, str, datetime | None]]:
    rows = _latest_events_by_type(engine, "DataHealthEvaluated", limit=1000)
    out: dict[str, tuple[str, str, datetime | None]] = {}
    for row in rows:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        ticker = str(payload.get("ticker", "")).upper()
        if not ticker or ticker in out:
            continue
        decision = str(payload.get("decision", {}).get("execution", "ALLOW")).upper()
        if decision == "BLOCK":
            health = "Blocked"
        elif decision in {"DEGRADE", "WARN"}:
            health = "Degraded"
        else:
            health = "OK"
        reason = str(payload.get("reason", payload.get("summary", "data health OK")))
        ts = row.get("occurred_at")
        out[ticker] = (health, reason, ts if isinstance(ts, datetime) else None)
    return out


def _latest_risk_by_signal(engine: Engine) -> dict[str, dict[str, Any]]:
    rows = _latest_events_by_type(engine, "RiskDecision", limit=1000)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        signal_id = str(payload.get("signal_id", ""))
        if signal_id and signal_id not in out:
            out[signal_id] = payload
    return out


def _latest_approval_by_signal(engine: Engine) -> dict[str, dict[str, Any]]:
    rows = _latest_events_by_type(engine, "ApprovalDecision", limit=1000)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        signal_id = str(payload.get("signal_id", ""))
        if signal_id and signal_id not in out:
            out[signal_id] = payload
    return out


def _latest_approval_request_by_signal(engine: Engine) -> dict[str, dict[str, Any]]:
    rows = _latest_events_by_type(engine, "ApprovalRequestCreated", limit=1000)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        signal_id = str(payload.get("signal_id", ""))
        if signal_id and signal_id not in out:
            out[signal_id] = payload
    return out


def _latest_order_by_signal(engine: Engine) -> dict[str, dict[str, Any]]:
    rows = _latest_events_by_type(engine, "OrderIntentCreated", limit=1000)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        signal_id = str(payload.get("signal_id", ""))
        if signal_id and signal_id not in out:
            out[signal_id] = payload
    return out


def _latest_structure_by_signal(engine: Engine) -> dict[str, dict[str, Any]]:
    rows = _latest_events_by_type(engine, "StrategyStructureProposed", limit=1000)
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        signal_id = str(payload.get("signal_id", ""))
        if signal_id and signal_id not in out:
            out[signal_id] = payload
    return out


def watchlist_view(engine: Engine) -> list[WatchlistOpportunity]:
    active = active_universe_view(engine)
    tickers = active.tickers if active else []
    signal_by_ticker = _latest_signal_by_ticker(engine)
    health_by_ticker = _latest_data_health_by_ticker(engine)
    risk_by_signal = _latest_risk_by_signal(engine)
    approval_request_by_signal = _latest_approval_request_by_signal(engine)
    approval_by_signal = _latest_approval_by_signal(engine)
    structure_by_signal = _latest_structure_by_signal(engine)
    order_by_signal = _latest_order_by_signal(engine)
    out: list[WatchlistOpportunity] = []

    for ticker in tickers:
        signal = signal_by_ticker.get(ticker)
        state = "NoSignal"
        entry_zone = "n/a"
        invalidation = "n/a"
        target = "n/a"
        hold_period = "n/a"
        regime = "unknown"
        confidence_total = 0.0
        confidence_components: dict[str, float] = {}
        post_cost_edge_usd = 0.0
        post_cost_edge_pct = 0.0
        earnings_warning = False
        next_action = "view_trade_card"
        signal_id = None

        if signal:
            state = "CandidateSignal"
            signal_id = str(signal.get("signal_id", ""))
            entry_zone = str(signal.get("entry_zone", "n/a"))
            invalidation = str(signal.get("invalidation", "n/a"))
            targets = signal.get("targets") or []
            target = str(targets[0]) if isinstance(targets, list) and targets else "n/a"
            hold_period = f"{signal.get('expected_hold_days', 28)}d"
            regime = str(signal.get("regime_label", "unknown"))
            confidence_total = float(signal.get("confidence_total", 0.0))
            confidence_components = signal.get("confidence_components") or {}
            if not confidence_components:
                confidence_components = {
                    "setup_quality": max(0.0, confidence_total - 15.0),
                    "regime_fit": max(0.0, confidence_total - 10.0),
                    "liquidity": max(0.0, confidence_total - 12.0),
                    "event_risk": max(0.0, confidence_total - 20.0),
                    "data_quality_multiplier": 1.0,
                    "cost_adjustment": -2.0,
                }
            post_cost_edge_usd = float(signal.get("expected_edge_after_cost_usd", 0.0))
            post_cost_edge_pct = round((post_cost_edge_usd / 1000.0) * 100.0, 2)
            earnings_warning = any(
                "earnings" in str(item).lower()
                for item in signal.get("penalties", [])
            )

        if signal_id:
            risk = risk_by_signal.get(signal_id)
            approval_request = approval_request_by_signal.get(signal_id)
            approval = approval_by_signal.get(signal_id)
            structure = structure_by_signal.get(signal_id)
            order = order_by_signal.get(signal_id)
            if structure:
                state = "StructureProposed"
                next_action = "run_risk"
            if risk and risk.get("status", risk.get("decision")) == "approved":
                state = "RiskApproved"
                next_action = "request_approval"
            if approval_request and not approval:
                state = "AwaitingApproval"
                next_action = "request_approval"
            if approval:
                decision = str(approval.get("decision", ""))
                if decision == "approved":
                    state = "OrderIntent"
                    next_action = "manage_position"
                elif decision == "override":
                    state = "OrderIntent"
                    next_action = "manage_position"
                elif decision == "rejected":
                    state = "RiskApproved"
                    next_action = "build_structure"
            if order:
                state = "OrderIntent"
                next_action = "manage_position"

        health, health_reason, last_snapshot_ts = health_by_ticker.get(
            ticker, ("OK", "No health event yet", None)
        )
        if health == "Blocked":
            next_action = "blocked"

        out.append(
            WatchlistOpportunity(
                ticker=ticker,
                state=state,  # type: ignore[arg-type]
                data_health=health,  # type: ignore[arg-type]
                data_health_reason=health_reason,
                regime_label=regime,
                confidence_total=confidence_total,
                confidence_components=confidence_components,
                post_cost_edge_usd=post_cost_edge_usd,
                post_cost_edge_pct_of_debit=post_cost_edge_pct,
                entry_zone=entry_zone,
                invalidation=invalidation,
                target=target,
                hold_period=hold_period,
                earnings_warning=earnings_warning,
                earnings_date=None,
                earnings_certainty="unknown",
                last_snapshot_ts=last_snapshot_ts,
                next_action=next_action,  # type: ignore[arg-type]
            )
        )

    return out


def trade_card_view(engine: Engine, ticker: str) -> TradeCardResponse:
    watchlist = watchlist_view(engine)
    item = next((row for row in watchlist if row.ticker.upper() == ticker.upper()), None)
    if not item:
        return TradeCardResponse(ticker=ticker.upper(), state="NoSignal")

    recent_rows: list[dict[str, Any]] = []
    stmt = select(event_log).order_by(desc(event_log.c.seq_id)).limit(500)
    with engine.begin() as conn:
        for row in conn.execute(stmt).mappings():
            payload = row["payload"] or {}
            if not isinstance(payload, dict):
                continue
            if str(payload.get("ticker", "")).upper() == ticker.upper():
                recent_rows.append(dict(row))
            if len(recent_rows) >= 25:
                break
    recent_events = [
        EventSummary(
            event_id=str(row["event_id"]),
            event_type=str(row["event_type"]),
            occurred_at=row["occurred_at"],
            aggregate_type=str(row["aggregate_type"]),
            aggregate_id=str(row["aggregate_id"]),
            details=row["payload"] or {},
        )
        for row in recent_rows
    ]

    warnings = []
    if item.data_health != "OK":
        warnings.append(f"data_health:{item.data_health}")
    if item.earnings_warning:
        warnings.append("earnings_danger")
    if item.post_cost_edge_usd <= 0:
        warnings.append("negative_edge_after_costs")

    signal_id = next(
        (
            str((row.details or {}).get("signal_id", ""))
            for row in recent_events
            if row.event_type == "CandidateSignal"
        ),
        "",
    )
    structure_map = _latest_structure_by_signal(engine)
    risk_map = _latest_risk_by_signal(engine)
    approval_map = _latest_approval_by_signal(engine)
    structure_summary = structure_map.get(signal_id)
    risk_raw = risk_map.get(signal_id)
    approval_raw = approval_map.get(signal_id)
    risk_summary = None
    if risk_raw:
        risk_summary = {
            "status": risk_raw.get("status", risk_raw.get("decision")),
            "expected_total_cost_usd": risk_raw.get("expected_total_cost_usd"),
            "expected_edge_after_cost_usd": risk_raw.get("expected_edge_after_cost_usd"),
            "worst_case_stress_loss_usd": risk_raw.get("worst_case_stress_loss_usd"),
            "rule_reasons": risk_raw.get("rule_reasons", risk_raw.get("reasons", [])),
        }
    approval_status = None
    if approval_raw:
        approval_status = {
            "decision": approval_raw.get("decision"),
            "override": approval_raw.get("override", False),
            "override_reason": approval_raw.get("override_reason"),
            "notes": approval_raw.get("notes", ""),
        }

    thesis = {
        "setup_name": "bull_call_spread",
        "entry_zone": item.entry_zone,
        "invalidation": item.invalidation,
        "target": item.target,
        "hold_period": item.hold_period,
    }
    why_now = [
        f"Regime: {item.regime_label}",
        f"Confidence: {item.confidence_total:.1f}",
        f"Post-cost edge: {item.post_cost_edge_usd:.2f} USD",
    ]
    return TradeCardResponse(
        ticker=item.ticker,
        state=item.state,
        last_price=None,
        snapshot_timestamps={},
        thesis=thesis,
        why_now_deltas=why_now,
        confidence_total=item.confidence_total,
        confidence_components=item.confidence_components,
        warnings=warnings,
        structure_summary=structure_summary,
        risk_summary=risk_summary,
        approval_status=approval_status,
        position_summary=None,
        recent_events=recent_events[:10],
    )


def risk_status_view(engine: Engine) -> RiskStatus:
    stmt = _latest_event_select("RiskDecision").limit(1)
    drawdown_pct = 0.0
    stress_nav_pct = 0.0
    trading_mode = "paper"
    can_open = True
    with engine.begin() as conn:
        row = conn.execute(stmt).mappings().first()
        if row:
            payload = row["payload"] or {}
            drawdown_pct = float(payload.get("drawdown_pct", 0.0))
            stress_nav_pct = float(payload.get("worst_case_stress_loss_nav_pct", 0.0))
            trading_mode = payload.get("trading_mode", "paper")
            can_open = payload.get("status", payload.get("decision", "approved")) == "approved"

        halt_stmt = _latest_event_select("TradingHaltEvent").limit(25)
        active_halts: list[str] = []
        for h in conn.execute(halt_stmt).mappings():
            payload = h["payload"] or {}
            if payload.get("end_time") in (None, "", "null"):
                active_halts.append(payload.get("reason_code", "halt"))
        if active_halts:
            can_open = False

    return RiskStatus(
        trading_mode=trading_mode,  # type: ignore[arg-type]
        drawdown_pct=drawdown_pct,
        worst_case_stress_loss_nav_pct=stress_nav_pct,
        can_open_new_entries=can_open,
        active_halts=active_halts,
    )


def _latest_candidate_by_signal(engine: Engine) -> dict[str, dict]:
    stmt = _latest_event_select("CandidateSignal")
    out: dict[str, dict] = {}
    with engine.begin() as conn:
        for row in conn.execute(stmt).mappings():
            payload = row["payload"] or {}
            signal_id = payload.get("signal_id")
            if signal_id and signal_id not in out:
                out[signal_id] = payload
    return out


def positions_view(engine: Engine) -> PositionsResponse:
    opened = _latest_events_by_type(engine, "PositionOpened", limit=500)
    closed = _latest_events_by_type(engine, "PositionClosed", limit=500)
    closed_signal_ids = {
        str((row.get("payload") or {}).get("signal_id", ""))
        for row in closed
    }
    rows: list[PositionRow] = []
    health_by_ticker = _latest_data_health_by_ticker(engine)
    reconcile_rows = reconcile_mismatches_view(engine)
    blocking_reconcile = any(item.blocking for item in reconcile_rows)
    for row in opened:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        signal_id = str(payload.get("signal_id", ""))
        if signal_id and signal_id in closed_signal_ids:
            continue
        ticker = str(payload.get("ticker", "UNKNOWN")).upper()
        alerts: list[str] = []
        _health, health_reason, _ts = health_by_ticker.get(ticker, ("OK", "", None))
        if _health != "OK":
            alerts.append("data_degraded")
        if blocking_reconcile:
            alerts.append("reconcile_block")
        if payload.get("dte") is not None and int(payload.get("dte", 999)) <= 7:
            alerts.append("dte_threshold")
        invalidation = payload.get("invalidation_level")
        last_price = payload.get("last_price")
        if invalidation is not None and last_price is not None and float(last_price) <= float(invalidation):
            alerts.append("invalidation_breached")
        if health_reason and _health != "OK":
            alerts.append("exit_rule_triggered")
        qty = float(payload.get("qty_opened", payload.get("qty", 0.0)))
        rows.append(
            PositionRow(
                ticker=ticker,
                strategy_label=payload.get("strategy_label"),
                qty=qty,
                avg_price=float(payload.get("avg_entry_price", 0.0)) if payload.get("avg_entry_price") else None,
                last_price=float(last_price) if last_price is not None else None,
                pnl_daily=0.0,
                pnl_total=float(payload.get("unrealized_pnl_usd", 0.0)),
                dte=payload.get("dte"),
                breakeven=payload.get("breakeven"),
                alerts=alerts,
            )
        )
    return PositionsResponse(account_id="unknown", positions=rows)


def blotter_view(engine: Engine) -> list[BlotterRow]:
    intents = _latest_events_by_type(engine, "OrderIntentCreated", limit=500)
    broker_events = _latest_events_by_type(engine, "BrokerOrderEvent", limit=1000)
    fills = _latest_events_by_type(engine, "FillEvent", limit=1000)
    broker_by_intent: dict[str, list[dict[str, Any]]] = {}
    fills_by_intent: dict[str, list[dict[str, Any]]] = {}
    for row in broker_events:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        intent_id = str(payload.get("order_intent_id", ""))
        if intent_id:
            broker_by_intent.setdefault(intent_id, []).append(payload)
    for row in fills:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        intent_id = str(payload.get("order_intent_id", ""))
        if intent_id:
            fills_by_intent.setdefault(intent_id, []).append(payload)

    out: list[BlotterRow] = []
    for row in intents:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        intent_id = str(payload.get("order_intent_id", ""))
        broker_rows = broker_by_intent.get(intent_id, [])
        fill_rows = fills_by_intent.get(intent_id, [])
        statuses = [str(x.get("status", "")) for x in broker_rows if x.get("status")]
        broker_order_ids = list({str(x.get("broker_order_id")) for x in broker_rows if x.get("broker_order_id")})
        out.append(
            BlotterRow(
                order_intent_id=intent_id,
                ticker=str(payload.get("ticker", "UNKNOWN")).upper(),
                structure_label=payload.get("structure_label"),
                legs_summary=[str(leg) for leg in payload.get("legs_summary", [])] if isinstance(payload.get("legs_summary"), list) else [],
                created_ts=row["occurred_at"],
                submitted_ts=row["occurred_at"] if broker_rows else None,
                last_update_ts=broker_rows[0].get("event_time", row["occurred_at"]) if broker_rows else row["occurred_at"],
                broker_order_ids=broker_order_ids,
                status=statuses[0] if statuses else "CREATED",
                status_timeline=statuses or ["CREATED"],
                fills=fill_rows,
                fees_usd=float(payload.get("fees_usd", 0.0)),
                slippage_vs_expected_usd=float(payload.get("slippage_vs_expected_usd", 0.0)),
                broker_reject_reason=next(
                    (str(x.get("reason")) for x in broker_rows if str(x.get("status", "")).upper() == "REJECTED"),
                    None,
                ),
            )
        )
    return out


def reconcile_mismatches_view(engine: Engine) -> list[ReconcileMismatch]:
    mismatches = _latest_events_by_type(engine, "MismatchDetected", limit=500)
    out: list[ReconcileMismatch] = []
    now = datetime.now(UTC)
    for row in mismatches:
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        occurred = row.get("occurred_at")
        age_seconds = 0
        if isinstance(occurred, datetime):
            age_seconds = max(0, int((now - occurred).total_seconds()))
        out.append(
            ReconcileMismatch(
                mismatch_id=str(payload.get("mismatch_id", row.get("event_id"))),
                ticker=payload.get("ticker"),
                severity=str(payload.get("severity", "medium")),  # type: ignore[arg-type]
                reason=str(payload.get("reason", "reconcile mismatch")),
                blocking=bool(payload.get("blocking", True)),
                mismatch_age_seconds=age_seconds,
                last_broker_truth_ts=payload.get("broker_truth_ts"),
            )
        )
    return out


def strategy_health_view(engine: Engine) -> list[StrategyHealthRow]:
    signal_map = _latest_candidate_by_signal(engine)
    stmt = _latest_event_select("PositionClosed")
    grouped: dict[tuple[str, str, str], list[float]] = {}
    with engine.begin() as conn:
        for row in conn.execute(stmt).mappings():
            payload = row["payload"] or {}
            signal_id = payload.get("signal_id")
            sig = signal_map.get(signal_id or "")
            if not sig:
                continue
            key = (
                sig.get("strategy_sleeve", "unknown"),
                sig.get("regime_label", "unknown"),
                sig.get("trading_mode", "paper"),
            )
            pnl = float(payload.get("realized_pnl_after_costs_usd", 0.0))
            grouped.setdefault(key, []).append(pnl)

    out: list[StrategyHealthRow] = []
    for (sleeve, regime, mode), pnls in grouped.items():
        trades = len(pnls)
        wins = [x for x in pnls if x > 0]
        losses = [x for x in pnls if x < 0]
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        payoff_ratio = abs(avg_win / avg_loss) if avg_loss else (999.0 if avg_win > 0 else 0.0)
        out.append(
            StrategyHealthRow(
                strategy_sleeve=sleeve,
                regime_label=regime,
                trading_mode=mode,  # type: ignore[arg-type]
                trades=trades,
                win_rate=(len(wins) / trades) if trades else 0.0,
                expectancy_after_costs_usd=sum(pnls) / trades if trades else 0.0,
                avg_win_usd=avg_win,
                avg_loss_usd=avg_loss,
                payoff_ratio=payoff_ratio,
            )
        )
    return sorted(out, key=lambda x: x.expectancy_after_costs_usd, reverse=True)


def trade_review_queue_view(engine: Engine, limit: int = 100) -> list[TradeReviewItem]:
    out: list[TradeReviewItem] = []
    with engine.begin() as conn:
        # Human overrides are always review-worthy.
        approval_stmt = _latest_event_select("ApprovalDecision").limit(limit)
        for row in conn.execute(approval_stmt).mappings():
            payload = row["payload"] or {}
            flags = payload.get("override_flags", [])
            if flags:
                out.append(
                    TradeReviewItem(
                        occurred_at=row["occurred_at"],
                        issue_type="override",
                        severity="high",
                        aggregate_id=row["aggregate_id"],
                        message=f"Override flags: {', '.join(flags)}",
                    )
                )

        # Delayed/snapshot quotes should be reviewed.
        signal_stmt = _latest_event_select("CandidateSignal").limit(limit)
        for row in conn.execute(signal_stmt).mappings():
            payload = row["payload"] or {}
            quote_type = payload.get("quote_type")
            if quote_type in {"delayed", "snapshot"}:
                out.append(
                    TradeReviewItem(
                        occurred_at=row["occurred_at"],
                        issue_type="data_quality",
                        severity="medium",
                        aggregate_id=row["aggregate_id"],
                        message=f"Signal used {quote_type} quotes.",
                    )
                )

        # Approved negative edge is high severity.
        risk_stmt = _latest_event_select("RiskDecision").limit(limit)
        for row in conn.execute(risk_stmt).mappings():
            payload = row["payload"] or {}
            edge = float(payload.get("expected_edge_after_cost_usd", 0.0))
            status = payload.get("status", payload.get("decision"))
            if status == "approved" and edge <= 0:
                out.append(
                    TradeReviewItem(
                        occurred_at=row["occurred_at"],
                        issue_type="negative_edge",
                        severity="high",
                        aggregate_id=row["aggregate_id"],
                        message=f"Approved with non-positive edge after costs ({edge:.2f}).",
                    )
                )

    out.sort(key=lambda x: x.occurred_at, reverse=True)
    return out[:limit]


