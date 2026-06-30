export type Recommendation = {
  signal_id: string;
  ticker: string;
  strategy_sleeve: string;
  side: "bullish" | "bearish" | "neutral";
  trading_mode: "paper" | "micro_live" | "normal_live";
  confidence_total: number;
  regime_label: string;
  thesis: string;
  entry_zone: string;
  invalidation: string;
  targets: string[];
  data_sources_used: string[];
  quote_type: "real_time" | "delayed" | "snapshot";
  expected_edge_after_cost_usd: number;
};

export type RiskStatus = {
  trading_mode: "paper" | "micro_live" | "normal_live";
  drawdown_pct: number;
  worst_case_stress_loss_nav_pct: number;
  can_open_new_entries: boolean;
  active_halts: string[];
};

export type EventSummary = {
  event_id: string;
  event_type: string;
  occurred_at: string;
  aggregate_type: string;
  aggregate_id: string;
  details: Record<string, unknown>;
};

export type ExplainFeedItem = {
  event_id: string;
  correlation_id?: string | null;
  ts: string;
  ticker?: string | null;
  severity: "info" | "warn" | "block";
  category:
    | "data"
    | "news"
    | "signal"
    | "structure"
    | "risk"
    | "approval"
    | "execution"
    | "reconcile"
    | "broker"
    | "paper"
    | "review"
    | "system";
  step: string;
  human_message?: string;
  event_type?: string;
  scope?: "global" | "ticker" | "decision" | "risk" | "broker" | "paper" | "review";
  linked_decision_id?: string | null;
  refs: Record<string, unknown>;
};

export type StrategyHealthRow = {
  strategy_sleeve: string;
  regime_label: string;
  trading_mode: "paper" | "micro_live" | "normal_live";
  trades: number;
  win_rate: number;
  expectancy_after_costs_usd: number;
  avg_win_usd: number;
  avg_loss_usd: number;
  payoff_ratio: number;
};

export type TradeReviewItem = {
  decision_id: string;
  symbol: string;
  strategy_type: string;
  direction: string;
  created_at: string;
  closed_at?: string | null;
  original_score?: number;
  risk_status?: string;
  max_loss?: number | null;
  max_profit?: number | null;
  final_pnl?: number | null;
  final_pnl_percent?: number | null;
  max_drawdown?: number | null;
  time_in_trade?: string | null;
  outcome?: string | null;
  lesson?: string | null;
  review_status?: string;
  thesis?: string | null;
  entry_trigger?: string | null;
  invalidation_rule?: string | null;
  profit_plan?: string | null;
  rule_reasons?: Array<Record<string, unknown>>;
  market_regime?: string | null;
  technical_score?: number | null;
  catalyst_score?: number | null;
  liquidity_score?: number | null;
  entry_price?: number | null;
  exit_price?: number | null;
  entry_trigger_met?: boolean | null;
  invalidation_hit?: boolean | null;
  profit_target_hit?: boolean | null;
  exit_followed_plan?: boolean | null;
  occurred_at?: string;
  issue_type?: string;
  severity?: "low" | "medium" | "high";
  aggregate_id?: string;
  message?: string;
};

export type UniverseValidationResult = {
  ticker: string;
  status: "validated" | "ambiguous" | "invalid";
  ibkr_conid?: string | null;
  security_type?: string | null;
  primary_exchange?: string | null;
  currency?: string | null;
  ambiguity: {
    is_ambiguous: boolean;
    candidates: Array<{ display: string; conid: string; exchange: string }>;
  };
};

export type UniverseUploadResponse = {
  universe_version_id: string;
  universe_id: string;
  as_of: string;
  tickers_requested: string[];
  upload_status: "validated" | "failed";
  validation_results: UniverseValidationResult[];
  upload_errors: Array<{ code: string; detail: string }>;
  event_id: string;
};

export type UniverseVersionRow = {
  universe_version_id: string;
  universe_id: string;
  as_of: string;
  upload_status: "validated" | "failed";
  tickers_requested: string[];
  uploaded_at: string;
};

export type ActiveUniverse = {
  universe_version_id: string;
  universe_id: string;
  as_of?: string | null;
  activated_at: string;
  tickers: string[];
};

