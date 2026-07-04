const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export interface ModuleRefreshStatus {
  module: string;
  status: "ok" | "error";
  refreshed_at: string | null;
  duration_ms: number;
  error: string | null;
}

export interface MarketOpenRefreshTimestamps {
  news_refreshed_at: string | null;
  regime_refreshed_at: string | null;
  scanner_refreshed_at: string | null;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  next_recommended_refresh_at: string;
}

export interface MarketOpenRefreshResult {
  status: "ok" | "partial" | "failed";
  timestamps: MarketOpenRefreshTimestamps;
  modules: ModuleRefreshStatus[];
  scanner_payload: Record<string, unknown> | null;
}

export interface AnalyzeTopNJob {
  job_id: string;
  status: "running" | "done" | "stopped" | "no_job";
  symbols: string[];
  n: number;
  started_at: string;
  finished_at: string | null;
  current_index: number;
  current_symbol: string;
  progress: string;
  completed_symbols: Array<{
    symbol: string;
    status: string;
    duration_ms: number;
    error: string | null;
  }>;
  error: string | null;
}

export async function marketOpenRefresh(): Promise<MarketOpenRefreshResult> {
  const res = await fetch(`${API_BASE}/api/global/market-open-refresh`, { method: "POST" });
  return parseJson(res);
}

export async function getMarketOpenRefreshStatus(): Promise<MarketOpenRefreshResult> {
  const res = await fetch(`${API_BASE}/api/global/market-open-refresh/status`, { cache: "no-store" });
  return parseJson(res);
}

export async function analyzeTopN(n = 5): Promise<{ status: string; job: AnalyzeTopNJob }> {
  const res = await fetch(`${API_BASE}/api/global/analyze-top-n`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ n }),
  });
  return parseJson(res);
}

export async function getAnalyzeTopNStatus(): Promise<{ status: string; job?: AnalyzeTopNJob }> {
  const res = await fetch(`${API_BASE}/api/global/analyze-top-n/status`, { cache: "no-store" });
  return parseJson(res);
}
