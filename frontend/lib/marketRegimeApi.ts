import type { HistoryPoint, MarketRegimeDashboard } from "@/types/marketRegimeDashboard";

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

export function getMarketRegimeLatest(): Promise<MarketRegimeDashboard> {
  return fetchJson<MarketRegimeDashboard>("/api/market-regime/latest");
}

export function refreshMarketRegime(): Promise<MarketRegimeDashboard> {
  return fetchJson<MarketRegimeDashboard>("/api/market-regime/refresh", { method: "POST" });
}

export function refreshAllMarketData(): Promise<MarketRegimeDashboard> {
  return fetchJson<MarketRegimeDashboard>("/api/market-regime/refresh-all", { method: "POST" });
}

export function saveMarketRegimeSnapshot(): Promise<{ saved: boolean; snapshot_date: string; id?: string }> {
  return fetchJson("/api/market-regime/save-snapshot", { method: "POST" });
}

export function getMarketRegimeHistory(days = 30): Promise<HistoryPoint[]> {
  return fetchJson<HistoryPoint[]>(`/api/market-regime/history?days=${days}`);
}

export async function exportMarketRegime(): Promise<string> {
  const res = await fetch(`${API_BASE}/api/market-regime/export`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readApiError(res, "/api/market-regime/export"));
  return res.text();
}