export type WatchlistOpportunity = {
  ticker: string;
  state:
    | "NoSignal"
    | "CandidateSignal"
    | "StructureProposed"
    | "RiskApproved"
    | "AwaitingApproval"
    | "OrderIntent"
    | "Executed"
    | "Reconciled"
    | "PositionOpen"
    | "PositionClosed"
    | "Reviewed";
  data_health: "OK" | "Degraded" | "Blocked";
  data_health_reason: string;
  regime_label: string;
  confidence_total: number;
  confidence_components: Record<string, number>;
  post_cost_edge_usd: number;
  post_cost_edge_pct_of_debit: number;
  entry_zone: string;
  invalidation: string;
  target: string;
  hold_period: string;
  earnings_warning: boolean;
  earnings_date?: string | null;
  earnings_certainty: "high" | "medium" | "low" | "unknown";
  last_snapshot_ts?: string | null;
  suggested_strategy?: string | null;
  max_loss?: number | null;
  pop?: number | null;
  liquidity?: string;
  review_status?: string;
  decision_id?: string | null;
  decision_status?: string | null;
  signal_id?: string | null;
  next_action:
    | "view_trade_card"
    | "save_decision"
    | "run_replay"
    | "run_paper"
    | "reject"
    | "build_structure"
    | "run_risk"
    | "request_approval"
    | "manage_position"
    | "blocked";
};

export type TradeCard = {
  ticker: string;
  state: WatchlistOpportunity["state"];
  direction?: string | null;
  strategy_type?: string | null;
  risk_status?: string | null;
  data_status?: DataStatus;
  broker_status?: string;
  reconcile_status?: string;
  decision_id?: string | null;
  last_price?: number | null;
  snapshot_timestamps: Record<string, string>;
  thesis: Record<string, unknown>;
  why_now_deltas: string[];
  decision_summary?: Record<string, unknown>;
  trade_plan?: Record<string, unknown>;
  strategy_legs?: Array<Record<string, unknown>>;
  confidence_total: number;
  confidence_components: Record<string, number>;
  warnings: string[];
  structure_summary?: Record<string, unknown> | null;
  risk_summary?: Record<string, unknown> | null;
  approval_status?: Record<string, unknown> | null;
  position_summary?: Record<string, unknown> | null;
  recent_events: EventSummary[];
};

export type PositionRow = {
  decision_id?: string | null;
  ticker: string;
  strategy_label?: string | null;
  direction?: string | null;
  qty: number;
  avg_price?: number | null;
  current_price?: number | null;
  last_price?: number | null;
  pnl_daily: number;
  pnl_total: number;
  pnl_percent?: number;
  max_drawdown?: number;
  dte?: number | null;
  breakeven?: number | null;
  entry_trigger?: string | null;
  invalidation_rule?: string | null;
  profit_plan?: string | null;
  current_action?: "hold" | "take_partial_profit" | "close" | "watch_invalidation" | "review_required";
  alerts: string[];
};

export type PositionsResponse = {
  account_id: string;
  positions: PositionRow[];
};

export type BlotterRow = {
  decision_id?: string | null;
  order_intent_id: string;
  ticker: string;
  strategy_type?: string | null;
  direction?: string | null;
  structure_label?: string | null;
  legs_summary: string[];
  created_ts: string;
  submitted_ts?: string | null;
  last_update_ts: string;
  broker_order_ids: string[];
  status: string;
  status_timeline: string[];
  fills: Array<Record<string, unknown>>;
  fill_price?: number | null;
  fees_usd: number;
  slippage_vs_expected_usd: number;
  review_status?: string;
  broker_reject_reason?: string | null;
};

export type ReconcileMismatch = {
  mismatch_id: string;
  ticker?: string | null;
  severity: "low" | "medium" | "high";
  reason: string;
  blocking: boolean;
  mismatch_age_seconds: number;
  last_broker_truth_ts?: string | null;
};

export type StrategyOptionLegIn = {
  expiry: string;
  dte: number;
  option_type: "call" | "put";
  strike: number;
  bid: number;
  ask: number;
  volume?: number;
  open_interest?: number;
  delta?: number;
  gamma?: number;
  theta?: number;
  vega?: number;
  iv?: number;
};

export type StrategyRuleReason = {
  rule_id: string;
  message: string;
  severity: string;
};

export type StrategyCandidateOut = {
  symbol: string;
  strategy_type: string;
  direction: "bullish" | "bearish";
  expiry: string;
  dte: number;
  legs: Array<{ action: string; option_type: string; strike: number; qty: number }>;
  debit_or_credit: number;
  max_profit: number;
  max_loss: number;
  breakeven: number;
  probability_profit: number;
  expected_value: number;
  alpha_score: number;
  beta_score: number;
  gamma_score: number;
  liquidity_score: number;
  strategy_score: number;
  risk_status: "allow" | "reject" | "override_required" | "watch_only";
  rule_reasons: StrategyRuleReason[];
  setup_status?: "confirmed" | "mixed" | "conflict" | null;
  breakeven_distance_pct?: number | null;
};

