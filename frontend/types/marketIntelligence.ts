export interface MicHeader {
  last_updated: string | null;
  api_status: string;
}

export interface MicSummary {
  overall_sentiment: string;
  news_score_0_to_100: number;
  critical_events_count: number;
  high_impact_events_count: number;
  upcoming_earnings_count: number;
  api_health: string;
  bullish_count?: number;
  bearish_count?: number;
  neutral_count?: number;
}

export interface MicRegimeContext {
  available: boolean;
  message?: string;
  current_regime?: string;
  regime_score?: number;
  risk_level?: string;
  preferred_strategy?: string;
  next_major_catalyst?: string;
  next_catalyst_countdown_days?: number;
  volatility_regime?: string;
}

export interface MicWatchlistRow {
  enabled: boolean;
  priority: number;
  symbol: string;
  company: string;
  sector: string;
  last_news_time: string | null;
  news_score: number;
  sentiment: string;
  next_earnings: string | null;
  refresh_status: string;
}

export interface MicCriticalEvent {
  symbol: string;
  eventType: string;
  title: string;
  source: string;
  sentiment: string;
  importance: string;
  impactScore: number;
  publishedAt: string | null;
  relatedSymbols?: string[];
}

export interface MicCatalystRow {
  event: string;
  symbol: string;
  date: string | null;
  time: string;
  expected_impact: string;
  risk_level: string;
  countdown_days: number | null;
  source: string;
}

export interface MicSecFiling {
  symbol: string;
  form: string;
  filed_date: string | null;
  description: string;
  importance: string;
  link: string;
  impact_score: number;
}

export interface MicSentimentAnalytics {
  split: { bullish: number; bearish: number; neutral: number };
  trend: Array<{ date: string; bullish: number; bearish: number; neutral: number }>;
  most_positive: Array<{ symbol: string; avg_sentiment: number }>;
  most_negative: Array<{ symbol: string; avg_sentiment: number }>;
}

export interface MicApiBudget {
  finnhub: { used: number; limit: number };
  alpha_vantage: { used: number; limit: number };
  sec: { used: number; limit: number };
  planned_calls: number;
  skipped_calls: number;
  skip_reasons: string[];
}

export interface IbkrNewsStatus {
  available: boolean;
  message: string;
  providers_detected?: string[];
  cache_status?: { total_entries: number; valid_entries: number; expired_entries: number };
  last_fetch?: string | null;
  errors?: string[];
}

export interface MicActivityRow {
  timestamp: string | null;
  mode: string;
  provider: string;
  calls_planned: number | null;
  calls_executed: number;
  calls_skipped: number;
  items_saved: number;
  errors: string | null;
  status: string;
  request_type?: string;
  items_fetched?: number;
}

export interface MicSignalRow {
  symbol: string;
  label: string;
  news_score_0_to_100: number;
  sentiment_score: number;
  impact_score: number;
  confidence: string;
  top_catalyst: string | null;
  top_risk_event?: string | null;
  critical_event_count: number;
  last_updated: string | null;
  data_freshness_minutes?: number | null;
}

export interface MicNewsSignalOutput {
  primary: MicSignalRow;
  watchlist_signals: MicSignalRow[];
  consumers: string[];
}

export interface MicTickerSignal {
  symbol: string;
  news_bias: "Bullish" | "Bearish" | "Neutral" | string;
  news_quality_score: number;
  catalyst_strength_score: number;
  net_impact_score: number;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  top_catalyst: string | null;
  top_risk: string | null;
  llm_summary: string | null;
  confidence: "High" | "Medium" | "Low" | string;
  last_updated: string | null;
}

export interface MarketIntelligenceDashboard {
  timestamp: string;
  header: MicHeader;
  summary: MicSummary;
  regime_context: MicRegimeContext;
  watchlist: MicWatchlistRow[];
  critical_events: MicCriticalEvent[];
  catalyst_calendar: MicCatalystRow[];
  sec_filings: MicSecFiling[];
  sentiment_analytics: MicSentimentAnalytics;
  api_budget: MicApiBudget;
  ibkr_news_status?: IbkrNewsStatus;
  activity_log: MicActivityRow[];
  news_signal_output: MicNewsSignalOutput;
  comments: string[];
  refresh_result?: Record<string, unknown>;
}

export type RefreshMode = "quick" | "standard" | "deep";
