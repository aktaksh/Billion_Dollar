export type NewsSignalLabel = "Bullish" | "Bearish" | "Neutral" | "Unavailable";

export type ProviderStatus = "Online" | "Partial" | "Error";

export interface NewsSignalDto {
  symbol: string;
  label: NewsSignalLabel;
  news_score_0_to_100: number;
  sentiment_score: number;
  impact_score: number;
  confidence: string;
  top_catalyst: string | null;
  last_updated: string | null;
  data_freshness_minutes: number | null;
  provider_status: ProviderStatus;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
}

export interface NewsTopEvent {
  symbol: string;
  eventType: string;
  title: string;
  source: string;
  sentiment: string;
  importance: string;
  impactScore: number;
  publishedAt: string | null;
}

export interface NewsQuickRefreshResponse {
  status: string;
  refreshMode: string;
  startedAt?: string;
  completedAt?: string;
  plannedCalls?: number;
  executedCalls?: number;
  skippedCalls?: number;
  totalFetched?: number;
  totalSaved?: number;
  duplicatesRemoved?: number;
  lowRelevanceIgnored?: number;
  eventsCreated?: number;
  bullishCount: number;
  bearishCount: number;
  neutralCount: number;
  criticalEventCount: number;
  highEventCount: number;
  topEvents: NewsTopEvent[];
  providerErrors: string[];
  comments: string[];
  newsSignal: NewsSignalDto;
}

export interface NewsCardViewModel {
  label: NewsSignalLabel;
  newsScore: number;
  bullishCount: number;
  bearishCount: number;
  neutralCount: number;
  criticalCount: number;
  highCount: number;
  lastUpdated: string | null;
  dataFreshnessMinutes: number | null;
  providerStatus: ProviderStatus;
  topCatalyst: string | null;
  comments: string[];
  providerErrors: string[];
  refreshData: NewsQuickRefreshResponse | null;
  loadError: string | null;
}

export const EMPTY_NEWS_CARD: NewsCardViewModel = {
  label: "Unavailable",
  newsScore: 0,
  bullishCount: 0,
  bearishCount: 0,
  neutralCount: 0,
  criticalCount: 0,
  highCount: 0,
  lastUpdated: null,
  dataFreshnessMinutes: null,
  providerStatus: "Error",
  topCatalyst: null,
  comments: ["News signal not loaded yet. Click Quick Refresh or wait for initial fetch."],
  providerErrors: [],
  refreshData: null,
  loadError: null,
};
