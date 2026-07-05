export type DirectionCandidate = "Bullish" | "Bearish" | "Neutral" | "Mixed";

export type TradeReadiness = "Ready" | "Needs Analyze Live" | "Blocked";

export interface OpportunityReasonDetail {
  summary?: string;
  bullets?: string[];
  bull_evidence?: string[];
  bear_evidence?: string[];
  risk_factors?: string[];
  news_summary?: string;
  technical_summary?: string;
  liquidity_summary?: string;
  regime_context?: string;
  relative_strength_summary?: string;
  data_availability?: {
    analyzer_snapshot?: boolean;
    options_data?: boolean;
    news_data?: boolean;
  };
  sector?: string;
  risk_score?: number;
}

export interface OpportunityScanRow {
  rank: number;
  symbol: string;
  company?: string;
  sector?: string;
  priority?: number;
  direction_candidate: DirectionCandidate;
  market_opportunity_score: number;
  opportunity_score: number;
  bull_score: number;
  bear_score: number;
  confidence_score: number;
  risk_score: number;
  news_score: number;
  news_quality_score?: number;
  catalyst_strength_score?: number;
  technical_score: number;
  technical_confidence?: string;
  technical_hint?: string | null;
  trade_readiness?: TradeReadiness | string;
  liquidity_score: number;
  market_regime_score?: number;
  relative_strength_score?: number;
  paper_feedback_score?: number;
  next_earnings?: string | null;
  top_catalyst?: string | null;
  top_risk?: string | null;
  market_context?: string | null;
  reason: string;
  reason_json?: OpportunityReasonDetail;
  data_quality?: string;
  has_analyzer_snapshot?: boolean;
  has_options_data?: boolean;
  has_news_data?: boolean;
  last_analyzed_at?: string | null;
  snapshot_age_minutes?: number | null;
}

export interface OpportunityScannerPayload {
  timestamp: string;
  header: {
    last_updated: string;
    symbols_scanned: number;
    data_freshness: string;
    news_provider_error?: boolean;
  };
  summary: {
    best_bullish: OpportunityScanRow | null;
    best_bearish: OpportunityScanRow | null;
    highest_opportunity: OpportunityScanRow | null;
    highest_risk: OpportunityScanRow | null;
    symbols_scanned: number;
    data_quality: string;
    bullish_count: number;
    bearish_count: number;
    neutral_count: number;
  };
  results: OpportunityScanRow[];
  empty_message?: string;
  disclaimer: string;
}

export interface OpportunityFiltersState {
  direction: "All" | DirectionCandidate;
  minOpportunity: number;
  maxRisk: number;
  sector: string;
  maxPriority: number;
  hasNews: boolean | null;
  hasOptions: boolean | null;
  hideStale: boolean;
}

export const DEFAULT_OPPORTUNITY_FILTERS: OpportunityFiltersState = {
  direction: "All",
  minOpportunity: 0,
  maxRisk: 100,
  sector: "All",
  maxPriority: 99,
  hasNews: null,
  hasOptions: null,
  hideStale: false,
};
