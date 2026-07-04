export type RegimeName =
  | "Strong Bull Trend"
  | "Bull Trend"
  | "Bull Pullback"
  | "Sideways Range"
  | "High Volatility Range"
  | "Bear Rally"
  | "Bear Trend"
  | "Strong Bear Trend";

export interface MarketRegimeSummary {
  regime_name: RegimeName | string;
  regime_score: number;
  confidence: "High" | "Medium" | "Low";
  risk_level: "Low" | "Medium" | "High" | "Extreme";
  preferred_strategy: string;
}

export interface InstrumentCard {
  symbol: string;
  price: number | null;
  daily_pct: number | null;
  trend_badge: string;
  risk_badge: string;
  available: boolean;
}

export interface ScoreBreakdown {
  trend_score: number;
  momentum_score: number;
  volatility_score: number;
  breadth_score: number;
  macro_score: number;
  news_catalyst_score: number;
  final_score: number;
  regime_score: number;
  weights: Record<string, number>;
}

export interface TimeframeCard {
  timeframe: string;
  available: boolean;
  close?: number | null;
  ema20?: number | null;
  ema50?: number | null;
  sma200?: number | null;
  rsi14?: number | null;
  macd_line?: number | null;
  macd_signal?: number | null;
  macd_hist?: number | null;
  atr14?: number | null;
  trend_label?: string;
  signal_label?: string;
  note?: string;
}

export interface BreadthData {
  rows: Array<{ symbol: string; above_ema20: boolean | null; close?: number; ema20?: number }>;
  qqq_above_ema20: boolean | null;
  spy_above_ema20: boolean | null;
  iwm_above_ema20: boolean | null;
  dia_above_ema20: boolean | null;
  smh_soxx_confirming: boolean;
  bullish_count: number;
  bearish_count: number;
  breadth_score: number;
  heatmap: Array<{ symbol: string; state: "bull" | "bear" | "na" }>;
}

export interface VolatilityPanel {
  vix_level: number | null;
  vix_daily_change_pct: number | null;
  atr_trend: string;
  bollinger_width_pct: number | null;
  iv_rank: number | null;
  iv_percentile: number | null;
  volatility_regime: string;
  volatility_score: number;
  risk_level: string;
}

export interface MacroPanel {
  ten_year_yield: number | null;
  two_year_yield: number | null;
  yield_curve_10y_minus_2y: number | null;
  dxy: number | null;
  fed_funds_rate: number | null;
  next_cpi_date: string;
  next_fomc_date: string;
  next_jobs_report_date: string;
  macro_score: number;
  available: boolean;
  source: string;
}

export interface StrategyMatrixRow {
  regime: string;
  bull_call: string;
  bear_put: string;
  bull_put: string;
  bear_call: string;
  iron_condor: string;
  wait: string;
  notes: string;
}

export interface CatalystEvent {
  event: string;
  date: string;
  time: string;
  expected_impact: string;
  risk_level: string;
  countdown_days: number;
}

export interface HistoryPoint {
  timestamp: string;
  regime_score: number;
  confidence: string;
  risk_level: string;
  regime_name: string;
}

export interface AISummary {
  current_regime: string;
  why_changed: string;
  confirms: string[];
  contradicts: string[];
  preferred_strategies: string[];
  avoid_strategies: string[];
  key_levels_events: string[];
  narrative: string;
}

export interface MarketRegimeDashboard {
  timestamp: string;
  data_source: { ibkr: string; analyzer: string; macro: string };
  summary: MarketRegimeSummary;
  instruments: InstrumentCard[];
  score_breakdown: ScoreBreakdown;
  multi_timeframe: TimeframeCard[];
  breadth: BreadthData;
  volatility: VolatilityPanel;
  macro: MacroPanel;
  strategy_matrix: StrategyMatrixRow[];
  strategy_matrix_highlight: StrategyMatrixRow[];
  catalysts: CatalystEvent[];
  ai_summary: AISummary;
  market_regime: {
    regime_score: number;
    regime_name: string;
    confidence: string;
    preferred_strategy: string;
    risk_level: string;
  };
}
