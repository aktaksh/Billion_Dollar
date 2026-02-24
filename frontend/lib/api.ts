import type {
  ActiveUniverse,
  BlotterRow,
  ExplainFeedItem,
  EventSummary,
  PositionsResponse,
  ReconcileMismatch,
  Recommendation,
  RiskStatus,
  StrategyHealthRow,
  TradeCard,
  TradeReviewItem,
  UniverseUploadResponse,
  UniverseVersionRow,
  WatchlistOpportunity,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${path}`);
  }
  return (await res.json()) as T;
}

async function fetchJsonWithInit<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${path}`);
  }
  return (await res.json()) as T;
}

export function getRecommendations() {
  return fetchJson<Recommendation[]>("/api/recommendations");
}

export function getRiskStatus() {
  return fetchJson<RiskStatus>("/api/risk-status");
}

export function getEvents() {
  return fetchJson<EventSummary[]>("/api/events");
}

export function getExplainFeed(params?: { ticker?: string; limit?: number; correlation_id?: string; minutes?: number }) {
  const query = new URLSearchParams();
  if (params?.ticker) query.set("ticker", params.ticker);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.correlation_id) query.set("correlation_id", params.correlation_id);
  if (params?.minutes) query.set("minutes", String(params.minutes));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return fetchJson<ExplainFeedItem[]>(`/api/explain-feed${suffix}`);
}

export function getStrategyHealth() {
  return fetchJson<StrategyHealthRow[]>("/api/strategy-health");
}

export function getTradeReviewQueue() {
  return fetchJson<TradeReviewItem[]>("/api/trade-review-queue");
}

export function getUniverseActive() {
  return fetchJson<ActiveUniverse>("/api/universe/active");
}

export function getUniverseVersions() {
  return fetchJson<UniverseVersionRow[]>("/api/universe/versions");
}

export function activateUniverse(universe_version_id: string, universe_id: string, activated_by: string) {
  return fetchJsonWithInit<{ event_id: string; activated_at: string; universe_version_id: string; universe_id: string }>(
    "/api/universe/activate",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ universe_version_id, universe_id, activated_by }),
    },
  );
}

export async function uploadUniverse(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return fetchJsonWithInit<UniverseUploadResponse>("/api/universe/upload", {
    method: "POST",
    body: formData,
  });
}

export function getWatchlist() {
  return fetchJson<WatchlistOpportunity[]>("/api/watchlist");
}

export function getTradeCard(ticker: string) {
  return fetchJson<TradeCard>(`/api/tickers/${encodeURIComponent(ticker)}/trade-card`);
}

export function getPositions() {
  return fetchJson<PositionsResponse>("/api/positions");
}

export function getBlotter() {
  return fetchJson<BlotterRow[]>("/api/blotter");
}

export function getReconcileMismatches() {
  return fetchJson<ReconcileMismatch[]>("/api/reconcile/mismatches");
}


