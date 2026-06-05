from datetime import UTC, datetime
import hashlib
import json
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.db import event_log, get_engine, init_db
from app.models import (
    ActiveUniverseResponse,
    ApprovalRequestIn,
    ApprovalDecisionIn,
    BrokerOrderEventIn,
    BrokerRequestResponseRecordedIn,
    CandidateSignalBulkIn,
    CandidateSignalBulkOut,
    CandidateSignalIn,
    EventSummary,
    EventWriteResponse,
    GenerateSignalsFromIbkrIn,
    GenerateSignalsFromIbkrOut,
    GeneratedSignalSummary,
    HealthResponse,
    DataHealthEvaluatedIn,
    ExplainFeedItem,
    MismatchDetectedIn,
    PositionRow,
    PositionsResponse,
    PositionOpenedIn,
    PositionClosedIn,
    OrderIntentCreatedIn,
    ReconcileSnapshotIn,
    RiskConfigChangedIn,
    Recommendation,
    ReconcileMismatch,
    RiskDecisionIn,
    StrategyStructureProposedIn,
    StrategyBuilderCandidatesIn,
    StrategyBuilderCandidatesOut,
    StrategyCandidateOut,
    RiskStatus,
    StrategyHealthRow,
    TradeCardResponse,
    TradeReviewItem,
    TradingHaltIn,
    ExitPlanCreatedIn,
    TradingModeChangedIn,
    FillEventIn,
    FeatureBuildIn,
    FeatureBuildOut,
    FeatureRow,
    UniverseActivateIn,
    UniverseActivatedOut,
    IngestionRunIn,
    IngestionRunOut,
    IngestionTickerSummary,
    PaperTradeRunIn,
    PaperTradeRunOut,
    ReplayCandidateResult,
    ReplayRunIn,
    ReplayRunOut,
    ShellStatusOut,
    OpsMetricsOut,
    BrokerStatusOut,
    BrokerConnectOut,
    StrategyRuntimeIn,
    StrategyRuntimeOut,
    UniverseUploadedOut,
    UniverseVersionRow,
    UniverseValidationResult,
    WatchlistOpportunity,
    TradeDecisionSaveIn,
    TradeDecisionPatchIn,
    TradeDecisionOut,
    DashboardSummaryOut,
    DashboardDecisionQuality,
    EnrichedRecommendation,
    TradeReviewCompleteIn,
    TradeReviewClassifyOut,
)
from app.engines.feature_engine import build_symbol_features
from app.engines.ingestion_engine import (
    build_mock_option_chain,
    normalize_context_snapshot,
    normalize_market_snapshot,
    normalize_option_chain_from_tws,
)
from app.engines.paper_trade_engine import simulate_paper_trade
from app.engines.replay_engine import replay_candidates_under_scenarios
from app.engines.strategy_runtime_engine import run_strategy_runtime
from app.engines.strategy_builder_engine import build_and_rank_candidates
from app.services.event_store import (
    active_universe_view,
    append_event,
    blotter_view,
    explain_feed_view,
    get_latest_event_payload,
    list_recent_events,
    list_recommendations_view,
    positions_view,
    reconcile_mismatches_view,
    risk_status_view,
    strategy_health_view,
    trade_card_view,
    trade_review_queue_view,
    universe_versions_view,
    watchlist_view,
)
from app.services.broker.factory import get_broker_client
from app.services.decision_store import dashboard_summary, get_decision, list_decisions, patch_decision
from app.services.decisions_service import enriched_recommendations, save_decision_from_candidate
from app.services.paper_decision_service import run_paper_for_decision
from app.services.broker_session import connect_broker_session, evaluate_broker_connection
from app.services.broker_status import runtime_gate_status, snapshot_data_status
from app.services.observability import log_runtime_event, metrics_snapshot, request_timing_middleware
from app.workers.reconcile_worker import ReconcileWorker
from app.workers.tws_connection_worker import TwsConnectionWorker

app = FastAPI(title=settings.app_name, version=settings.app_version)
engine = get_engine()
broker_client = get_broker_client()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _broker_state() -> dict:
    return evaluate_broker_connection()


def _broker_data_status(broker: dict) -> str:
    reachable = broker.get("tws_reachable") or broker.get("gateway_reachable")
    if not reachable:
        return "disconnected"
    if not broker.get("connected"):
        return "disconnected"
    return "live"


def _aggregate_data_status(statuses: list[str]) -> str:
    priority = ["disconnected", "stale", "degraded", "mock", "live"]
    for item in priority:
        if item in statuses:
            return item
    return "live"


def _evaluate_reconcile_state() -> dict:
    mismatches = reconcile_mismatches_view(engine)
    blocking = [row for row in mismatches if row.blocking]
    oldest = max((row.mismatch_age_seconds for row in blocking), default=0)
    return {
        "status": "ok",
        "blocking_count": len(blocking),
        "oldest_blocking_age_seconds": oldest,
    }


