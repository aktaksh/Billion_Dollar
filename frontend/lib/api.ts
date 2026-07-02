import type { QqqSpreadAnalysis, QqqSpreadRunOut, QqqSpreadRunStatusOut } from "@/types/qqqSpreadAnalyzer";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function readApiError(res: Response, path: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string | Array<{ msg?: string }> };
    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail;
    }
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const first = body.detail[0];
      if (first && typeof first.msg === "string") {
        return first.msg;
      }
    }
  } catch {
    // ignore JSON parse errors
  }
  return `Request failed: ${res.status} ${path}`;
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(await readApiError(res, path));
  }
  return (await res.json()) as T;
}

async function fetchJsonWithInit<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    throw new Error(await readApiError(res, path));
  }
  return (await res.json()) as T;
}

export async function getQqqSpreadAnalysis(symbol = "QQQ"): Promise<QqqSpreadAnalysis | null> {
  const sym = symbol.trim().toUpperCase();
  const res = await fetch(`${API_BASE}/api/qqq-spread-analyzer/latest?symbol=${encodeURIComponent(sym)}`, {
    cache: "no-store",
  });
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} /api/qqq-spread-analyzer/latest`);
  }
  return (await res.json()) as QqqSpreadAnalysis;
}

export function runQqqSpreadAnalysis(symbol = "QQQ", noCache = false) {
  return fetchJsonWithInit<QqqSpreadRunOut>("/api/qqq-spread-analyzer/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol: symbol.trim().toUpperCase(), no_cache: noCache }),
  });
}

export function getQqqSpreadRunStatus(jobId: string) {
  return fetchJson<QqqSpreadRunStatusOut>(`/api/qqq-spread-analyzer/run/${encodeURIComponent(jobId)}`);
}

export async function getOptionsSpreadStrategyAnalysis(symbol: string): Promise<QqqSpreadAnalysis | null> {
  const sym = symbol.trim().toUpperCase();
  const res = await fetch(`${API_BASE}/api/options-spread-strategy/latest?symbol=${encodeURIComponent(sym)}`, {
    cache: "no-store",
  });
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    throw new Error(await readApiError(res, `/api/options-spread-strategy/latest`));
  }
  return (await res.json()) as QqqSpreadAnalysis;
}

export function runOptionsSpreadStrategyAnalysis(symbol: string, noCache = false) {
  return fetchJsonWithInit<QqqSpreadRunOut>("/api/options-spread-strategy/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol: symbol.trim().toUpperCase(), no_cache: noCache }),
  });
}

export function getOptionsSpreadStrategyRunStatus(jobId: string) {
  return fetchJson<QqqSpreadRunStatusOut>(`/api/options-spread-strategy/run/${encodeURIComponent(jobId)}`);
}
