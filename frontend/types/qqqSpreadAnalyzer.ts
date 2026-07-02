export type QqqBias = "Bullish" | "Bearish" | "Neutral";
export type QqqConfidence = "High" | "Medium" | "Low";

export interface QqqLevelRow {
  price: number;
  kind: string;
  side: string;
  distance_abs: number;
  distance_pct: number;
}

export interface QqqOptionQuote {
  expiry: string;
  dte: number;
  option_type: "call" | "put";
  strike: number;
  bid: number;
  ask: number;
  last: number;
  mid: number;
  spread_pct: number;
  volume: number;
  open_interest: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  iv: number;
  liquid: boolean;
}

export interface QqqSpreadCandidate {
  strategy: string;
  spread_type: string;
  expiry: string;
  dte: number;
  long_leg: string;
  short_leg: string;
  buy_strike: number;
  sell_strike: number;
  net_debit: number;
  max_loss: number;
  max_profit: number;
  breakeven: number;
  reward_risk: number;
  probability_of_profit: number | null;
  combined_delta: number;
  combined_gamma: number;
  combined_theta: number;
  combined_vega: number;
  bid_ask_quality: number;
  open_interest: number | null;
  volume: number | null;
  liquidity_score: number;
  status: string;
  rejection_reason: string | null;
}

export interface QqqQualificationFailure {
  expiry: string;
  failed_count: number;
  reason_hint: string;
}

export interface QqqDiagnostics {
  ib_connected?: boolean;
  ib_host?: string;
  ib_port?: number;
  ib_client_id?: number;
  daily_bars?: number;
  intraday_bars?: number;
  intraday_timeframe?: string;
  liquid_quotes?: number;
  spread_candidates_count?: number;
  contracts_planned?: number;
  contracts_qualified?: number;
  raw_quotes?: number;
  ib_error_200_count?: number;
  qualification_failures?: QqqQualificationFailure[];
  cache_status?: { daily?: boolean; intraday?: boolean };
}

export interface QqqIndicatorSnapshot {
  close: number;
  ema20?: number | null;
  ema50?: number | null;
  sma200?: number | null;
  rsi14?: number | null;
  macd_line?: number | null;
  macd_signal?: number | null;
  macd_hist?: number | null;
  atr14?: number | null;
  bb_upper?: number | null;
  bb_mid?: number | null;
  bb_lower?: number | null;
  ema9?: number | null;
  ema21?: number | null;
  macd_expanding?: boolean;
  macd_weakening?: boolean;
}

export interface QqqSpreadAnalysis {
  timestamp: string;
  symbol: string;
  underlying_price: number;
  bias: QqqBias;
  confidence: QqqConfidence;
  suggested_action: string;
  action: string;
  bullish_score: number;
  bearish_score: number;
  reason_summary: string;
  score: {
    bullish_score: number;
    bearish_score: number;
    intraday_timing_bull: number;
    intraday_timing_bear: number;
    bias: QqqBias;
    confidence: QqqConfidence;
    action: string;
    invalid_conditions: string[];
    daily_checks: Record<string, boolean>;
    intraday_checks: Record<string, boolean>;
  };
  daily_indicators: QqqIndicatorSnapshot;
  intraday_indicators: QqqIndicatorSnapshot;
  support_levels: QqqLevelRow[];
  resistance_levels: QqqLevelRow[];
  spread_candidates: QqqSpreadCandidate[];
  liquid_options?: QqqOptionQuote[];
  raw_options?: QqqOptionQuote[];
  risk_notes: string[];
  positions_count: number;
  open_orders_count: number;
  backtest: { available: boolean; message: string };
  diagnostics: QqqDiagnostics;
}

export interface QqqSpreadRunOut {
  job_id: string;
  status: "queued" | "running" | "done" | "failed";
  started_at: string;
  message: string;
}

export interface QqqSpreadRunStatusOut {
  job_id: string;
  status: "queued" | "running" | "done" | "failed";
  started_at: string;
  finished_at?: string | null;
  exit_code?: number | null;
  error?: string | null;
  symbol: string;
}
