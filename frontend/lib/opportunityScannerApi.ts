import type { OpportunityScannerPayload } from "@/types/opportunityScanner";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export async function getOpportunityScannerLatest(): Promise<OpportunityScannerPayload> {
  const res = await fetch(`${API_BASE}/api/opportunity-scanner/latest`, { cache: "no-store" });
  return parseJson(res);
}

export async function refreshOpportunityScanner(refreshNews = false): Promise<OpportunityScannerPayload> {
  const res = await fetch(`${API_BASE}/api/opportunity-scanner/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_news: refreshNews }),
  });
  return parseJson(res);
}

export async function exportOpportunityScanner(): Promise<string> {
  const res = await fetch(`${API_BASE}/api/opportunity-scanner/export`, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.text();
}

export async function getOpportunitySymbol(symbol: string) {
  const res = await fetch(`${API_BASE}/api/opportunity-scanner/symbol/${encodeURIComponent(symbol)}`, {
    cache: "no-store",
  });
  return parseJson(res);
}
