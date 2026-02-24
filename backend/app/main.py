from datetime import UTC, datetime
import hashlib
import json
from uuid import uuid4

import httpx
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
    RiskStatus,
    StrategyHealthRow,
    TradeCardResponse,
    TradeReviewItem,
    TradingHaltIn,
    ExitPlanCreatedIn,
    TradingModeChangedIn,
    FillEventIn,
    UniverseActivateIn,
    UniverseActivatedOut,
    UniverseUploadedOut,
    UniverseVersionRow,
    UniverseValidationResult,
    WatchlistOpportunity,
)
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
from app.services.ibkr_gateway import IbkrGatewayClient, IbkrGatewayConfig

app = FastAPI(title=settings.app_name, version=settings.app_version)
engine = get_engine()
ibkr_client = IbkrGatewayClient(
    IbkrGatewayConfig(
        base_url=settings.ibkr_gateway_base_url,
        timeout_seconds=settings.ibkr_timeout_seconds,
        verify_tls=settings.ibkr_verify_tls,
    )
)

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


def _ibkr_get(endpoint: str, params: dict | None = None) -> dict | list:
    try:
        return ibkr_client.get(endpoint, params=params)
    except httpx.HTTPStatusError as exc:
        detail = {"message": "IBKR gateway returned an error", "status_code": exc.response.status_code}
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        detail = {"message": "Unable to reach IBKR gateway", "error": str(exc)}
        raise HTTPException(status_code=503, detail=detail) from exc


def _ibkr_get_optional(endpoint: str, params: dict | None = None) -> dict | list | None:
    try:
        return _ibkr_get(endpoint, params=params)
    except HTTPException:
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


def _validate_ticker_via_ibkr(ticker: str) -> UniverseValidationResult:
    secdef = _ibkr_get_optional("/iserver/secdef/search", params={"symbol": ticker})
    if not isinstance(secdef, list) or not secdef:
        return UniverseValidationResult(
            ticker=ticker,
            status="invalid",
            ambiguity={"is_ambiguous": False, "candidates": []},
        )

    candidates = []
    exact_stk = []
    for row in secdef:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", "")).upper()
        sections = row.get("sections", [])
        has_stk = isinstance(sections, list) and any(
            isinstance(sec, dict) and str(sec.get("secType", "")).upper() == "STK" for sec in sections
        )
        if symbol == ticker and has_stk:
            exact_stk.append(row)
        if row.get("conid"):
            candidates.append(
                {
                    "display": str(row.get("description") or row.get("name") or row.get("symbol") or ticker),
                    "conid": str(row.get("conid")),
                    "exchange": str(row.get("description") or ""),
                }
            )

    if len(exact_stk) == 1:
        one = exact_stk[0]
        return UniverseValidationResult(
            ticker=ticker,
            status="validated",
            ibkr_conid=str(one.get("conid")),
            primary_exchange=str(one.get("description") or "") or None,
            ambiguity={"is_ambiguous": False, "candidates": []},
        )
    # Auto-resolve common US primary exchanges to reduce false ambiguity for
    # tickers like AAPL/MSFT/SPY that also have non-US listings.
    preferred_exchanges = ("NASDAQ", "NYSE", "ARCA", "AMEX")
    preferred_matches = [
        row
        for row in exact_stk
        if str(row.get("description", "")).upper() in preferred_exchanges
    ]
    if len(preferred_matches) == 1:
        one = preferred_matches[0]
        return UniverseValidationResult(
            ticker=ticker,
            status="validated",
            ibkr_conid=str(one.get("conid")),
            primary_exchange=str(one.get("description") or "") or None,
            ambiguity={"is_ambiguous": False, "candidates": []},
        )
    if len(exact_stk) > 1:
        return UniverseValidationResult(
            ticker=ticker,
            status="ambiguous",
            ambiguity={"is_ambiguous": True, "candidates": candidates[:10]},
        )
    return UniverseValidationResult(
        ticker=ticker,
        status="invalid",
        ambiguity={"is_ambiguous": False, "candidates": candidates[:10]},
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


def _build_candidate_from_ibkr(
    *,
    ticker: str,
    strategy_sleeve: str,
    trading_mode: str,
    include_news: bool,
) -> tuple[CandidateSignalIn, float, str]:
    secdef = _ibkr_get("/iserver/secdef/search", params={"symbol": ticker})
    conid = _extract_primary_conid(secdef, ticker)
    if not conid:
        raise ValueError(f"{ticker}: unable to resolve conid")

    snapshot_resp = _ibkr_get("/iserver/marketdata/snapshot", params={"conids": conid, "fields": "31,84,86,88"})
    if not isinstance(snapshot_resp, list) or not snapshot_resp:
        raise ValueError(f"{ticker}: empty market snapshot")
    quote = snapshot_resp[0] if isinstance(snapshot_resp[0], dict) else {}
    last = _to_float(quote.get("31") or quote.get("last"))
    bid = _to_float(quote.get("84") or quote.get("bid"))
    ask = _to_float(quote.get("86") or quote.get("ask"))

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
    news_reason = "news not requested"
    if include_news:
        news_rows = _ibkr_get_optional("/iserver/news", params={"conid": conid, "limit": 5})
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
        data_sources_used=["IBKR"],
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


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        timestamp=datetime.now(UTC),
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
) -> list[ExplainFeedItem]:
    return explain_feed_view(
        engine,
        ticker=ticker,
        limit=limit,
        correlation_id=correlation_id,
        minutes=minutes,
    )


@app.get("/api/strategy-health", response_model=list[StrategyHealthRow])
def strategy_health() -> list[StrategyHealthRow]:
    return strategy_health_view(engine)


@app.get("/api/trade-review-queue", response_model=list[TradeReviewItem])
def trade_review_queue() -> list[TradeReviewItem]:
    return trade_review_queue_view(engine, limit=200)


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
    validation_results = [_validate_ticker_via_ibkr(ticker) for ticker in tickers]
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
    tickle = _ibkr_get("/tickle")
    auth_status = _ibkr_get("/iserver/auth/status")
    accounts = _ibkr_get("/portfolio/accounts")
    return {"gateway": "ok", "tickle": tickle, "auth_status": auth_status, "accounts": accounts}


@app.get("/api/ibkr/accounts")
def ibkr_accounts() -> dict | list:
    return _ibkr_get("/portfolio/accounts")


@app.get("/api/ibkr/secdef/search")
def ibkr_secdef_search(symbol: str = Query(min_length=1)) -> dict | list:
    return _ibkr_get("/iserver/secdef/search", params={"symbol": symbol})


@app.get("/api/ibkr/marketdata/snapshot")
def ibkr_marketdata_snapshot(conids: str = Query(min_length=1), fields: str = "31,84,86,88") -> dict | list:
    return _ibkr_get("/iserver/marketdata/snapshot", params={"conids": conids, "fields": fields})


@app.get("/api/ibkr/portfolio/{account_id}/positions/{page_id}")
def ibkr_positions(account_id: str, page_id: int) -> dict | list:
    return _ibkr_get(f"/portfolio/{account_id}/positions/{page_id}")


@app.get("/api/ibkr/orders")
def ibkr_orders() -> dict | list:
    return _ibkr_get("/iserver/account/orders")


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
                _build_candidate_from_ibkr(
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


