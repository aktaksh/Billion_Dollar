import type { MarketIntelligenceDashboard, RefreshMode } from "@/types/marketIntelligence";

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

export function getMarketIntelligenceDashboard(): Promise<MarketIntelligenceDashboard> {
  return fetchJson<MarketIntelligenceDashboard>("/api/market-intelligence/dashboard");
}

export function refreshMarketIntelligence(mode: RefreshMode): Promise<MarketIntelligenceDashboard> {
  return fetchJson<MarketIntelligenceDashboard>("/api/market-intelligence/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
}

export async function exportMarketIntelligence(): Promise<string> {
  const res = await fetch(`${API_BASE}/api/market-intelligence/export`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readApiError(res, "/api/market-intelligence/export"));
  return res.text();
}

export function patchWatchlistRow(
  symbol: string,
  patch: { enabled?: boolean; priority?: number },
): Promise<Record<string, unknown>> {
  return fetchJson(`/api/market-intelligence/watchlist/${encodeURIComponent(symbol)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export function resetWatchlist(): Promise<{ reset: boolean; count: number }> {
  return fetchJson("/api/market-intelligence/watchlist/reset", { method: "POST" });
}
