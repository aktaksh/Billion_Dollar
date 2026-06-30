from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TradingMode = Literal["paper", "micro_live", "normal_live"]
SignalSide = Literal["bullish", "bearish", "neutral"]
QuoteType = Literal["real_time", "delayed", "snapshot"]
DataStatus = Literal["live", "stale", "mock", "degraded", "disconnected"]
ExecutionMode = Literal["paper_only", "read_only", "manual_approval", "close_only", "halted"]
DataHealth = Literal["OK", "Degraded", "Blocked"]
TickerState = Literal[
    "NoSignal",
    "CandidateSignal",
    "StructureProposed",
    "RiskApproved",
    "AwaitingApproval",
    "OrderIntent",
    "Executed",
    "Reconciled",
    "PositionOpen",
    "PositionClosed",
    "Reviewed",
]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    version: str
    timestamp: datetime
    as_of: datetime
    execution_mode: ExecutionMode = "paper_only"
    data_status: DataStatus = "live"


class Recommendation(BaseModel):
    signal_id: str
    ticker: str
    strategy_sleeve: str
    side: SignalSide
    trading_mode: TradingMode
    confidence_total: float = Field(ge=0.0, le=100.0)
    regime_label: str
    thesis: str
    entry_zone: str
    invalidation: str
    targets: list[str] = Field(default_factory=list)
    data_sources_used: list[str] = Field(default_factory=list)
    quote_type: QuoteType
    expected_edge_after_cost_usd: float


class RiskStatus(BaseModel):
    trading_mode: TradingMode
    drawdown_pct: float
    worst_case_stress_loss_nav_pct: float
    can_open_new_entries: bool
    active_halts: list[str] = Field(default_factory=list)


