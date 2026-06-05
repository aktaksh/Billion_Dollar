import type {
  ActiveUniverse,
  BlotterRow,
  DashboardSummary,
  EnrichedRecommendation,
  ExplainFeedItem,
  EventSummary,
  PositionsResponse,
  ReconcileMismatch,
  Recommendation,
  ReplayRunOut,
  RiskStatus,
  StrategyBuilderCandidatesIn,
  StrategyBuilderCandidatesOut,
  StrategyRuntimeOut,
  PaperTradeRunOut,
  StrategyHealthRow,
  TradeCard,
  TradeDecision,
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

export function getExplainFeed(params?: {
  ticker?: string;
  limit?: number;
  correlation_id?: string;
  minutes?: number;
  scope?: string;
  decision_id?: string;
}) {
  const query = new URLSearchParams();
  if (params?.ticker) query.set("ticker", params.ticker);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.correlation_id) query.set("correlation_id", params.correlation_id);
  if (params?.minutes) query.set("minutes", String(params.minutes));
  if (params?.scope) query.set("scope", params.scope);
  if (params?.decision_id) query.set("decision_id", params.decision_id);
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

export function getShellStatus() {
  return fetchJson<import("@/types").ShellStatus>("/api/ops/shell-status");
}

export function getBrokerStatus() {
  return fetchJson<import("@/types").BrokerStatus>("/api/ops/broker/status");
}

export function connectBroker(refreshIngestion = true) {
  return fetchJsonWithInit<import("@/types").BrokerConnectResult>(
    `/api/ops/broker/connect?refresh_ingestion=${refreshIngestion ? "true" : "false"}`,
    { method: "POST" },
  );
}

export function runIngestionOnce(payload: { tickers: string[]; include_news?: boolean }) {
  return fetchJsonWithInit<{ run_id: string; processed: number; as_of: string; data_status: string }>(
    "/api/ops/ingestion/run-once",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export function getStrategyBuilderCandidates(payload: StrategyBuilderCandidatesIn) {
  return fetchJsonWithInit<StrategyBuilderCandidatesOut>("/api/strategy-builder/candidates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function runStrategyRuntime(payload: {
  ticker: string;
  direction: "bullish" | "bearish";
  reconciliation_mismatch_active?: boolean;
  thresholds?: Record<string, number>;
}) {
  return fetchJsonWithInit<StrategyRuntimeOut>("/api/strategy-builder/runtime", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function runReplay(payload: { ticker: string; direction: "bullish" | "bearish"; scenarios?: number[] }) {
  return fetchJsonWithInit<ReplayRunOut>("/api/replay/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function runPaperTrade(payload: {
  mode?: "decision" | "quick";
  decision_id?: string;
  ticker?: string;
  direction?: "bullish" | "bearish";
  scenario_return?: number;
}) {
  return fetchJsonWithInit<PaperTradeRunOut>("/api/paper/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: "decision", scenario_return: 0.015, ...payload }),
  });
}

export function getDashboardSummary() {
  return fetchJson<DashboardSummary>("/api/dashboard/summary");
}

export function getDashboardRecommendations() {
  return fetchJson<EnrichedRecommendation[]>("/api/dashboard/recommendations");
}

export function saveDecision(payload: Record<string, unknown>) {
  return fetchJsonWithInit<TradeDecision>("/api/decisions/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getDecisions(params?: { symbol?: string; review_status?: string }) {
  const q = new URLSearchParams();
  if (params?.symbol) q.set("symbol", params.symbol);
  if (params?.review_status) q.set("review_status", params.review_status);
  const suffix = q.toString() ? `?${q.toString()}` : "";
  return fetchJson<TradeDecision[]>(`/api/decisions${suffix}`);
}

export function getDecision(decisionId: string) {
  return fetchJson<TradeDecision>(`/api/decisions/${encodeURIComponent(decisionId)}`);
}

export function patchDecision(decisionId: string, payload: Record<string, unknown>) {
  return fetchJsonWithInit<TradeDecision>(`/api/decisions/${encodeURIComponent(decisionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getTradeReview() {
  return fetchJson<TradeReviewItem[]>("/api/trade-review");
}

export function classifyReview(decisionId: string) {
  return fetchJsonWithInit<{ decision_id: string; final_outcome: string; review_status: string }>(
    `/api/trade-review/${encodeURIComponent(decisionId)}/classify`,
    { method: "POST" },
  );
}

export function completeReview(decisionId: string, payload: { final_outcome: string; lesson: string }) {
  return fetchJsonWithInit<TradeDecision>(`/api/trade-review/${encodeURIComponent(decisionId)}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}


