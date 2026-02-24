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
  category: "data" | "news" | "signal" | "structure" | "risk" | "approval" | "execution" | "reconcile" | "system";
  step: string;
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
  occurred_at: string;
  issue_type: string;
  severity: "low" | "medium" | "high";
  aggregate_id: string;
  message: string;
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
  next_action: "view_trade_card" | "build_structure" | "run_risk" | "request_approval" | "manage_position" | "blocked";
};

export type TradeCard = {
  ticker: string;
  state: WatchlistOpportunity["state"];
  last_price?: number | null;
  snapshot_timestamps: Record<string, string>;
  thesis: Record<string, unknown>;
  why_now_deltas: string[];
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
  ticker: string;
  strategy_label?: string | null;
  qty: number;
  avg_price?: number | null;
  last_price?: number | null;
  pnl_daily: number;
  pnl_total: number;
  dte?: number | null;
  breakeven?: number | null;
  alerts: string[];
};

export type PositionsResponse = {
  account_id: string;
  positions: PositionRow[];
};

export type BlotterRow = {
  order_intent_id: string;
  ticker: string;
  structure_label?: string | null;
  legs_summary: string[];
  created_ts: string;
  submitted_ts?: string | null;
  last_update_ts: string;
  broker_order_ids: string[];
  status: string;
  status_timeline: string[];
  fills: Array<Record<string, unknown>>;
  fees_usd: number;
  slippage_vs_expected_usd: number;
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