class EventSummary(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    aggregate_type: str
    aggregate_id: str
    details: dict[str, Any]


ExplainSeverity = Literal["info", "warn", "block"]
ExplainCategory = Literal[
    "data",
    "news",
    "signal",
    "structure",
    "risk",
    "approval",
    "execution",
    "reconcile",
    "broker",
    "paper",
    "review",
    "system",
]


class ExplainFeedItem(BaseModel):
    event_id: str
    correlation_id: str | None = None
    ts: datetime
    ticker: str | None = None
    severity: ExplainSeverity = "info"
    category: ExplainCategory = "system"
    step: str
    human_message: str = ""
    event_type: str = ""
    scope: Literal["global", "ticker", "decision", "risk", "broker", "paper", "review"] = "global"
    linked_decision_id: str | None = None
    refs: dict[str, Any] = Field(default_factory=dict)


class CandidateSignalIn(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    signal_id: str
    ticker: str
    strategy_sleeve: str
    side: SignalSide
    signal_config_version: str = "sig_cfg_v1"
    signal_config_ref: str | None = None
    model_version: str
    feature_version: str
    feature_contract_version: str | None = None
    regime_label: str
    data_sources_used: list[str] = Field(default_factory=list)
    snapshot_refs: dict[str, str] = Field(default_factory=dict)
    determinism_key: str = "sha256:pending"
    confidence_total: float = Field(ge=0.0, le=100.0)
    confidence_components: dict[str, float] = Field(default_factory=dict)
    penalties: list[dict[str, Any]] = Field(default_factory=list)
    thesis: str
    entry_zone: str
    invalidation: str
    targets: list[str] = Field(default_factory=list)
    expected_hold_days: int = Field(default=28, ge=1, le=90)
    expected_edge_after_cost_usd: float
    quote_type: QuoteType
    trading_mode: TradingMode

    @model_validator(mode="after")
    def validate_required_repro_fields(self) -> "CandidateSignalIn":
        if not self.snapshot_refs:
            raise ValueError("snapshot_refs is required and must not be empty")
        required_snapshot_refs = {"market_snapshot_ref", "options_snapshot_ref"}
        missing = [k for k in required_snapshot_refs if k not in self.snapshot_refs]
        if missing:
            raise ValueError(f"snapshot_refs missing required keys: {', '.join(missing)}")
        if not self.determinism_key.startswith("sha256:") or self.determinism_key == "sha256:pending":
            raise ValueError("determinism_key must be a computed sha256 value")
        return self


class CandidateSignalBulkIn(BaseModel):
    items: list[CandidateSignalIn] = Field(min_length=1, max_length=200)


class RiskDecisionIn(BaseModel):
    risk_decision_id: str
    signal_id: str
    status: Literal["approved", "rejected", "override_required"]
    risk_config_version: str
    trading_mode: TradingMode
    expected_commission_usd: float = 0.0
    expected_fees_usd: float = 0.0
    expected_slippage_usd: float = 0.0
    expected_total_cost_usd: float
    expected_edge_after_cost_usd: float
    rule_reasons: list[dict[str, Any]] = Field(default_factory=list)
    overrideable_rule_codes: list[str] = Field(default_factory=list)
    spy_down_3pct_loss_usd: float = 0.0
    spy_down_5pct_loss_usd: float = 0.0
    vol_up_20pct_loss_usd: float = 0.0
    spread_widen_3x_loss_usd: float = 0.0
    data_health: dict[str, Literal["OK", "DEGRADED", "BLOCKED"]] = Field(default_factory=dict)
    worst_case_stress_loss_nav_pct: float
    reasons: list[str] = Field(default_factory=list)
    drawdown_pct: float = 0.0

    @model_validator(mode="after")
    def validate_data_health(self) -> "RiskDecisionIn":
        required_domains = {"market", "options", "news"}
        missing = [k for k in required_domains if k not in self.data_health]
        if missing:
            raise ValueError(f"data_health missing required keys: {', '.join(missing)}")
        if self.status == "override_required" and not self.rule_reasons:
            raise ValueError("rule_reasons is required when status=override_required")
        return self


class ApprovalDecisionIn(BaseModel):
    approval_request_id: str
    signal_id: str
    risk_decision_id: str
    exit_plan_id: str
    decision: Literal["approved", "rejected", "override"]
    actor: str
    override: bool = False
    override_reason: str | None = None
    checklist: dict[str, bool] = Field(default_factory=dict)
    override_flags: list[str] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def validate_override_reason(self) -> "ApprovalDecisionIn":
        if self.override and (not self.override_reason or not self.override_reason.strip()):
            raise ValueError("override_reason is required when override=true")
        required = {"thesis_complete", "liquidity_ok", "event_risk_ok", "risk_budget_ok"}
        if self.decision in {"approved", "override"}:
            missing = [k for k in required if k not in self.checklist]
            if missing:
                raise ValueError(f"checklist missing required keys: {', '.join(missing)}")
            incomplete = [k for k in required if not bool(self.checklist.get(k))]
            if incomplete and self.decision == "approved":
                raise ValueError("approved decisions require all checklist items=true")
        return self


class EventWriteResponse(BaseModel):
    event_id: str
    event_type: str
    aggregate_id: str


class CandidateSignalBulkOut(BaseModel):
    requested: int
    written: int
    results: list[EventWriteResponse]


class GenerateSignalsFromIbkrIn(BaseModel):
    tickers: list[str] = Field(default_factory=list, max_length=200)
    top_n: int = Field(default=10, ge=1, le=100)
    trading_mode: TradingMode = "paper"
    strategy_sleeve: str = "options_defined_risk"
    include_news: bool = True


class GeneratedSignalSummary(BaseModel):
    ticker: str
    signal_id: str
    confidence_total: float
    quote_type: QuoteType
    expected_edge_after_cost_usd: float
    rationale: str


class GenerateSignalsFromIbkrOut(BaseModel):
    requested: int
    generated: int
    skipped: list[str] = Field(default_factory=list)
    results: list[GeneratedSignalSummary] = Field(default_factory=list)


class ApprovalRequestIn(BaseModel):
    approval_request_id: str
    signal_id: str
    risk_decision_id: str
    exit_plan_id: str
    trading_mode_at_request: TradingMode
    risk_config_version: str
    risk_summary: str
    expected_total_cost_usd: float
    expected_edge_after_cost_usd: float


class TradingHaltIn(BaseModel):
    halt_id: str
    scope: Literal["global", "sleeve", "ticker", "broker"]
    reason_code: str
    reason_detail: str
    trigger_metrics: str
    start_time: datetime
    end_time: datetime | None = None
    cleared_by: str | None = None


class PositionClosedIn(BaseModel):
    position_event_id: str
    signal_id: str
    instrument_key: str
    close_order_intent_id: str
    close_broker_order_id: str
    close_fill_event_ids: list[str] = Field(default_factory=list)
    close_reason: Literal["target_hit", "invalidation", "time_stop", "event_exit", "manual_override"]
    entry_time: datetime
    exit_time: datetime
    qty_closed: float
    avg_entry_price: float
    avg_exit_price: float
    realized_pnl_usd: float
    total_fees_usd: float
    total_commission_usd: float
    realized_pnl_after_costs_usd: float
    mae_usd: float
    mfe_usd: float


class PositionOpenedIn(BaseModel):
    position_event_id: str
    signal_id: str
    ticker: str
    strategy_label: str
    instrument_key: str
    qty_opened: float
    avg_entry_price: float
    open_order_intent_id: str
    open_fill_event_ids: list[str] = Field(default_factory=list)
    opened_at: datetime
    dte: int | None = None
    breakeven: float | None = None
    invalidation_level: float | None = None
    last_price: float | None = None
    unrealized_pnl_usd: float = 0.0


class ExitPlanCreatedIn(BaseModel):
    exit_plan_id: str
    signal_id: str
    instrument_key: str
    exit_time_stop_days: int
    exit_invalidation_level: float
    exit_profit_targets: list[float] = Field(default_factory=list)
    exit_trailing_rule: str | None = None
    event_exit_rule: str | None = None


class StrategyHealthRow(BaseModel):
    strategy_sleeve: str
    regime_label: str
    trading_mode: TradingMode
    trades: int
    win_rate: float
    expectancy_after_costs_usd: float
    avg_win_usd: float
    avg_loss_usd: float
    payoff_ratio: float


class TradeReviewItem(BaseModel):
    decision_id: str
    symbol: str
    strategy_type: str
    direction: str
    created_at: datetime
    closed_at: datetime | None = None
    original_score: float = 0.0
    risk_status: str = "unknown"
    max_loss: float | None = None
    max_profit: float | None = None
    final_pnl: float | None = None
    final_pnl_percent: float | None = None
    max_drawdown: float | None = None
    time_in_trade: str | None = None
    outcome: str | None = None
    lesson: str | None = None
    review_status: str = "pending"
    thesis: str | None = None
    entry_trigger: str | None = None
    invalidation_rule: str | None = None
    profit_plan: str | None = None
    rule_reasons: list[dict[str, Any]] = Field(default_factory=list)
    market_regime: str | None = None
    technical_score: float | None = None
    catalyst_score: float | None = None
    liquidity_score: float | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    entry_trigger_met: bool | None = None
    invalidation_hit: bool | None = None
    profit_target_hit: bool | None = None
    exit_followed_plan: bool | None = None
    # legacy override queue fields
    occurred_at: datetime | None = None
    issue_type: str | None = None
    severity: Literal["low", "medium", "high"] | None = None
    aggregate_id: str | None = None
    message: str | None = None


class UniverseValidationResult(BaseModel):
    ticker: str
    status: Literal["validated", "ambiguous", "invalid"]
    ibkr_conid: str | None = None
    security_type: str | None = "STK"
    primary_exchange: str | None = None
    currency: str | None = "USD"
    ambiguity: dict[str, Any] = Field(default_factory=lambda: {"is_ambiguous": False, "candidates": []})


class UniverseUploadedOut(BaseModel):
    universe_version_id: str
    universe_id: str
    as_of: str
    tickers_requested: list[str]
    upload_status: Literal["validated", "failed"]
    validation_results: list[UniverseValidationResult]
    upload_errors: list[dict[str, str]] = Field(default_factory=list)
    event_id: str


class UniverseActivateIn(BaseModel):
    universe_version_id: str
    universe_id: str
    activated_by: str = "human_trader"


class UniverseActivatedOut(BaseModel):
    universe_version_id: str
    universe_id: str
    activated_at: datetime
    activated_by: str
    event_id: str


class ActiveUniverseResponse(BaseModel):
    universe_version_id: str
    universe_id: str
    as_of: str | None = None
    activated_at: datetime
    tickers: list[str] = Field(default_factory=list)


class UniverseVersionRow(BaseModel):
    universe_version_id: str
    universe_id: str
    as_of: str
    upload_status: Literal["validated", "failed"]
    tickers_requested: list[str] = Field(default_factory=list)
    uploaded_at: datetime


class WatchlistOpportunity(BaseModel):
    ticker: str
    state: TickerState
    data_health: DataHealth
    data_health_reason: str
    regime_label: str
    confidence_total: float
    confidence_components: dict[str, float] = Field(default_factory=dict)
    post_cost_edge_usd: float
    post_cost_edge_pct_of_debit: float
    entry_zone: str
    invalidation: str
    target: str
    hold_period: str
    earnings_warning: bool
    earnings_date: str | None = None
    earnings_certainty: Literal["high", "medium", "low", "unknown"] = "unknown"
    last_snapshot_ts: datetime | None = None
    suggested_strategy: str | None = None
    max_loss: float | None = None
    pop: float | None = None
    liquidity: str = "unknown"
    review_status: str = "pending"
    decision_id: str | None = None
    decision_status: str | None = None
    signal_id: str | None = None
    next_action: Literal[
        "view_trade_card",
        "save_decision",
        "run_replay",
        "run_paper",
        "reject",
        "build_structure",
        "run_risk",
        "request_approval",
        "manage_position",
        "blocked",
    ]


class TradeCardResponse(BaseModel):
    ticker: str
    state: TickerState
    direction: str | None = None
    strategy_type: str | None = None
    risk_status: str | None = None
    data_status: DataStatus = "disconnected"
    broker_status: str = "disconnected"
    reconcile_status: str = "ok"
    decision_id: str | None = None
    last_price: float | None = None
    snapshot_timestamps: dict[str, str] = Field(default_factory=dict)
    thesis: dict[str, Any] = Field(default_factory=dict)
    why_now_deltas: list[str] = Field(default_factory=list)
    decision_summary: dict[str, Any] = Field(default_factory=dict)
    trade_plan: dict[str, Any] = Field(default_factory=dict)
    strategy_legs: list[dict[str, Any]] = Field(default_factory=list)
    confidence_total: float = 0.0
    confidence_components: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    structure_summary: dict[str, Any] | None = None
    risk_summary: dict[str, Any] | None = None
    approval_status: dict[str, Any] | None = None
    position_summary: dict[str, Any] | None = None
    recent_events: list[EventSummary] = Field(default_factory=list)


class PositionRow(BaseModel):
    decision_id: str | None = None
    ticker: str
    strategy_label: str | None = None
    direction: str | None = None
    qty: float
    avg_price: float | None = None
    current_price: float | None = None
    last_price: float | None = None
    pnl_daily: float = 0.0
    pnl_total: float = 0.0
    pnl_percent: float = 0.0
    max_drawdown: float = 0.0
    dte: int | None = None
    breakeven: float | None = None
    entry_trigger: str | None = None
    invalidation_rule: str | None = None
    profit_plan: str | None = None
    current_action: Literal["hold", "take_partial_profit", "close", "watch_invalidation", "review_required"] = "hold"
    alerts: list[str] = Field(default_factory=list)


class PositionsResponse(BaseModel):
    account_id: str
    positions: list[PositionRow] = Field(default_factory=list)


class BlotterRow(BaseModel):
    decision_id: str | None = None
    order_intent_id: str
    ticker: str
    strategy_type: str | None = None
    direction: str | None = None
    structure_label: str | None = None
    legs_summary: list[str] = Field(default_factory=list)
    created_ts: datetime
    submitted_ts: datetime | None = None
    last_update_ts: datetime
    broker_order_ids: list[str] = Field(default_factory=list)
    status: str
    status_timeline: list[str] = Field(default_factory=list)
    fills: list[dict[str, Any]] = Field(default_factory=list)
    fill_price: float | None = None
    fees_usd: float = 0.0
    slippage_vs_expected_usd: float = 0.0
    review_status: str = "pending"
    broker_reject_reason: str | None = None


class ReconcileMismatch(BaseModel):
    mismatch_id: str
    ticker: str | None = None
    severity: Literal["low", "medium", "high"] = "medium"
    reason: str
    blocking: bool
    mismatch_age_seconds: int = 0
    last_broker_truth_ts: datetime | None = None


class StrategyStructureProposedIn(BaseModel):
    structure_id: str
    signal_id: str
    ticker: str
    strategy_label: str = "bull_call_spread"
    legs: list[dict[str, Any]] = Field(default_factory=list)
    net_debit: float
    max_loss_usd: float
    max_gain_usd: float
    breakeven_price: float
    liquidity_score: float = 0.0
    sanity_flags: list[str] = Field(default_factory=list)
    snapshot_refs: dict[str, str] = Field(default_factory=dict)


class DataHealthEvaluatedIn(BaseModel):
    ticker: str
    calendar_session_id: str
    evaluated_at: datetime
    market: dict[str, Any]
    options: dict[str, Any]
    news: dict[str, Any]
    decision: dict[str, Literal["ALLOW", "DEGRADE", "BLOCK"]]


class ReconcileSnapshotIn(BaseModel):
    snapshot_id: str
    broker: str = "IBKR"
    account_id: str
    mismatch_count: int
    blocking: bool
    broker_truth_ts: datetime


class MismatchDetectedIn(BaseModel):
    mismatch_id: str
    ticker: str | None = None
    severity: Literal["low", "medium", "high"] = "medium"
    reason: str
    blocking: bool = True
    broker_truth_ts: datetime | None = None


class BrokerRequestResponseRecordedIn(BaseModel):
    request_id: str
    order_intent_id: str
    broker_route: str = "IBKR"
    request_type: Literal["submit", "replace", "cancel"]
    request_payload_redacted: dict[str, Any] = Field(default_factory=dict)
    response_status_code: int
    response_payload_redacted: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class BrokerOrderEventIn(BaseModel):
    broker_event_id: str
    order_intent_id: str
    broker_order_id: str
    status: Literal["CREATED", "SENT", "ACK", "PARTIAL", "FILLED", "CANCELLED", "REJECTED", "EXPIRED"]
    reason: str | None = None
    event_time: datetime


class FillEventIn(BaseModel):
    fill_event_id: str
    order_intent_id: str
    broker_order_id: str
    qty: float
    price: float
    commission_usd: float = 0.0
    fees_usd: float = 0.0
    occurred_at: datetime


class RiskConfigChangedIn(BaseModel):
    old_value: dict[str, Any]
    new_value: dict[str, Any]
    changed_by: str
    changed_at: datetime
    reason: str


class TradingModeChangedIn(BaseModel):
    old_value: TradingMode
    new_value: TradingMode
    changed_by: str
    changed_at: datetime
    reason: str


class OrderIntentCreatedIn(BaseModel):
    order_intent_id: str
    signal_id: str
    ticker: str
    broker_route: str = "IBKR"
    execution_config_version: str = "exec_cfg_v1"
    trading_mode: TradingMode
    snapshot_refs: dict[str, str]
    underlying_bid_at_decision: float
    underlying_ask_at_decision: float
    underlying_last_at_decision: float
    option_bid_at_decision: float
    option_ask_at_decision: float
    option_mid_at_decision: float
    idempotency_key: str | None = None

    @model_validator(mode="after")
    def validate_snapshot_refs(self) -> "OrderIntentCreatedIn":
        required = {"market_snapshot_ref", "options_snapshot_ref"}
        missing = [k for k in required if k not in self.snapshot_refs]
        if missing:
            raise ValueError(f"snapshot_refs missing required keys: {', '.join(missing)}")
        return self


class StrategyOptionLegIn(BaseModel):
    expiry: str
    dte: int
    option_type: Literal["call", "put"]
    strike: float
    bid: float
    ask: float
    volume: int = 0
    open_interest: int = 0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    iv: float = 0.0


class StrategyBuilderCandidatesIn(BaseModel):
    symbol: str
    direction: Literal["bullish", "bearish"]
    last_price: float
    feature: dict[str, Any] = Field(default_factory=dict)
    option_chain: list[StrategyOptionLegIn] = Field(default_factory=list, min_length=1)
    reconciliation_mismatch_active: bool = False
    thresholds: dict[str, float] = Field(default_factory=dict)


class StrategyCandidateOut(BaseModel):
    symbol: str
    strategy_type: str
    direction: str
    expiry: str
    dte: int
    legs: list[dict[str, Any]] = Field(default_factory=list)
    debit_or_credit: float
    max_profit: float
    max_loss: float
    breakeven: float
    probability_profit: float
    expected_value: float
    alpha_score: float
    beta_score: float
    gamma_score: float
    liquidity_score: float
    strategy_score: float
    risk_status: Literal["allow", "reject", "override_required", "watch_only"]
    rule_reasons: list[dict[str, Any]] = Field(default_factory=list)
    setup_status: Literal["confirmed", "mixed", "conflict"] | None = None
    breakeven_distance_pct: float | None = None


class StrategyBuilderCandidatesOut(BaseModel):
    symbol: str
    direction: Literal["bullish", "bearish"]
    candidates: list[StrategyCandidateOut] = Field(default_factory=list)
    as_of: datetime
    data_status: DataStatus = "live"


class IngestionRunIn(BaseModel):
    tickers: list[str] = Field(default_factory=list, max_length=200)
    include_news: bool = True


class IngestionTickerSummary(BaseModel):
    ticker: str
    market_snapshot_event_id: str
    option_chain_event_id: str
    context_snapshot_event_id: str
    data_status: DataStatus = "live"
    chain_source: Literal["broker", "mock", "none"] = "mock"


class IngestionRunOut(BaseModel):
    run_id: str
    processed: int
    results: list[IngestionTickerSummary] = Field(default_factory=list)
    as_of: datetime
    data_status: DataStatus = "live"


class FeatureBuildIn(BaseModel):
    tickers: list[str] = Field(default_factory=list, max_length=200)


class FeatureRow(BaseModel):
    ticker: str
    feature_event_id: str
    feature: dict[str, Any]


class FeatureBuildOut(BaseModel):
    run_id: str
    built: int
    results: list[FeatureRow] = Field(default_factory=list)
    as_of: datetime
    data_status: DataStatus = "live"


class StrategyRuntimeIn(BaseModel):
    ticker: str
    direction: Literal["bullish", "bearish"]
    reconciliation_mismatch_active: bool = False
    thresholds: dict[str, float] = Field(default_factory=dict)


class StrategyRuntimeOut(BaseModel):
    ticker: str
    direction: Literal["bullish", "bearish"]
    feature_snapshot_ref: str
    option_chain_snapshot_ref: str
    candidates: list[StrategyCandidateOut] = Field(default_factory=list)
    top_recommendations: list[StrategyCandidateOut] = Field(default_factory=list)
    allowed_candidates: list[StrategyCandidateOut] = Field(default_factory=list)
    override_required_candidates: list[StrategyCandidateOut] = Field(default_factory=list)
    watch_only_candidates: list[StrategyCandidateOut] = Field(default_factory=list)
    rejected_candidates: list[StrategyCandidateOut] = Field(default_factory=list)
    setup_status: Literal["confirmed", "mixed", "conflict"] | None = None
    setup_diagnostics: dict[str, Any] = Field(default_factory=dict)
    no_trade: bool = False
    chain_diagnostics: dict[str, Any] = Field(default_factory=dict)
    as_of: datetime
    data_status: DataStatus = "live"
    runtime_allowed: bool = True
    runtime_block_reason: str | None = None
    runtime_warning: str | None = None


class ReplayRunIn(BaseModel):
    ticker: str
    direction: Literal["bullish", "bearish"]
    scenarios: list[float] = Field(default_factory=lambda: [-0.04, -0.02, 0.0, 0.02, 0.04], min_length=1, max_length=25)


class ReplayCandidateResult(BaseModel):
    strategy_type: str
    risk_status: str
    strategy_score: float
    probability_profit: float
    expected_value: float
    replay_avg_pnl: float
    scenario_pnls: list[float] = Field(default_factory=list)


class ReplayRunOut(BaseModel):
    ticker: str
    direction: Literal["bullish", "bearish"]
    scenarios: list[float]
    results: list[ReplayCandidateResult] = Field(default_factory=list)
    as_of: datetime
    data_status: DataStatus = "live"


class PaperTradeRunIn(BaseModel):
    mode: Literal["decision", "quick"] = "decision"
    decision_id: str | None = None
    ticker: str | None = None
    direction: Literal["bullish", "bearish"] | None = None
    scenario_return: float = 0.015


class PaperTradeRunOut(BaseModel):
    mode: Literal["decision", "quick"] = "decision"
    decision_id: str | None = None
    ticker: str
    direction: Literal["bullish", "bearish"]
    signal_id: str
    order_intent_id: str
    position_event_id: str
    close_event_id: str
    entry_price: float
    exit_price: float
    realized_pnl_after_costs_usd: float
    realized_pnl_percent: float = 0.0
    max_drawdown: float = 0.0
    fees_usd: float
    slippage_usd: float
    lifecycle: list[str] = Field(default_factory=list)
    as_of: datetime
    data_status: DataStatus = "live"


class ShellStatusOut(BaseModel):
    as_of: datetime
    broker_connected: bool
    broker_authenticated: bool
    data_status: DataStatus
    execution_mode: ExecutionMode
    trading_mode: TradingMode
    reconcile_worker_status: str
    reconcile_blocking_count: int
    can_open_new_entries: bool
    active_halts: list[str] = Field(default_factory=list)
    runtime_block_reason: str | None = None
    options_chain_scanner_status: str | None = None
    options_chain_default_symbol: str | None = None


class OpsMetricsOut(BaseModel):
    as_of: datetime
    requests: dict[str, int] = Field(default_factory=dict)
    errors: dict[str, int] = Field(default_factory=dict)


class DevFlagsOut(BaseModel):
    as_of: datetime
    runtime_mode: Literal["production", "testing"] = "production"
    allow_stale_runtime_dev: bool = False
    chain_origin: str = "none"
    is_production_valid_chain: bool = False


class RuntimeModeIn(BaseModel):
    mode: Literal["production", "testing"]


class RuntimeModeOut(BaseModel):
    as_of: datetime
    runtime_mode: Literal["production", "testing"]
    allow_stale_runtime_dev: bool
    chain_origin: str = "none"
    is_production_valid_chain: bool = False
    scanner_status: str | None = None
    last_scan_completed_at: datetime | None = None
    next_action: str | None = None
    message: str | None = None


class BrokerStatusOut(BaseModel):
    as_of: datetime
    tws_reachable: bool
    broker_connected: bool
    broker_authenticated: bool
    data_status: DataStatus
    tws_host: str
    tws_port: int
    tws_client_id: int
    tws_read_only: bool
    connection_worker_status: str
    message: str
    next_action: str


class BrokerConnectOut(BaseModel):
    as_of: datetime
    status: Literal["connected", "tws_unreachable", "error"]
    message: str
    next_action: str
    data_status: DataStatus
    ingestion_processed: int = 0
    steps: list[str] = Field(default_factory=list)


DecisionCurrentStatus = Literal[
    "candidate_generated",
    "decision_saved",
    "replayed",
    "paper_order_created",
    "paper_filled",
    "position_open",
    "position_closed",
    "skipped",
    "rejected",
]

DecisionReviewStatus = Literal["pending", "ready_for_review", "reviewed"]

DecisionFinalOutcome = Literal[
    "correct",
    "partially_correct",
    "wrong",
    "invalid_entry",
    "invalid_exit",
    "skipped_trigger_not_met",
    "not_reviewed",
]


class TradeDecisionSaveIn(BaseModel):
    candidate: StrategyCandidateOut
    symbol: str
    direction: Literal["bullish", "bearish"]
    signal_id: str | None = None
    universe: str | None = None
    confidence: float = Field(ge=0.0, le=100.0, default=50.0)
    edge: float = 0.0
    market_regime: str = "unknown"
    thesis: str = ""
    feature: dict[str, Any] = Field(default_factory=dict)
    data_status: DataStatus = "mock"
    broker_status: str = "disconnected"
    reconciliation_status: str = "ok"
    rejected: bool = False


class TradeDecisionPatchIn(BaseModel):
    current_status: DecisionCurrentStatus | None = None
    review_status: DecisionReviewStatus | None = None
    final_outcome: DecisionFinalOutcome | None = None
    lesson: str | None = None
    replay_avg_pnl: float | None = None
    rejected: bool = False


class TradeDecisionOut(BaseModel):
    decision_id: str
    created_at: datetime
    updated_at: datetime
    symbol: str
    universe: str | None = None
    signal_id: str | None = None
    direction: str
    strategy_type: str
    risk_status: str
    confidence: float
    score: float
    edge: float
    market_regime: str | None = None
    technical_score: float | None = None
    catalyst_score: float | None = None
    liquidity_score: float | None = None
    risk_score: float | None = None
    max_loss: float | None = None
    max_profit: float | None = None
    breakeven: float | None = None
    probability_profit: float | None = None
    expected_value: float | None = None
    entry_trigger: str | None = None
    invalidation_rule: str | None = None
    profit_plan: str | None = None
    thesis: str | None = None
    rule_reasons: list[dict[str, Any]] = Field(default_factory=list)
    legs: list[dict[str, Any]] = Field(default_factory=list)
    data_status: DataStatus = "mock"
    broker_status: str = "disconnected"
    reconciliation_status: str = "ok"
    paper_order_id: str | None = None
    paper_position_id: str | None = None
    paper_pnl: float | None = None
    paper_pnl_percent: float | None = None
    max_drawdown: float | None = None
    current_status: DecisionCurrentStatus = "decision_saved"
    review_status: DecisionReviewStatus = "pending"
    final_outcome: DecisionFinalOutcome | None = None
    lesson: str | None = None
    closed_at: datetime | None = None
    replay_avg_pnl: float | None = None


class DashboardDecisionQuality(BaseModel):
    total_decisions_today: int = 0
    paper_trades_opened: int = 0
    open_paper_positions: int = 0
    decisions_ready_for_review: int = 0
    reviewed_decisions: int = 0
    win_rate: float = 0.0
    avg_paper_pnl_percent: float = 0.0
    avg_max_drawdown: float = 0.0
    best_strategy: str = "n/a"
    worst_strategy: str = "n/a"
    most_common_reject_reason: str = "n/a"
    engine_accuracy: float = 0.0


class DashboardSummaryOut(BaseModel):
    as_of: datetime
    decision_quality: DashboardDecisionQuality
    shell: ShellStatusOut | None = None


class EnrichedRecommendation(BaseModel):
    signal_id: str
    ticker: str
    strategy: str
    direction: str
    confidence: float
    edge: float
    max_loss: float | None = None
    max_profit: float | None = None
    pop: float | None = None
    risk_status: str = "unknown"
    decision_status: str = "none"
    decision_id: str | None = None
    regime_label: str = "unknown"
    thesis: str = ""
    entry_trigger: str = "not_ready"
    invalidation_rule: str = "not_ready"
    liquidity_status: str = "unknown"
    reason_preview: list[str] = Field(default_factory=list)


class TradeReviewCompleteIn(BaseModel):
    final_outcome: DecisionFinalOutcome
    lesson: str = ""


class TradeReviewClassifyOut(BaseModel):
    decision_id: str
    final_outcome: DecisionFinalOutcome
    review_status: DecisionReviewStatus


ScannerStatus = Literal["idle", "scanning", "fresh", "stale", "partial", "failed"]


class OptionsChainContractRow(BaseModel):
    expiry: str
    dte: int
    option_type: str
    strike: float
    bid: float
    ask: float
    last: float | None = None
    mid: float
    spread_pct: float
    volume: int
    open_interest: int
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    status: str
    rejection_reason: str | None = None


class OptionsChainScanStatusOut(BaseModel):
    symbol: str
    scanner_status: ScannerStatus
    chain_source: str
    last_scan_started_at: datetime | None = None
    last_scan_completed_at: datetime | None = None
    last_error: str | None = None
    expiries_selected: list[str] = Field(default_factory=list)
    strike_low: float | None = None
    strike_high: float | None = None
    underlying_price: float | None = None
    contracts_scanned: int = 0
    contracts_rejected: int = 0
    contracts_usable: int = 0


class OptionsChainSnapshotOut(BaseModel):
    as_of: datetime
    symbol: str
    data_status: DataStatus
    scanner_status: ScannerStatus
    chain_source: str
    last_scan_completed_at: datetime | None = None
    expiries_selected: list[str] = Field(default_factory=list)
    strike_low: float | None = None
    strike_high: float | None = None
    underlying_price: float | None = None
    contracts_scanned: int = 0
    contracts_rejected: int = 0
    contracts_usable: int = 0
    contracts_planned: int = 0
    scan_notes: list[str] = Field(default_factory=list)
    last_error: str | None = None
    chain_origin: str = "none"
    runtime_mode: Literal["production", "testing"] = "production"
    is_production_valid_chain: bool = False
    allow_stale_runtime_dev: bool = False
    contracts: list[OptionsChainContractRow] = Field(default_factory=list)


class OptionsChainRefreshOut(BaseModel):
    as_of: datetime
    symbol: str
    enqueued: bool
    scanner_status: ScannerStatus
    message: str