def _emit_trading_halt(payload: dict) -> None:
    correlation_id, causation_id = _event_trace()
    append_event(
        engine=engine,
        event_type="TradingHaltEvent",
        aggregate_type="halt",
        aggregate_id=str(payload["halt_id"]),
        producer="reconcile_worker",
        payload=payload,
        schema_ref="bd.events.trading_halt.v1",
        idempotency_key=f"reconcile_worker:TradingHaltEvent:{payload['halt_id']}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    log_runtime_event(event="trading_halt_emitted", halt_id=payload["halt_id"], reason=payload.get("reason_code"))


reconcile_worker = ReconcileWorker(
    interval_seconds=settings.reconcile_worker_interval_seconds,
    mismatch_halt_seconds=settings.reconcile_mismatch_halt_seconds,
    evaluate_fn=_evaluate_reconcile_state,
    emit_halt_fn=_emit_trading_halt,
)


def _broker_heartbeat_once() -> None:
    broker_client.heartbeat()


def _broker_reconnect_once() -> None:
    broker_client.connect()


tws_connection_worker = TwsConnectionWorker(
    interval_seconds=settings.tws_connection_interval_seconds,
    heartbeat_fn=_broker_heartbeat_once,
    reconnect_fn=_broker_reconnect_once,
)


def _broker_status_out() -> BrokerStatusOut:
    now = datetime.now(UTC)
    broker = _broker_state()
    data_status = _broker_data_status(broker)
    tws_reachable = bool(broker.get("tws_reachable") or broker.get("gateway_reachable"))
    if not tws_reachable:
        message = "Start TWS paper, enable API (read-only), port 7497, then Connect Broker."
        next_action = "start_tws_paper"
    elif not broker.get("authenticated"):
        message = "TWS is reachable but not connected. Click Connect Broker."
        next_action = "connect_tws"
    else:
        message = "TWS read-only session is live."
        next_action = "run_ingestion"
    return BrokerStatusOut(
        as_of=now,
        tws_reachable=tws_reachable,
        broker_connected=bool(broker.get("connected")),
        broker_authenticated=bool(broker.get("authenticated")),
        data_status=data_status,  # type: ignore[arg-type]
        tws_host=str(broker.get("tws_host", settings.tws_host)),
        tws_port=int(broker.get("tws_port", settings.tws_port)),
        tws_client_id=int(broker.get("tws_client_id", settings.tws_client_id)),
        tws_read_only=bool(broker.get("read_only", settings.tws_read_only)),
        connection_worker_status=tws_connection_worker.last_status,
        message=message,
        next_action=next_action,
    )


def _shell_status() -> ShellStatusOut:
    now = datetime.now(UTC)
    broker = _broker_state()
    risk = risk_status_view(engine)
    mismatches = reconcile_mismatches_view(engine)
    blocking = [row for row in mismatches if row.blocking]
    data_status = _broker_data_status(broker)
    runtime_allowed, runtime_block_reason = runtime_gate_status(
        broker_connected=bool(broker.get("connected")),
        data_status=data_status,  # type: ignore[arg-type]
        reconciliation_mismatch_active=bool(blocking),
        allow_mock_option_chain=settings.allow_mock_option_chain,
    )
    execution_mode = settings.execution_mode
    if risk.active_halts or blocking:
        execution_mode = "halted"
    elif not risk.can_open_new_entries:
        execution_mode = "close_only"
    return ShellStatusOut(
        as_of=now,
        broker_connected=bool(broker.get("connected")),
        broker_authenticated=bool(broker.get("authenticated")),
        data_status=data_status,  # type: ignore[arg-type]
        execution_mode=execution_mode,  # type: ignore[arg-type]
        trading_mode=risk.trading_mode,
        reconcile_worker_status=reconcile_worker.last_status,
        reconcile_blocking_count=len(blocking),
        can_open_new_entries=risk.can_open_new_entries and runtime_allowed,
        active_halts=risk.active_halts,
        runtime_block_reason=None if runtime_allowed else runtime_block_reason,
    )


def _active_or_default_tickers(requested: list[str]) -> list[str]:
    normalized = [t.strip().upper() for t in requested if t and t.strip()]
    if normalized:
        return normalized
    active = active_universe_view(engine)
    if active and active.tickers:
        return [t.strip().upper() for t in active.tickers if t and t.strip()]
    return [t.strip().upper() for t in settings.default_runtime_tickers if t and t.strip()]


def _latest_payload_by_event_ticker(event_type: str, ticker: str) -> dict | None:
    rows = list_recent_events(engine, limit=5000)
    target = ticker.strip().upper()
    for row in rows:
        if row.event_type != event_type:
            continue
        details = row.details or {}
        if str(details.get("ticker", "")).upper() == target:
            return details
    return None


def _to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _extract_primary_conid(secdef_result: dict | list, ticker: str) -> str | None:
    if not isinstance(secdef_result, list):
        return None
    target = ticker.upper()
    for row in secdef_result:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", "")).upper()
        sections = row.get("sections", [])
        has_stk = isinstance(sections, list) and any(
            isinstance(sec, dict) and str(sec.get("secType", "")).upper() == "STK" for sec in sections
        )
        if symbol == target and has_stk and row.get("conid"):
            return str(row["conid"])
    for row in secdef_result:
        if isinstance(row, dict) and row.get("conid"):
            return str(row["conid"])
    return None


def _compute_news_score(news_rows: dict | list | None) -> tuple[float, str]:
    if not isinstance(news_rows, list) or not news_rows:
        return 0.0, "no recent news headlines"
    positive_words = {"beat", "surge", "growth", "upgrade", "record", "strong", "bullish", "outperform"}
    negative_words = {"miss", "drop", "downgrade", "weak", "lawsuit", "probe", "bearish", "warning"}
    score = 0.0
    for row in news_rows:
        if not isinstance(row, dict):
            continue
        text = " ".join(
            str(row.get(key, "")) for key in ("headline", "title", "summary", "text", "story_text")
        ).lower()
        if not text:
            continue
        score += sum(1 for w in positive_words if w in text)
        score -= sum(1 for w in negative_words if w in text)
    score = max(-15.0, min(15.0, score * 2.5))
    if score > 0:
        reason = "news tone positive"
    elif score < 0:
        reason = "news tone negative"
    else:
        reason = "news tone neutral"
    return score, reason


def _determinism_key(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _normalize_ticker(raw: str) -> str:
    return raw.strip().upper()


def _event_trace(causation_id: str | None = None) -> tuple[str, str]:
    correlation_id = str(uuid4())
    return correlation_id, causation_id or correlation_id


def _validate_ticker_via_broker(ticker: str) -> UniverseValidationResult:
    info = broker_client.qualify_stock(ticker)
    if info:
        return UniverseValidationResult(
            ticker=ticker,
            status="validated",
            ibkr_conid=str(info.conid),
            primary_exchange=info.exchange or None,
            ambiguity={"is_ambiguous": False, "candidates": []},
        )
    return UniverseValidationResult(
        ticker=ticker,
        status="invalid",
        ambiguity={"is_ambiguous": False, "candidates": []},
    )


def _extract_json_universe(payload: dict) -> tuple[str, str, list[str]]:
    universe_id = str(payload.get("universe_id", "")).strip() or f"universe_{datetime.now(UTC).strftime('%Y%m%d')}"
    as_of = str(payload.get("as_of", datetime.now(UTC).date().isoformat()))
    tickers_raw = payload.get("tickers")
    if not isinstance(tickers_raw, list):
        raise HTTPException(status_code=422, detail="Universe JSON must include a tickers list")

    deduped: list[str] = []
    seen: set[str] = set()
    for raw in tickers_raw:
        ticker = _normalize_ticker(str(raw))
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        deduped.append(ticker)
    if not deduped:
        raise HTTPException(status_code=422, detail="Universe JSON must contain at least one valid ticker")
    if len(deduped) > 200:
        raise HTTPException(status_code=422, detail="Universe JSON exceeds max_tickers=200")
    return universe_id, as_of, deduped


def _latest_event_payload_for_signal(event_type: str, signal_id: str) -> dict | None:
    rows = list_recent_events(engine, limit=2000)
    for row in rows:
        if row.event_type != event_type:
            continue
        details = row.details or {}
        if str(details.get("signal_id", "")) == signal_id:
            return details
    return None


def _latest_event_payload_for_ticker(event_type: str, ticker: str) -> dict | None:
    target = ticker.strip().upper()
    rows = list_recent_events(engine, limit=3000)
    for row in rows:
        if row.event_type != event_type:
            continue
        details = row.details or {}
        if str(details.get("ticker", "")).upper() == target:
            return details
    return None


def _is_pause_new_entries_mode() -> bool:
    rows = list_recent_events(engine, limit=1000)
    for row in rows:
        if row.event_type != "RiskDecision":
            continue
        details = row.details or {}
        drawdown_mode = str(details.get("drawdown_mode", "")).upper()
        if drawdown_mode:
            return drawdown_mode == "PAUSE_NEW_ENTRIES"
    return False


def _latest_order_status(order_intent_id: str) -> str | None:
    rows = list_recent_events(engine, limit=3000)
    for row in rows:
        if row.event_type != "BrokerOrderEvent":
            continue
        details = row.details or {}
        if str(details.get("order_intent_id", "")) == order_intent_id:
            status = details.get("status")
            return str(status) if status else None
    return None


def _is_valid_order_transition(previous: str | None, current: str) -> bool:
    transitions = {
        None: {"CREATED"},
        "CREATED": {"SENT"},
        "SENT": {"ACK", "REJECTED"},
        "ACK": {"PARTIAL", "FILLED", "CANCELLED", "EXPIRED"},
        "PARTIAL": {"FILLED", "CANCELLED", "EXPIRED"},
        "FILLED": set(),
        "CANCELLED": set(),
        "REJECTED": set(),
        "EXPIRED": set(),
    }
    return current in transitions.get(previous, set())


def _build_candidate_from_broker(
    *,
    ticker: str,
    strategy_sleeve: str,
    trading_mode: str,
    include_news: bool,
) -> tuple[CandidateSignalIn, float, str]:
    info = broker_client.qualify_stock(ticker)
    if not info:
        raise ValueError(f"{ticker}: unable to resolve contract")
    snap = broker_client.market_snapshot(ticker)
    if not snap:
        raise ValueError(f"{ticker}: empty market snapshot")
    last = _to_float(snap.get("last"))
    bid = _to_float(snap.get("bid"))
    ask = _to_float(snap.get("ask"))
    conid = str(info.conid)

    quote_type = "real_time"
    quote_score = 0.0
    spread_pct = 0.01
    if bid and ask and bid > 0 and ask > 0:
        mid = (bid + ask) / 2.0
        spread_pct = max(0.0, (ask - bid) / mid) if mid > 0 else 0.02
        if spread_pct <= 0.002:
            quote_score += 20.0
        elif spread_pct <= 0.01:
            quote_score += 10.0
        else:
            quote_score -= 5.0
        if last and bid <= last <= ask:
            quote_score += 10.0
    else:
        quote_type = "snapshot"
        quote_score -= 10.0

    news_score = 0.0
    news_reason = "news not available via TWS read-only path"
    if include_news:
        news_rows = None
        news_score, news_reason = _compute_news_score(news_rows)

    confidence = max(0.0, min(100.0, 55.0 + quote_score + news_score))
    edge = round(((confidence - 50.0) * 1.8) - (spread_pct * 100.0 * 2.0), 2)
    side = "bullish" if confidence >= 62 else ("neutral" if confidence >= 48 else "bearish")
    regime = "trend_low_vol" if spread_pct <= 0.01 and confidence >= 60 else "chop"

    px = last or (bid if bid else (ask if ask else 100.0))
    entry_low = round(px * 0.995, 2)
    entry_high = round(px * 1.005, 2)
    inv = round(px * 0.97, 2)
    target_1 = round(px * 1.02, 2)
    target_2 = round(px * 1.04, 2)

    signal_id = f"sig_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{ticker.replace('.', '_')}_auto"
    ts_key = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    rationale = f"spread={spread_pct:.4f}, {news_reason}"
    seed_payload = {
        "ticker": ticker,
        "conid": conid,
        "quote_type": quote_type,
        "spread_pct": spread_pct,
        "trading_mode": trading_mode,
    }
    candidate = CandidateSignalIn(
        signal_id=signal_id,
        ticker=ticker,
        strategy_sleeve=strategy_sleeve,
        side=side,  # type: ignore[arg-type]
        signal_config_version="sig_cfg_v1",
        model_version="ibkr_simple_rank_v1",
        feature_version="ibkr_quote_news_v1",
        regime_label=regime,
        data_sources_used=["TWS"],
        snapshot_refs={
            "market_snapshot_ref": f"evt:MarketSnapshot:ms_{ts_key}_{ticker}",
            "options_snapshot_ref": f"evt:OptionsChainSnapshot:ocs_{ts_key}_{ticker}",
            "news_snapshot_ref": f"evt:NewsSnapshot:ns_{ts_key}_{ticker}",
        },
        determinism_key=_determinism_key(seed_payload),
        confidence_components={
            "technical": round(max(0.0, confidence - 8.0), 1),
            "options_quality": round(max(0.0, confidence - 12.0), 1),
            "event_sentiment": round(max(0.0, confidence - 15.0), 1),
            "fundamental_sector": round(max(0.0, confidence - 10.0), 1),
            "regime_fit": round(max(0.0, confidence - 9.0), 1),
            "execution_quality": round(max(0.0, confidence - 14.0), 1),
        },
        confidence_total=round(confidence, 1),
        thesis=f"Auto-generated from IBKR quote quality and headline tone ({rationale}).",
        entry_zone=f"{entry_low}-{entry_high}",
        invalidation=f"< {inv}",
        targets=[str(target_1), str(target_2)],
        expected_hold_days=28,
        expected_edge_after_cost_usd=edge,
        quote_type=quote_type,  # type: ignore[arg-type]
        trading_mode=trading_mode,  # type: ignore[arg-type]
    )
    return candidate, confidence, rationale


def _run_ingestion_once(*, tickers: list[str], include_news: bool) -> IngestionRunOut:
    run_id = f"ing_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}_{uuid4().hex[:8]}"
    summaries: list[IngestionTickerSummary] = []
    broker = _broker_state()
    broker_connected = bool(broker.get("connected"))
    ticker_statuses: list[str] = []
    for ticker in tickers:
        symbol = ticker.strip().upper()
        if not symbol:
            continue
        snap_row = broker_client.market_snapshot(symbol)
        market_snapshot = (
            snap_row
            if snap_row
            else normalize_market_snapshot(ticker=symbol, ibkr_snapshot=None)
        )
        last_px = float(market_snapshot["last"])

        def _fetch_chain() -> tuple[list[dict], str, str]:
            return broker_client.option_chain(symbol=symbol, last_price=last_px)

        option_chain, chain_source, _chain_reason = normalize_option_chain_from_tws(
            ticker=symbol,
            last_price=last_px,
            broker_connected=broker_connected,
            fetch_chain=_fetch_chain,
            allow_mock_fallback=settings.allow_mock_option_chain,
        )
        captured_at = str(market_snapshot.get("captured_at"))
        ticker_data_status = snapshot_data_status(
            captured_at=captured_at,
            broker_connected=broker_connected,
            chain_source=chain_source,
        )
        ticker_statuses.append(ticker_data_status)
        news_rows: list[dict] = []
        context_snapshot = normalize_context_snapshot(ticker=symbol, market_snapshot=market_snapshot, news_rows=news_rows)

        corr, caus = _event_trace()
        market_event_id = append_event(
            engine=engine,
            event_type="MarketSnapshotCaptured",
            aggregate_type="ticker",
            aggregate_id=symbol,
            producer="ingestion_worker",
            payload={**market_snapshot, "data_status": ticker_data_status},
            schema_ref="bd.events.market_snapshot_captured.v1",
            idempotency_key=f"ingestion_worker:MarketSnapshotCaptured:{symbol}:{run_id}",
            correlation_id=corr,
            causation_id=caus,
        )
        option_event_id = append_event(
            engine=engine,
            event_type="OptionsChainSnapshotCaptured",
            aggregate_type="ticker",
            aggregate_id=symbol,
            producer="ingestion_worker",
            payload={
                "ticker": symbol,
                "captured_at": datetime.now(UTC).isoformat(),
                "rows": option_chain,
                "data_status": ticker_data_status,
                "chain_source": chain_source,
            },
            schema_ref="bd.events.options_chain_snapshot_captured.v1",
            idempotency_key=f"ingestion_worker:OptionsChainSnapshotCaptured:{symbol}:{run_id}",
            correlation_id=corr,
            causation_id=caus,
        )
        context_event_id = append_event(
            engine=engine,
            event_type="ContextSnapshotCaptured",
            aggregate_type="ticker",
            aggregate_id=symbol,
            producer="ingestion_worker",
            payload=context_snapshot,
            schema_ref="bd.events.context_snapshot_captured.v1",
            idempotency_key=f"ingestion_worker:ContextSnapshotCaptured:{symbol}:{run_id}",
            correlation_id=corr,
            causation_id=caus,
        )
        summaries.append(
            IngestionTickerSummary(
                ticker=symbol,
                market_snapshot_event_id=market_event_id,
                option_chain_event_id=option_event_id,
                context_snapshot_event_id=context_event_id,
                data_status=ticker_data_status,  # type: ignore[arg-type]
                chain_source=chain_source,  # type: ignore[arg-type]
            )
        )
    aggregate_status = _aggregate_data_status(ticker_statuses) if ticker_statuses else ("disconnected" if not broker_connected else "live")
    return IngestionRunOut(
        run_id=run_id,
        processed=len(summaries),
        results=summaries,
        as_of=datetime.now(UTC),
        data_status=aggregate_status,  # type: ignore[arg-type]
    )


def _run_feature_build_once(*, tickers: list[str]) -> FeatureBuildOut:
    run_id = f"feat_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}_{uuid4().hex[:8]}"
    results: list[FeatureRow] = []
    for ticker in tickers:
        symbol = ticker.strip().upper()
        market = _latest_payload_by_event_ticker("MarketSnapshotCaptured", symbol)
        options_payload = _latest_payload_by_event_ticker("OptionsChainSnapshotCaptured", symbol)
        context = _latest_payload_by_event_ticker("ContextSnapshotCaptured", symbol)
        if not market or not options_payload:
            continue
        option_rows = options_payload.get("rows", [])
        if not isinstance(option_rows, list):
            option_rows = []
        features = build_symbol_features(
            ticker=symbol,
            market_snapshot=market,
            option_chain=option_rows,
            context_snapshot=context or {"news_score": 0.0, "sector_strength_score": 50.0, "event_risk_score": 50.0},
        )
        corr, caus = _event_trace()
        feature_event_id = append_event(
            engine=engine,
            event_type="SymbolFeatureSnapshotBuilt",
            aggregate_type="ticker",
            aggregate_id=symbol,
            producer="feature_engine",
            payload=features,
            schema_ref="st.events.symbol_feature_snapshot_built.v1",
            idempotency_key=f"feature_engine:SymbolFeatureSnapshotBuilt:{symbol}:{run_id}",
            correlation_id=corr,
            causation_id=caus,
        )
        results.append(FeatureRow(ticker=symbol, feature_event_id=feature_event_id, feature=features))
    return FeatureBuildOut(
        run_id=run_id,
        built=len(results),
        results=results,
        as_of=datetime.now(UTC),
        data_status="live",
    )


def _run_strategy_runtime_once(
    *,
    ticker: str,
    direction: str,
    reconciliation_mismatch_active: bool,
    thresholds: dict[str, float],
) -> StrategyRuntimeOut:
    symbol = ticker.strip().upper()
    market = _latest_payload_by_event_ticker("MarketSnapshotCaptured", symbol)
    options_payload = _latest_payload_by_event_ticker("OptionsChainSnapshotCaptured", symbol)
    feature = _latest_payload_by_event_ticker("SymbolFeatureSnapshotBuilt", symbol)
    if not market or not options_payload:
        _run_ingestion_once(tickers=[symbol], include_news=True)
        market = _latest_payload_by_event_ticker("MarketSnapshotCaptured", symbol)
        options_payload = _latest_payload_by_event_ticker("OptionsChainSnapshotCaptured", symbol)
    if not feature:
        _run_feature_build_once(tickers=[symbol])
        feature = _latest_payload_by_event_ticker("SymbolFeatureSnapshotBuilt", symbol)
    if not market or not options_payload or not feature:
        raise HTTPException(status_code=422, detail=f"Unable to build runtime snapshots for ticker {symbol}")
    options_rows = options_payload.get("rows", [])
    if not isinstance(options_rows, list):
        options_rows = []
    chain_source = str(options_payload.get("chain_source", "mock"))
    captured_at = str(options_payload.get("captured_at") or market.get("captured_at"))
    broker = _broker_state()
    data_status = snapshot_data_status(
        captured_at=captured_at,
        broker_connected=bool(broker.get("connected")),
        chain_source=chain_source,
    )
    runtime_allowed, runtime_block_reason = runtime_gate_status(
        broker_connected=bool(broker.get("connected")),
        data_status=data_status,
        reconciliation_mismatch_active=reconciliation_mismatch_active,
        allow_mock_option_chain=settings.allow_mock_option_chain,
    )
    candidates: list[dict] = []
    if runtime_allowed:
        candidates = run_strategy_runtime(
            ticker=symbol,
            direction=direction,
            market_snapshot=market,
            feature_snapshot=feature,
            option_chain_snapshot=options_rows,
            reconciliation_mismatch_active=reconciliation_mismatch_active,
            thresholds=thresholds,
        )
    return StrategyRuntimeOut(
        ticker=symbol,
        direction=direction,  # type: ignore[arg-type]
        feature_snapshot_ref=f"evt:SymbolFeatureSnapshotBuilt:{symbol}",
        option_chain_snapshot_ref=f"evt:OptionsChainSnapshotCaptured:{symbol}",
        candidates=[StrategyCandidateOut(**row) for row in candidates],
        as_of=datetime.now(UTC),
        data_status=data_status,
        runtime_allowed=runtime_allowed,
        runtime_block_reason=runtime_block_reason if not runtime_allowed else None,
    )


def _seed_if_empty() -> None:
    with engine.begin() as conn:
        first = conn.execute(select(event_log.c.seq_id).limit(1)).first()
    if first:
        return

    sig = CandidateSignalIn(
        signal_id="sig_20260212_NVDA_001",
        ticker="NVDA",
        strategy_sleeve="options_defined_risk",
        side="bullish",
        signal_config_version="sig_cfg_v1",
        model_version="sig_model_2026_02_12_a",
        feature_version="feat_v3",
        regime_label="trend_low_vol",
        data_sources_used=["IBKR", "Finnhub"],
        snapshot_refs={
            "market_snapshot_ref": "evt:MarketSnapshot:ms_20260212_NVDA_150401",
            "options_snapshot_ref": "evt:OptionsChainSnapshot:ocs_20260212_NVDA_150401",
            "news_snapshot_ref": "evt:NewsSnapshot:ns_20260212_NVDA_150350",
        },
        determinism_key=_determinism_key({"seed": "nvda_20260212"}),
        confidence_total=78.4,
        thesis="Seed data: pullback setup with positive post-cost expectancy.",
        entry_zone="890-900",
        invalidation="< 865",
        targets=["930", "950"],
        expected_edge_after_cost_usd=92.3,
        quote_type="real_time",
        trading_mode="paper",
    )
    bootstrap_corr, bootstrap_caus = _event_trace()
    append_event(
        engine=engine,
        event_type="CandidateSignal",
        aggregate_type="signal",
        aggregate_id=sig.signal_id,
        producer="bootstrap",
        payload=sig.model_dump(),
        schema_ref="st.events.candidate_signal.v1",
        idempotency_key=f"bootstrap:CandidateSignal:{sig.signal_id}",
        correlation_id=bootstrap_corr,
        causation_id=bootstrap_caus,
    )

    rd = RiskDecisionIn(
        risk_decision_id="rd_20260212_NVDA_001",
        signal_id=sig.signal_id,
        status="approved",
        risk_config_version="risk_cfg_v1",
        trading_mode="paper",
        expected_total_cost_usd=8.7,
        expected_edge_after_cost_usd=92.3,
        data_health={"market": "OK", "options": "OK", "news": "DEGRADED"},
        worst_case_stress_loss_nav_pct=-0.64,
        reasons=[],
        drawdown_pct=-2.1,
    )
    bootstrap_risk_corr, bootstrap_risk_caus = _event_trace()
    append_event(
        engine=engine,
        event_type="RiskDecision",
        aggregate_type="risk",
        aggregate_id=rd.risk_decision_id,
        producer="bootstrap",
        payload=rd.model_dump(),
        schema_ref="st.events.risk_decision.v1",
        idempotency_key=f"bootstrap:RiskDecision:{rd.risk_decision_id}",
        correlation_id=bootstrap_risk_corr,
        causation_id=bootstrap_risk_caus,
    )


def _write_candidate_signal_event(payload: CandidateSignalIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="CandidateSignal",
        aggregate_type="signal",
        aggregate_id=payload.signal_id,
        producer="signal_engine",
        payload=payload.model_dump(),
        schema_ref="st.events.candidate_signal.v1",
        idempotency_key=f"signal_engine:CandidateSignal:{payload.signal_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(event_id=event_id, event_type="CandidateSignal", aggregate_id=payload.signal_id)


@app.on_event("startup")
def startup() -> None:
    init_db(engine)
    _seed_if_empty()
    reconcile_worker.start()
    tws_connection_worker.start()
    if settings.auto_ingestion_on_startup:
        tickers = _active_or_default_tickers([])
        if tickers:
            _run_ingestion_once(tickers=tickers, include_news=False)
            _run_feature_build_once(tickers=tickers)


@app.on_event("shutdown")
def shutdown() -> None:
    reconcile_worker.stop()
    tws_connection_worker.stop()
    broker_client.disconnect()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    now = datetime.now(UTC)
    shell = _shell_status()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        timestamp=now,
        as_of=now,
        execution_mode=shell.execution_mode,
        data_status=shell.data_status,
    )


@app.get("/api/ops/shell-status", response_model=ShellStatusOut)
def shell_status() -> ShellStatusOut:
    return _shell_status()


@app.get("/api/ops/metrics", response_model=OpsMetricsOut)
def ops_metrics() -> OpsMetricsOut:
    snapshot = metrics_snapshot()
    return OpsMetricsOut(as_of=datetime.now(UTC), requests=snapshot["requests"], errors=snapshot["errors"])


@app.get("/api/ops/broker/status", response_model=BrokerStatusOut)
def broker_status() -> BrokerStatusOut:
    return _broker_status_out()


@app.post("/api/ops/broker/connect", response_model=BrokerConnectOut)
def broker_connect(refresh_ingestion: bool = Query(default=True)) -> BrokerConnectOut:
    now = datetime.now(UTC)
    try:
        result = connect_broker_session()
    except Exception as exc:
        return BrokerConnectOut(
            as_of=now,
            status="error",
            message=str(exc),
            next_action="check_tws_api_settings",
            data_status="disconnected",
            steps=[],
        )

    status = str(result.get("status", "error"))
    if status not in {"connected", "tws_unreachable"}:
        status = "error"

    ingestion_processed = 0
    data_status: str = "disconnected"
    if status == "connected":
        data_status = "live"
        if refresh_ingestion:
            tickers = _active_or_default_tickers([])
            if tickers:
                try:
                    ing = _run_ingestion_once(tickers=tickers, include_news=True)
                    _run_feature_build_once(tickers=tickers)
                    ingestion_processed = ing.processed
                    data_status = ing.data_status
                except Exception as exc:
                    log_runtime_event(event="broker_connect_ingestion_error", error=str(exc))
                    data_status = "degraded"
        tws_connection_worker.tick_once()

    return BrokerConnectOut(
        as_of=now,
        status=status,  # type: ignore[arg-type]
        message=str(result.get("message", "")),
        next_action=str(result.get("next_action", "")),
        data_status=data_status,  # type: ignore[arg-type]
        ingestion_processed=ingestion_processed,
        steps=list(result.get("steps", [])),
    )


@app.get("/api/recommendations", response_model=list[Recommendation])
def list_recommendations() -> list[Recommendation]:
    return list_recommendations_view(engine)


@app.get("/api/risk-status", response_model=RiskStatus)
def risk_status() -> RiskStatus:
    return risk_status_view(engine)


@app.get("/api/events", response_model=list[EventSummary])
def events() -> list[EventSummary]:
    return list_recent_events(engine, limit=200)


@app.get("/api/explain-feed", response_model=list[ExplainFeedItem])
def explain_feed(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    correlation_id: str | None = Query(default=None),
    minutes: int | None = Query(default=None, ge=1, le=720),
    scope: str | None = Query(default=None),
    decision_id: str | None = Query(default=None),
) -> list[ExplainFeedItem]:
    return explain_feed_view(
        engine,
        ticker=ticker,
        limit=limit,
        correlation_id=correlation_id,
        minutes=minutes,
        scope=scope,
        decision_id=decision_id,
    )


@app.get("/api/dashboard/summary", response_model=DashboardSummaryOut)
def dashboard_summary_endpoint() -> DashboardSummaryOut:
    metrics = dashboard_summary(engine)
    return DashboardSummaryOut(
        as_of=datetime.now(UTC),
        decision_quality=DashboardDecisionQuality(**metrics),
        shell=_shell_status(),
    )


@app.get("/api/dashboard/recommendations", response_model=list[EnrichedRecommendation])
def dashboard_recommendations() -> list[EnrichedRecommendation]:
    return enriched_recommendations(engine)


@app.post("/api/decisions/save", response_model=TradeDecisionOut)
def decisions_save(payload: TradeDecisionSaveIn) -> TradeDecisionOut:
    saved = save_decision_from_candidate(engine, payload.model_dump())
    corr, caus = _event_trace()
    append_event(
        engine=engine,
        event_type="TradeDecisionSaved",
        aggregate_type="decision",
        aggregate_id=saved.decision_id,
        producer="decision_service",
        payload={"decision_id": saved.decision_id, "symbol": saved.symbol, "strategy_type": saved.strategy_type},
        schema_ref="bd.events.trade_decision_saved.v1",
        idempotency_key=f"decision_service:TradeDecisionSaved:{saved.decision_id}",
        correlation_id=corr,
        causation_id=caus,
    )
    return saved


@app.get("/api/decisions", response_model=list[TradeDecisionOut])
def decisions_list(
    symbol: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
) -> list[TradeDecisionOut]:
    rows = list_decisions(engine, symbol=symbol, review_status=review_status)
    return [TradeDecisionOut(**{k: v for k, v in r.items() if k in TradeDecisionOut.model_fields}) for r in rows]


@app.get("/api/decisions/{decision_id}", response_model=TradeDecisionOut)
def decisions_get(decision_id: str) -> TradeDecisionOut:
    row = get_decision(engine, decision_id)
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")
    return TradeDecisionOut(**{k: v for k, v in row.items() if k in TradeDecisionOut.model_fields})


@app.patch("/api/decisions/{decision_id}", response_model=TradeDecisionOut)
def decisions_patch(decision_id: str, payload: TradeDecisionPatchIn) -> TradeDecisionOut:
    updates = payload.model_dump(exclude_unset=True)
    if payload.rejected:
        updates["current_status"] = "rejected"
        updates["review_status"] = "reviewed"
        updates["final_outcome"] = "not_reviewed"
    row = patch_decision(engine, decision_id, updates)
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")
    return TradeDecisionOut(**{k: v for k, v in row.items() if k in TradeDecisionOut.model_fields})


@app.get("/api/trade-review", response_model=list[TradeReviewItem])
def trade_review() -> list[TradeReviewItem]:
    return trade_review_queue_view(engine, limit=200)


@app.post("/api/trade-review/{decision_id}/classify", response_model=TradeReviewClassifyOut)
def trade_review_classify(decision_id: str) -> TradeReviewClassifyOut:
    row = get_decision(engine, decision_id)
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")
    from app.engines.review_engine import infer_review_flags

    flags = infer_review_flags(
        decision=row,
        realized_pnl=float(row.get("paper_pnl") or 0),
        scenario_return=float(row.get("paper_pnl_percent") or 0) / 100.0,
    )
    updated = patch_decision(
        engine,
        decision_id,
        {"final_outcome": flags["final_outcome"], "extra": {**(row.get("extra") or {}), **flags}},
    )
    return TradeReviewClassifyOut(
        decision_id=decision_id,
        final_outcome=flags["final_outcome"],  # type: ignore[arg-type]
        review_status="ready_for_review",
    )


@app.post("/api/trade-review/{decision_id}/complete", response_model=TradeDecisionOut)
def trade_review_complete(decision_id: str, payload: TradeReviewCompleteIn) -> TradeDecisionOut:
    row = patch_decision(
        engine,
        decision_id,
        {
            "final_outcome": payload.final_outcome,
            "lesson": payload.lesson,
            "review_status": "reviewed",
        },
    )
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")
    return TradeDecisionOut(**{k: v for k, v in row.items() if k in TradeDecisionOut.model_fields})


@app.get("/api/strategy-health", response_model=list[StrategyHealthRow])
def strategy_health() -> list[StrategyHealthRow]:
    return strategy_health_view(engine)


@app.get("/api/trade-review-queue", response_model=list[TradeReviewItem])
def trade_review_queue() -> list[TradeReviewItem]:
    return trade_review_queue_view(engine, limit=200)


@app.post("/api/strategy-builder/candidates", response_model=StrategyBuilderCandidatesOut)
def strategy_builder_candidates(payload: StrategyBuilderCandidatesIn) -> StrategyBuilderCandidatesOut:
    feature = dict(payload.feature or {})
    feature.setdefault("iv_percentile", 50.0)
    feature.setdefault("trend_score", 50.0)
    feature.setdefault("atr_14", max(1.0, payload.last_price * 0.015))
    feature.setdefault("news_score", 0.0)
    feature.setdefault("beta_to_spy", 1.0)
    feature.setdefault("beta_to_qqq", 1.0)
    feature.setdefault("sector_strength_score", 50.0)
    feature.setdefault("overextended_penalty", 0.0)

    candidates = build_and_rank_candidates(
        symbol=payload.symbol.strip().upper(),
        direction=payload.direction,
        last_price=payload.last_price,
        feature=feature,
        option_chain=[row.model_dump() for row in payload.option_chain],
        reconciliation_mismatch_active=payload.reconciliation_mismatch_active,
        thresholds=payload.thresholds,
    )

    out_rows = [StrategyCandidateOut(**row) for row in candidates]
    return StrategyBuilderCandidatesOut(
        symbol=payload.symbol.strip().upper(),
        direction=payload.direction,
        candidates=out_rows,
        as_of=datetime.now(UTC),
        data_status="mock" if payload.reconciliation_mismatch_active else "live",
    )


@app.post("/api/ops/ingestion/run-once", response_model=IngestionRunOut)
def run_ingestion_once(payload: IngestionRunIn) -> IngestionRunOut:
    tickers = _active_or_default_tickers(payload.tickers)
    if not tickers:
        raise HTTPException(status_code=422, detail="No tickers available for ingestion")
    return _run_ingestion_once(tickers=tickers, include_news=payload.include_news)


@app.post("/api/ops/features/build", response_model=FeatureBuildOut)
def run_feature_build(payload: FeatureBuildIn) -> FeatureBuildOut:
    tickers = _active_or_default_tickers(payload.tickers)
    if not tickers:
        raise HTTPException(status_code=422, detail="No tickers available for feature build")
    return _run_feature_build_once(tickers=tickers)


@app.post("/api/ops/scheduler/tick")
def scheduler_tick() -> dict:
    tickers = _active_or_default_tickers([])
    ing = _run_ingestion_once(tickers=tickers, include_news=False)
    feat = _run_feature_build_once(tickers=tickers)
    return {"status": "ok", "tickers": tickers, "ingestion_processed": ing.processed, "features_built": feat.built}


@app.post("/api/strategy-builder/runtime", response_model=StrategyRuntimeOut)
def strategy_builder_runtime(payload: StrategyRuntimeIn) -> StrategyRuntimeOut:
    return _run_strategy_runtime_once(
        ticker=payload.ticker,
        direction=payload.direction,
        reconciliation_mismatch_active=payload.reconciliation_mismatch_active,
        thresholds=payload.thresholds,
    )


@app.post("/api/replay/run", response_model=ReplayRunOut)
def replay_run(payload: ReplayRunIn) -> ReplayRunOut:
    runtime = _run_strategy_runtime_once(
        ticker=payload.ticker,
        direction=payload.direction,
        reconciliation_mismatch_active=False,
        thresholds={},
    )
    replayed = replay_candidates_under_scenarios(
        candidates=[row.model_dump(mode="json") for row in runtime.candidates],
        scenarios=payload.scenarios,
    )
    return ReplayRunOut(
        ticker=payload.ticker.strip().upper(),
        direction=payload.direction,
        scenarios=payload.scenarios,
        results=[ReplayCandidateResult(**row) for row in replayed],
        as_of=datetime.now(UTC),
        data_status=runtime.data_status,
    )


@app.post("/api/paper/run", response_model=PaperTradeRunOut)
def paper_trade_run(payload: PaperTradeRunIn) -> PaperTradeRunOut:
    if payload.mode == "decision":
        if not payload.decision_id:
            raise HTTPException(status_code=422, detail="decision_id is required for decision-based paper trading")
        decision = get_decision(engine, payload.decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail="Decision not found")
        if decision.get("paper_order_id"):
            raise HTTPException(status_code=409, detail="Decision already has a linked paper trade")
        out, _ = run_paper_for_decision(
            engine=engine,
            decision=decision,
            scenario_return=payload.scenario_return,
            trace_fn=_event_trace,
        )
        return out

    if payload.mode != "quick":
        raise HTTPException(status_code=422, detail="Invalid paper mode")
    if not payload.ticker or not payload.direction:
        raise HTTPException(status_code=422, detail="ticker and direction required for quick paper test")
    runtime = _run_strategy_runtime_once(
        ticker=payload.ticker,
        direction=payload.direction,
        reconciliation_mismatch_active=False,
        thresholds={},
    )
    if not runtime.runtime_allowed:
        raise HTTPException(status_code=403, detail=f"Paper trade blocked: {runtime.runtime_block_reason}")
    candidate = next((row for row in runtime.candidates if row.risk_status == "allow"), None)
    if not candidate:
        raise HTTPException(status_code=422, detail="Quick paper test requires an allow-risk candidate")
    saved = save_decision_from_candidate(
        engine,
        {
            "candidate": candidate,
            "symbol": payload.ticker.strip().upper(),
            "direction": payload.direction,
            "confidence": 50.0,
            "edge": candidate.expected_value,
            "market_regime": "quick_test",
            "thesis": "Quick paper test (developer mode)",
            "data_status": runtime.data_status,
            "broker_status": "mock",
            "reconciliation_status": "ok",
        },
    )
    decision = get_decision(engine, saved.decision_id)
    if not decision:
        raise HTTPException(status_code=500, detail="Failed to create quick-test decision")
    out, _ = run_paper_for_decision(
        engine=engine,
        decision=decision,
        scenario_return=payload.scenario_return,
        trace_fn=_event_trace,
    )
    out.mode = "quick"
    return out



@app.post("/api/universe/upload", response_model=UniverseUploadedOut)
async def universe_upload(file: UploadFile = File(...)) -> UniverseUploadedOut:
    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()
    allowed = {"application/json", "text/json", "text/plain", ""}
    # curl multipart commonly sends application/octet-stream unless type is set explicitly.
    if content_type == "application/octet-stream" and filename.endswith(".json"):
        content_type = "application/json"
    if content_type not in allowed:
        raise HTTPException(status_code=415, detail="Universe upload must be a JSON file")
    contents = await file.read()
    if len(contents) > 1_048_576:
        raise HTTPException(status_code=413, detail="Universe JSON exceeds max_file_size_bytes=1048576")
    try:
        payload = json.loads(contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Universe JSON root must be an object")

    universe_id, as_of, tickers = _extract_json_universe(payload)
    validation_results = [_validate_ticker_via_broker(ticker) for ticker in tickers]
    upload_errors: list[dict[str, str]] = []
    ambiguous = [r for r in validation_results if r.status == "ambiguous"]
    invalid = [r for r in validation_results if r.status == "invalid"]
    if ambiguous:
        upload_errors.append(
            {
                "code": "SECCDEF_AMBIGUOUS",
                "detail": "One or more tickers returned ambiguous secdef results",
            }
        )
    if invalid:
        upload_errors.append(
            {
                "code": "SECCDEF_INVALID",
                "detail": "One or more tickers failed secdef validation",
            }
        )
    upload_status = "failed" if upload_errors else "validated"
    universe_version_id = f"uv_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{universe_id}"
    event_payload = {
        "universe_version_id": universe_version_id,
        "universe_id": universe_id,
        "as_of": as_of,
        "source": "human_trader",
        "upload_contract": {
            "content_type": "application/json",
            "multipart_field": "file",
            "max_tickers": 200,
            "max_file_size_bytes": 1048576,
        },
        "tickers_requested": tickers,
        "validation_results": [row.model_dump() for row in validation_results],
        "upload_status": upload_status,
        "upload_errors": upload_errors,
    }
    upload_corr, upload_caus = _event_trace()
    event_id = append_event(
        correlation_id=upload_corr,
        causation_id=upload_caus,
        engine=engine,
        event_type="UniverseUploaded",
        aggregate_type="universe_version",
        aggregate_id=universe_version_id,
        producer="universe_service",
        payload=event_payload,
        schema_ref="st.events.universe_uploaded.v1",
        idempotency_key=f"universe_service:UniverseUploaded:{universe_version_id}",
    )
    return UniverseUploadedOut(
        universe_version_id=universe_version_id,
        universe_id=universe_id,
        as_of=as_of,
        tickers_requested=tickers,
        upload_status=upload_status,  # type: ignore[arg-type]
        validation_results=validation_results,
        upload_errors=upload_errors,
        event_id=event_id,
    )


@app.post("/api/universe/activate", response_model=UniverseActivatedOut)
def universe_activate(payload: UniverseActivateIn) -> UniverseActivatedOut:
    uploaded = get_latest_event_payload(engine, "UniverseUploaded")
    if not uploaded:
        raise HTTPException(status_code=404, detail="No uploaded universe found")
    latest_version = str(uploaded.get("universe_version_id", ""))
    if payload.universe_version_id != latest_version:
        raise HTTPException(status_code=409, detail="Activation requires the latest uploaded universe_version_id")
    if str(uploaded.get("upload_status", "failed")) != "validated":
        raise HTTPException(status_code=422, detail="Activation blocked: uploaded universe is not fully validated")

    activated_at = datetime.now(UTC)
    event_payload = {
        "universe_version_id": payload.universe_version_id,
        "universe_id": payload.universe_id,
        "activated_at": activated_at.isoformat(),
        "activated_by": payload.activated_by,
        "activation_policy": {
            "allow_partial_activation": False,
            "ambiguous_secdef_default": "hard_fail",
        },
    }
    activate_corr, activate_caus = _event_trace()
    event_id = append_event(
        correlation_id=activate_corr,
        causation_id=activate_caus,
        engine=engine,
        event_type="UniverseActivated",
        aggregate_type="universe",
        aggregate_id=payload.universe_id,
        producer="universe_service",
        payload=event_payload,
        schema_ref="st.events.universe_activated.v1",
        idempotency_key=f"universe_service:UniverseActivated:{payload.universe_version_id}",
    )
    return UniverseActivatedOut(
        universe_version_id=payload.universe_version_id,
        universe_id=payload.universe_id,
        activated_at=activated_at,
        activated_by=payload.activated_by,
        event_id=event_id,
    )


@app.get("/api/universe/active", response_model=ActiveUniverseResponse)
def universe_active() -> ActiveUniverseResponse:
    active = active_universe_view(engine)
    if not active:
        raise HTTPException(status_code=404, detail="No active universe")
    return active


@app.get("/api/universe/versions", response_model=list[UniverseVersionRow])
def universe_versions() -> list[UniverseVersionRow]:
    return universe_versions_view(engine, limit=100)


@app.get("/api/watchlist", response_model=list[WatchlistOpportunity])
def watchlist() -> list[WatchlistOpportunity]:
    return watchlist_view(engine)


@app.get("/api/tickers/{ticker}/trade-card", response_model=TradeCardResponse)
def trade_card(ticker: str) -> TradeCardResponse:
    return trade_card_view(engine, ticker=ticker)


@app.get("/api/positions", response_model=PositionsResponse)
def positions() -> PositionsResponse:
    return positions_view(engine)


@app.get("/api/blotter", response_model=list[dict])
def blotter() -> list[dict]:
    return [row.model_dump(mode="json") for row in blotter_view(engine)]


@app.get("/api/reconcile/mismatches", response_model=list[ReconcileMismatch])
def reconcile_mismatches() -> list[ReconcileMismatch]:
    return reconcile_mismatches_view(engine)


@app.get("/api/ibkr/health")
def ibkr_health() -> dict:
    """Legacy path; returns TWS read-only connection health."""
    broker = _broker_state()
    reachable = bool(broker.get("tws_reachable") or broker.get("gateway_reachable"))
    if not reachable:
        return {
            "broker": "tws",
            "status": "unreachable",
            "message": f"Connect TWS paper API at {settings.tws_host}:{settings.tws_port} (read-only).",
            **broker,
        }
    return {
        "broker": "tws",
        "status": "ok" if broker.get("authenticated") else "disconnected",
        "read_only": settings.tws_read_only,
        **broker,
    }


@app.get("/api/ibkr/accounts")
def ibkr_accounts() -> dict:
    accounts = getattr(broker_client, "list_accounts", lambda: [])()
    return {"accounts": accounts}


@app.get("/api/ibkr/secdef/search")
def ibkr_secdef_search(symbol: str = Query(min_length=1)) -> dict:
    info = broker_client.qualify_stock(symbol)
    if not info:
        raise HTTPException(status_code=404, detail=f"Unable to qualify {symbol}")
    return {
        "symbol": info.symbol,
        "conid": info.conid,
        "exchange": info.exchange,
        "currency": info.currency,
    }


@app.get("/api/ibkr/marketdata/snapshot")
def ibkr_marketdata_snapshot(symbol: str = Query(min_length=1)) -> dict:
    snap = broker_client.market_snapshot(symbol)
    if not snap:
        raise HTTPException(status_code=503, detail="Market snapshot unavailable (TWS disconnected or no data)")
    return snap


@app.get("/api/ibkr/portfolio/{account_id}/positions/{page_id}")
def ibkr_positions(account_id: str, page_id: int) -> dict:
    del account_id, page_id
    return {"positions": broker_client.list_positions()}


@app.get("/api/ibkr/orders")
def ibkr_orders() -> dict:
    return {"orders": broker_client.list_open_orders()}


@app.get("/api/ops/broker/fills")
def broker_fills() -> dict:
    return {"fills": broker_client.list_executions()}


@app.post("/api/events/candidate-signal", response_model=EventWriteResponse)
def write_candidate_signal(payload: CandidateSignalIn) -> EventWriteResponse:
    return _write_candidate_signal_event(payload)


@app.post("/api/events/candidate-signal/bulk", response_model=CandidateSignalBulkOut)
def write_candidate_signal_bulk(payload: CandidateSignalBulkIn) -> CandidateSignalBulkOut:
    results = [_write_candidate_signal_event(item) for item in payload.items]
    return CandidateSignalBulkOut(requested=len(payload.items), written=len(results), results=results)


@app.post("/api/signals/generate-from-ibkr", response_model=GenerateSignalsFromIbkrOut)
def generate_signals_from_ibkr(payload: GenerateSignalsFromIbkrIn) -> GenerateSignalsFromIbkrOut:
    candidates: list[tuple[CandidateSignalIn, float, str]] = []
    skipped: list[str] = []
    requested_tickers = payload.tickers
    if not requested_tickers:
        active = active_universe_view(engine)
        if not active:
            raise HTTPException(status_code=422, detail="No active universe; provide tickers or activate a universe")
        requested_tickers = active.tickers
    for ticker in requested_tickers:
        symbol = ticker.strip().upper()
        if not symbol:
            continue
        try:
            candidates.append(
                _build_candidate_from_broker(
                    ticker=symbol,
                    strategy_sleeve=payload.strategy_sleeve,
                    trading_mode=payload.trading_mode,
                    include_news=payload.include_news,
                )
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{symbol}: {exc}")

    ranked = sorted(candidates, key=lambda row: row[1], reverse=True)[: payload.top_n]
    summaries: list[GeneratedSignalSummary] = []
    for candidate, _score, rationale in ranked:
        _write_candidate_signal_event(candidate)
        summaries.append(
            GeneratedSignalSummary(
                ticker=candidate.ticker,
                signal_id=candidate.signal_id,
                confidence_total=candidate.confidence_total,
                quote_type=candidate.quote_type,
                expected_edge_after_cost_usd=candidate.expected_edge_after_cost_usd,
                rationale=rationale,
            )
        )

    return GenerateSignalsFromIbkrOut(
        requested=len(requested_tickers),
        generated=len(summaries),
        skipped=skipped,
        results=summaries,
    )


@app.post("/api/events/risk-decision", response_model=EventWriteResponse)
def write_risk_decision(payload: RiskDecisionIn) -> EventWriteResponse:
    # Enforce minimum risk hard-rules from architecture before persisting.
    rule_reasons = list(payload.rule_reasons)
    status = payload.status
    if payload.expected_edge_after_cost_usd <= 0:
        status = "override_required"
        rule_reasons.append(
            {
                "rule_code": "NEG_EDGE_AFTER_COST",
                "message": "edge after costs <= 0",
                "observed_value": payload.expected_edge_after_cost_usd,
                "threshold_value": 0,
            }
        )
    non_ok_sources = [k for k, v in payload.data_health.items() if v != "OK"]
    if non_ok_sources:
        status = "override_required"
        rule_reasons.append(
            {
                "rule_code": "INPUT_DATA_HEALTH_NOT_OK",
                "message": "one or more data health domains are not OK",
                "observed_value": ",".join(non_ok_sources),
                "threshold_value": "OK",
            }
        )
    if payload.worst_case_stress_loss_nav_pct <= -1.0:
        status = "override_required"
        rule_reasons.append(
            {
                "rule_code": "STRESS_NAV_BREACH",
                "message": "worst case stress loss exceeds NAV threshold",
                "observed_value": payload.worst_case_stress_loss_nav_pct,
                "threshold_value": -1.0,
            }
        )

    risk_payload = payload.model_dump()
    risk_payload["status"] = status
    risk_payload["rule_reasons"] = rule_reasons
    risk_payload["overrideable_rule_codes"] = sorted(
        {str(item.get("rule_code")) for item in rule_reasons if item.get("rule_code")}
    )

    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="RiskDecision",
        aggregate_type="risk",
        aggregate_id=payload.risk_decision_id,
        producer="risk_engine",
        payload=risk_payload,
        schema_ref="st.events.risk_decision.v1",
        idempotency_key=f"risk_engine:RiskDecision:{payload.risk_decision_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(event_id=event_id, event_type="RiskDecision", aggregate_id=payload.risk_decision_id)


@app.post("/api/events/approval-request", response_model=EventWriteResponse)
def write_approval_request(payload: ApprovalRequestIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="ApprovalRequestCreated",
        aggregate_type="approval",
        aggregate_id=payload.approval_request_id,
        producer="approval_layer",
        payload=payload.model_dump(),
        schema_ref="st.events.approval_request_created.v1",
        idempotency_key=f"approval_layer:ApprovalRequestCreated:{payload.approval_request_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="ApprovalRequestCreated",
        aggregate_id=payload.approval_request_id,
    )


@app.post("/api/events/approval-decision", response_model=EventWriteResponse)
def write_approval_decision(payload: ApprovalDecisionIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="ApprovalDecision",
        aggregate_type="approval",
        aggregate_id=payload.approval_request_id,
        producer="approval_layer",
        payload=payload.model_dump(),
        schema_ref="st.events.approval_decision.v1",
        idempotency_key=f"approval_layer:ApprovalDecision:{payload.approval_request_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="ApprovalDecision",
        aggregate_id=payload.approval_request_id,
    )


@app.post("/api/events/order-intent", response_model=EventWriteResponse)
def write_order_intent(payload: OrderIntentCreatedIn) -> EventWriteResponse:
    if _is_pause_new_entries_mode():
        raise HTTPException(status_code=422, detail="OrderIntentCreated blocked: drawdown mode is PAUSE_NEW_ENTRIES")

    risk = _latest_event_payload_for_signal("RiskDecision", payload.signal_id)
    if not risk:
        raise HTTPException(status_code=422, detail="RiskDecision not found for signal")
    risk_status = str(risk.get("status", risk.get("decision", "")))
    if risk_status not in {"approved", "override_required"}:
        raise HTTPException(status_code=422, detail=f"Risk gate failed: status={risk_status}")

    approval = _latest_event_payload_for_signal("ApprovalDecision", payload.signal_id)
    if not approval:
        raise HTTPException(status_code=422, detail="ApprovalDecision not found for signal")

    approval_decision = str(approval.get("decision", ""))
    if approval_decision not in {"approved", "override"}:
        raise HTTPException(status_code=422, detail=f"Approval gate failed: decision={approval_decision}")
    override_allowed = bool(approval.get("override", False)) or approval_decision == "override"
    if risk_status == "override_required" and not override_allowed:
        raise HTTPException(
            status_code=422,
            detail="Risk override_required needs ApprovalDecision.override=true or decision=override before OrderIntentCreated",
        )

    latest_dh = _latest_event_payload_for_ticker("DataHealthEvaluated", payload.ticker)
    if latest_dh:
        execution_decision = str((latest_dh.get("decision") or {}).get("execution", "ALLOW")).upper()
        if execution_decision != "ALLOW" and not override_allowed:
            raise HTTPException(
                status_code=422,
                detail=f"OrderIntentCreated blocked: DataHealthEvaluated.decision.execution={execution_decision}",
            )

    event_payload = payload.model_dump()
    event_payload["override_recheck_passed"] = bool(override_allowed or risk_status == "approved")
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="OrderIntentCreated",
        aggregate_type="order_intent",
        aggregate_id=payload.order_intent_id,
        producer="execution_engine",
        payload=event_payload,
        schema_ref="st.events.order_intent_created.v1",
        idempotency_key=payload.idempotency_key
        or f"execution_engine:OrderIntentCreated:{payload.order_intent_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="OrderIntentCreated",
        aggregate_id=payload.order_intent_id,
    )


@app.post("/api/events/exit-plan", response_model=EventWriteResponse)
def write_exit_plan(payload: ExitPlanCreatedIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="ExitPlanCreated",
        aggregate_type="exit_plan",
        aggregate_id=payload.exit_plan_id,
        producer="risk_engine",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.exit_plan_created.v1",
        idempotency_key=f"risk_engine:ExitPlanCreated:{payload.exit_plan_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(event_id=event_id, event_type="ExitPlanCreated", aggregate_id=payload.exit_plan_id)


@app.post("/api/events/position-opened", response_model=EventWriteResponse)
def write_position_opened(payload: PositionOpenedIn) -> EventWriteResponse:
    # Schema rule: position open requires a linked ExitPlanCreated.
    exit_plan = _latest_event_payload_for_signal("ExitPlanCreated", payload.signal_id)
    if not exit_plan:
        raise HTTPException(status_code=422, detail="PositionOpened blocked: missing ExitPlanCreated for signal")

    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="PositionOpened",
        aggregate_type="position",
        aggregate_id=payload.position_event_id,
        producer="execution_engine",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.position_opened.v1",
        idempotency_key=f"execution_engine:PositionOpened:{payload.position_event_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(event_id=event_id, event_type="PositionOpened", aggregate_id=payload.position_event_id)


@app.post("/api/events/strategy-structure", response_model=EventWriteResponse)
def write_strategy_structure(payload: StrategyStructureProposedIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="StrategyStructureProposed",
        aggregate_type="structure",
        aggregate_id=payload.structure_id,
        producer="strategy_builder",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.strategy_structure_proposed.v1",
        idempotency_key=f"strategy_builder:StrategyStructureProposed:{payload.structure_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="StrategyStructureProposed",
        aggregate_id=payload.structure_id,
    )


@app.post("/api/events/data-health", response_model=EventWriteResponse)
def write_data_health(payload: DataHealthEvaluatedIn) -> EventWriteResponse:
    ticker = payload.ticker.strip().upper()
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="DataHealthEvaluated",
        aggregate_type="ticker",
        aggregate_id=ticker,
        producer="data_quality_gate",
        payload={**payload.model_dump(mode="json"), "ticker": ticker},
        schema_ref="st.events.data_health_evaluated.v1",
        idempotency_key=f"data_quality_gate:DataHealthEvaluated:{ticker}:{payload.evaluated_at.isoformat()}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="DataHealthEvaluated",
        aggregate_id=ticker,
    )


@app.post("/api/events/reconcile-snapshot", response_model=EventWriteResponse)
def write_reconcile_snapshot(payload: ReconcileSnapshotIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="ReconcileSnapshot",
        aggregate_type="reconcile",
        aggregate_id=payload.snapshot_id,
        producer="reconciliation_service",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.reconcile_snapshot.v1",
        idempotency_key=f"reconciliation_service:ReconcileSnapshot:{payload.snapshot_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="ReconcileSnapshot",
        aggregate_id=payload.snapshot_id,
    )


@app.post("/api/events/mismatch-detected", response_model=EventWriteResponse)
def write_mismatch_detected(payload: MismatchDetectedIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="MismatchDetected",
        aggregate_type="reconcile",
        aggregate_id=payload.mismatch_id,
        producer="reconciliation_service",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.mismatch_detected.v1",
        idempotency_key=f"reconciliation_service:MismatchDetected:{payload.mismatch_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="MismatchDetected",
        aggregate_id=payload.mismatch_id,
    )


@app.post("/api/events/broker-request-response", response_model=EventWriteResponse)
def write_broker_request_response(payload: BrokerRequestResponseRecordedIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="BrokerRequestResponseRecorded",
        aggregate_type="order_intent",
        aggregate_id=payload.order_intent_id,
        producer="execution_engine",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.broker_request_response_recorded.v1",
        idempotency_key=f"execution_engine:BrokerRequestResponseRecorded:{payload.request_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="BrokerRequestResponseRecorded",
        aggregate_id=payload.order_intent_id,
    )


@app.post("/api/events/broker-order", response_model=EventWriteResponse)
def write_broker_order_event(payload: BrokerOrderEventIn) -> EventWriteResponse:
    previous = _latest_order_status(payload.order_intent_id)
    if not _is_valid_order_transition(previous, payload.status):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid order state transition: {previous or 'NONE'} -> {payload.status}",
        )
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="BrokerOrderEvent",
        aggregate_type="order_intent",
        aggregate_id=payload.order_intent_id,
        producer="execution_engine",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.broker_order_event.v1",
        idempotency_key=f"execution_engine:BrokerOrderEvent:{payload.broker_event_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="BrokerOrderEvent",
        aggregate_id=payload.order_intent_id,
    )


@app.post("/api/events/fill", response_model=EventWriteResponse)
def write_fill_event(payload: FillEventIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="FillEvent",
        aggregate_type="order_intent",
        aggregate_id=payload.order_intent_id,
        producer="execution_engine",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.fill_event.v1",
        idempotency_key=f"execution_engine:FillEvent:{payload.fill_event_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="FillEvent",
        aggregate_id=payload.order_intent_id,
    )


@app.post("/api/events/risk-config-changed", response_model=EventWriteResponse)
def write_risk_config_changed(payload: RiskConfigChangedIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    aggregate_id = f"risk_cfg_{payload.changed_at.isoformat()}"
    event_id = append_event(
        engine=engine,
        event_type="RiskConfigChanged",
        aggregate_type="config",
        aggregate_id=aggregate_id,
        producer="governance",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.risk_config_changed.v1",
        idempotency_key=f"governance:RiskConfigChanged:{aggregate_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(event_id=event_id, event_type="RiskConfigChanged", aggregate_id=aggregate_id)


@app.post("/api/events/trading-mode-changed", response_model=EventWriteResponse)
def write_trading_mode_changed(payload: TradingModeChangedIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    aggregate_id = f"mode_{payload.changed_at.isoformat()}"
    event_id = append_event(
        engine=engine,
        event_type="TradingModeChanged",
        aggregate_type="config",
        aggregate_id=aggregate_id,
        producer="governance",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.trading_mode_changed.v1",
        idempotency_key=f"governance:TradingModeChanged:{aggregate_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(event_id=event_id, event_type="TradingModeChanged", aggregate_id=aggregate_id)


@app.post("/api/ops/circuit-breakers/evaluate")
def evaluate_circuit_breakers() -> dict:
    alerts: list[str] = []
    emitted: list[str] = []

    health = strategy_health_view(engine)
    negative_sleeves = [row for row in health if row.trades >= 20 and row.expectancy_after_costs_usd < 0]
    for row in negative_sleeves:
        halt_id = f"halt_expectancy_{row.strategy_sleeve}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        payload = {
            "halt_id": halt_id,
            "scope": "sleeve",
            "reason_code": "EXPECTANCY_BREACH",
            "reason_detail": f"{row.strategy_sleeve} expectancy below zero over {row.trades} trades",
            "trigger_metrics": f"expectancy_after_costs_usd={row.expectancy_after_costs_usd:.2f}",
            "start_time": datetime.now(UTC).isoformat(),
            "end_time": None,
            "cleared_by": None,
        }
        append_event(
            engine=engine,
            event_type="TradingHaltEvent",
            aggregate_type="halt",
            aggregate_id=halt_id,
            producer="circuit_breakers",
            payload=payload,
            schema_ref="st.events.trading_halt.v1",
            idempotency_key=f"circuit_breakers:TradingHaltEvent:{halt_id}",
            correlation_id=str(uuid4()),
            causation_id=str(uuid4()),
        )
        emitted.append(halt_id)
        alerts.append(payload["reason_detail"])

    mismatches = reconcile_mismatches_view(engine)
    stale_blocking = [m for m in mismatches if m.blocking and m.mismatch_age_seconds >= 600]
    if stale_blocking:
        halt_id = f"halt_reconcile_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        payload = {
            "halt_id": halt_id,
            "scope": "global",
            "reason_code": "RECONCILE_STALE_BLOCK",
            "reason_detail": f"{len(stale_blocking)} blocking mismatches older than 10 minutes",
            "trigger_metrics": f"blocking_count={len(stale_blocking)}",
            "start_time": datetime.now(UTC).isoformat(),
            "end_time": None,
            "cleared_by": None,
        }
        append_event(
            engine=engine,
            event_type="TradingHaltEvent",
            aggregate_type="halt",
            aggregate_id=halt_id,
            producer="circuit_breakers",
            payload=payload,
            schema_ref="st.events.trading_halt.v1",
            idempotency_key=f"circuit_breakers:TradingHaltEvent:{halt_id}",
            correlation_id=str(uuid4()),
            causation_id=str(uuid4()),
        )
        emitted.append(halt_id)
        alerts.append(payload["reason_detail"])

    return {"status": "ok", "alerts": alerts, "halts_emitted": emitted}


@app.post("/api/events/trading-halt", response_model=EventWriteResponse)
def write_trading_halt(payload: TradingHaltIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="TradingHaltEvent",
        aggregate_type="halt",
        aggregate_id=payload.halt_id,
        producer="risk_engine",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.trading_halt.v1",
        idempotency_key=f"risk_engine:TradingHaltEvent:{payload.halt_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="TradingHaltEvent",
        aggregate_id=payload.halt_id,
    )


@app.post("/api/events/position-closed", response_model=EventWriteResponse)
def write_position_closed(payload: PositionClosedIn) -> EventWriteResponse:
    correlation_id, causation_id = _event_trace()
    event_id = append_event(
        engine=engine,
        event_type="PositionClosed",
        aggregate_type="position",
        aggregate_id=payload.position_event_id,
        producer="execution_engine",
        payload=payload.model_dump(mode="json"),
        schema_ref="st.events.position_closed.v1",
        idempotency_key=f"execution_engine:PositionClosed:{payload.position_event_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    return EventWriteResponse(
        event_id=event_id,
        event_type="PositionClosed",
        aggregate_id=payload.position_event_id,
    )


app = request_timing_middleware(app)