export type StrategyBuilderCandidatesIn = {
  symbol: string;
  direction: "bullish" | "bearish";
  last_price: number;
  feature?: Record<string, number>;
  option_chain: StrategyOptionLegIn[];
  reconciliation_mismatch_active?: boolean;
  thresholds?: Record<string, number>;
};

export type DataStatus = "live" | "stale" | "mock" | "degraded" | "disconnected";
export type ExecutionMode = "paper_only" | "read_only" | "manual_approval" | "close_only" | "halted";

export type BrokerStatus = {
  as_of: string;
  tws_reachable: boolean;
  broker_connected: boolean;
  broker_authenticated: boolean;
  data_status: DataStatus;
  tws_host: string;
  tws_port: number;
  tws_client_id: number;
  tws_read_only: boolean;
  connection_worker_status: string;
  message: string;
  next_action: string;
};

export type BrokerConnectResult = {
  as_of: string;
  status: "connected" | "tws_unreachable" | "error";
  message: string;
  next_action: string;
  data_status: DataStatus;
  ingestion_processed: number;
  steps: string[];
};

export type ShellStatus = {
  as_of: string;
  broker_connected: boolean;
  broker_authenticated: boolean;
  data_status: DataStatus;
  execution_mode: ExecutionMode;
  trading_mode: RiskStatus["trading_mode"];
  reconcile_worker_status: string;
  reconcile_blocking_count: number;
  can_open_new_entries: boolean;
  active_halts: string[];
  runtime_block_reason?: string | null;
};

export type StrategyBuilderCandidatesOut = {
  symbol: string;
  direction: "bullish" | "bearish";
  candidates: StrategyCandidateOut[];
  as_of: string;
  data_status: DataStatus;
};

export type StrategyRuntimeOut = {
  ticker: string;
  direction: "bullish" | "bearish";
  feature_snapshot_ref: string;
  option_chain_snapshot_ref: string;
  candidates: StrategyCandidateOut[];
  top_recommendations?: StrategyCandidateOut[];
  allowed_candidates?: StrategyCandidateOut[];
  override_required_candidates?: StrategyCandidateOut[];
  watch_only_candidates?: StrategyCandidateOut[];
  rejected_candidates?: StrategyCandidateOut[];
  setup_status?: "confirmed" | "mixed" | "conflict" | null;
  setup_diagnostics?: Record<string, unknown>;
  no_trade?: boolean;
  chain_diagnostics?: Record<string, unknown>;
  as_of: string;
  data_status: DataStatus;
  runtime_allowed: boolean;
  runtime_block_reason?: string | null;
  runtime_warning?: string | null;
};

export type ScannerStatus = "idle" | "scanning" | "fresh" | "stale" | "partial" | "failed";

export type OptionsChainContractRow = {
  expiry: string;
  dte: number;
  option_type: string;
  strike: number;
  bid: number;
  ask: number;
  last?: number | null;
  mid: number;
  spread_pct: number;
  volume: number;
  open_interest: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  status: string;
  rejection_reason?: string | null;
};

export type OptionsChainSnapshotOut = {
  as_of: string;
  symbol: string;
  data_status: DataStatus;
  scanner_status: ScannerStatus;
  chain_source: string;
  last_scan_completed_at?: string | null;
  expiries_selected: string[];
  strike_low?: number | null;
  strike_high?: number | null;
  underlying_price?: number | null;
  contracts_scanned: number;
  contracts_rejected: number;
  contracts_usable: number;
  contracts_planned: number;
  scan_notes: string[];
  last_error?: string | null;
  chain_origin?: string;
  runtime_mode?: "production" | "testing";
  is_production_valid_chain?: boolean;
  allow_stale_runtime_dev?: boolean;
  contracts: OptionsChainContractRow[];
};

export type RuntimeMode = "production" | "testing";

export type RuntimeModeOut = {
  as_of: string;
  runtime_mode: RuntimeMode;
  allow_stale_runtime_dev: boolean;
  chain_origin: string;
  is_production_valid_chain: boolean;
  scanner_status?: string | null;
  last_scan_completed_at?: string | null;
  next_action?: string | null;
  message?: string | null;
};

