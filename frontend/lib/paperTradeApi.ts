import type { QqqSpreadAnalysis, QqqSpreadCandidate } from "@/types/qqqSpreadAnalyzer";
import type {
  IbkrSyncResult,
  PaperTrade,
  PaperTradeAnalytics,
  PaperTradeDetail,
  PaperTradeFilters,
  PaperTradeSummary,
  PaperTradeSyncStatus,
} from "@/types/paperTrading";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function readApiError(res: Response, path: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  } catch {
    // ignore
  }
  return `Request failed: ${res.status} ${path}`;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(await readApiError(res, path));
  return (await res.json()) as T;
}

function queryString(filters: PaperTradeFilters): string {
  const params = new URLSearchParams();
  if (filters.symbol) params.set("symbol", filters.symbol.toUpperCase());
  if (filters.strategy_type) params.set("strategy_type", filters.strategy_type);
  if (filters.status) params.set("status", filters.status);
  if (filters.profit_only) params.set("profit_only", "true");
  if (filters.loss_only) params.set("loss_only", "true");
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function createPaperTrade(
  analysis: QqqSpreadAnalysis,
  candidate: QqqSpreadCandidate,
  notes: string,
  quantity: number,
) {
  return fetchJson<PaperTrade>("/api/paper-trading/trades", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis, candidate, notes, quantity }),
  });
}

export function bulkCreatePaperTrades(analysis: QqqSpreadAnalysis, notes: string) {
  return fetchJson<{ created: PaperTrade[]; count: number }>("/api/paper-trading/trades/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis, notes }),
  });
}

export function listPaperTrades(filters: PaperTradeFilters = {}) {
  return fetchJson<PaperTrade[]>(`/api/paper-trading/trades${queryString(filters)}`);
}

export function getPaperTrade(id: string) {
  return fetchJson<PaperTradeDetail>(`/api/paper-trading/trades/${encodeURIComponent(id)}`);
}

export function updatePaperTradeNotes(id: string, notes: string) {
  return fetchJson<PaperTradeDetail>(`/api/paper-trading/trades/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
}

export function closePaperTrade(id: string, exitReason: string) {
  return fetchJson<PaperTradeDetail>(`/api/paper-trading/trades/${encodeURIComponent(id)}/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ exit_reason: exitReason }),
  });
}

export function getPaperTradeSummary() {
  return fetchJson<PaperTradeSummary>("/api/paper-trading/summary");
}

export function getPaperTradeAnalytics() {
  return fetchJson<PaperTradeAnalytics>("/api/paper-trading/analytics");
}

export function exportPaperTradesUrl(format: "csv" | "json", filters: PaperTradeFilters = {}): string {
  const params = new URLSearchParams({ format });
  if (filters.symbol) params.set("symbol", filters.symbol.toUpperCase());
  if (filters.status) params.set("status", filters.status);
  return `${API_BASE}/api/paper-trading/export?${params.toString()}`;
}

export function getIbkrSyncStatus() {
  return fetchJson<PaperTradeSyncStatus>("/api/paper-trading/ibkr/status");
}

export function ibkrFetchPositions() {
  return fetchJson<IbkrSyncResult>("/api/paper-trading/ibkr/fetch-positions", { method: "POST" });
}

export function ibkrRefreshPrices() {
  return fetchJson<IbkrSyncResult>("/api/paper-trading/ibkr/refresh-prices", { method: "POST" });
}

export function ibkrRecalculateAll() {
  return fetchJson<IbkrSyncResult>("/api/paper-trading/ibkr/recalculate", { method: "POST" });
}

export function ibkrSyncFromBroker() {
  return fetchJson<IbkrSyncResult>("/api/paper-trading/ibkr/sync", { method: "POST" });
}

export function setIbkrAutoSync(intervalSeconds: number) {
  return fetchJson<{ interval_seconds: number; running: boolean }>("/api/paper-trading/ibkr/auto-sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ interval_seconds: intervalSeconds }),
  });
}