export type DevFlagsOut = {
  as_of: string;
  runtime_mode?: RuntimeMode;
  allow_stale_runtime_dev: boolean;
  chain_origin?: string;
  is_production_valid_chain?: boolean;
};

export type OptionsChainRefreshOut = {
  as_of: string;
  symbol: string;
  enqueued: boolean;
  scanner_status: ScannerStatus;
  message: string;
};

export type ReplayCandidateResult = {
  strategy_type: string;
  risk_status: string;
  strategy_score: number;
  probability_profit: number;
  expected_value: number;
  replay_avg_pnl: number;
  scenario_pnls: number[];
};

export type ReplayRunOut = {
  ticker: string;
  direction: "bullish" | "bearish";
  scenarios: number[];
  results: ReplayCandidateResult[];
  as_of: string;
  data_status: DataStatus;
};

export type PaperTradeRunOut = {
  mode?: "decision" | "quick";
  decision_id?: string | null;
  ticker: string;
  direction: "bullish" | "bearish";
  signal_id: string;
  order_intent_id: string;
  position_event_id: string;
  close_event_id: string;
  entry_price: number;
  exit_price: number;
  realized_pnl_after_costs_usd: number;
  realized_pnl_percent?: number;
  max_drawdown?: number;
  fees_usd: number;
  slippage_usd: number;
  lifecycle?: string[];
  as_of: string;
  data_status: DataStatus;
};

export type DecisionCurrentStatus =
  | "candidate_generated"
  | "decision_saved"
  | "replayed"
  | "paper_order_created"
  | "paper_filled"
  | "position_open"
  | "position_closed"
  | "skipped"
  | "rejected";

export type DecisionReviewStatus = "pending" | "ready_for_review" | "reviewed";

export type DecisionFinalOutcome =
  | "correct"
  | "partially_correct"
  | "wrong"
  | "invalid_entry"
  | "invalid_exit"
  | "skipped_trigger_not_met"
  | "not_reviewed";

export type TradeDecision = {
  decision_id: string;
  created_at: string;
  updated_at: string;
  symbol: string;
  universe?: string | null;
  signal_id?: string | null;
  direction: string;
  strategy_type: string;
  risk_status: string;
  confidence: number;
  score: number;
  edge: number;
  market_regime?: string | null;
  technical_score?: number | null;
  catalyst_score?: number | null;
  liquidity_score?: number | null;
  risk_score?: number | null;
  max_loss?: number | null;
  max_profit?: number | null;
  breakeven?: number | null;
  probability_profit?: number | null;
  expected_value?: number | null;
  entry_trigger?: string | null;
  invalidation_rule?: string | null;
  profit_plan?: string | null;
  thesis?: string | null;
  rule_reasons: Array<Record<string, unknown>>;
  legs: Array<Record<string, unknown>>;
  data_status: DataStatus;
  broker_status: string;
  reconciliation_status: string;
  paper_order_id?: string | null;
  paper_position_id?: string | null;
  paper_pnl?: number | null;
  paper_pnl_percent?: number | null;
  max_drawdown?: number | null;
  current_status: DecisionCurrentStatus;
  review_status: DecisionReviewStatus;
  final_outcome?: DecisionFinalOutcome | null;
  lesson?: string | null;
  closed_at?: string | null;
  replay_avg_pnl?: number | null;
};

export type DashboardDecisionQuality = {
  total_decisions_today: number;
  paper_trades_opened: number;
  open_paper_positions: number;
  decisions_ready_for_review: number;
  reviewed_decisions: number;
  win_rate: number;
  avg_paper_pnl_percent: number;
  avg_max_drawdown: number;
  best_strategy: string;
  worst_strategy: string;
  most_common_reject_reason: string;
  engine_accuracy: number;
};

export type DashboardSummary = {
  as_of: string;
  decision_quality: DashboardDecisionQuality;
  shell?: ShellStatus | null;
};

export type EnrichedRecommendation = {
  signal_id: string;
  ticker: string;
  strategy: string;
  direction: string;
  confidence: number;
  edge: number;
  max_loss?: number | null;
  max_profit?: number | null;
  pop?: number | null;
  risk_status: string;
  decision_status: string;
  decision_id?: string | null;
  regime_label: string;
  thesis: string;
  entry_trigger: string;
  invalidation_rule: string;
  liquidity_status: string;
  reason_preview: string[];
};

