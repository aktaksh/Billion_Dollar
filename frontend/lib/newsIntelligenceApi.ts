import type { NewsCardViewModel, NewsQuickRefreshResponse } from "@/types/newsIntelligence";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const CACHE_TTL_MS = 15 * 60 * 1000;

type CacheEntry = {
  symbol: string;
  data: NewsQuickRefreshResponse;
  at: number;
};

let signalCache: CacheEntry | null = null;

function isCacheValid(symbol: string): boolean {
  if (!signalCache || signalCache.symbol !== symbol.toUpperCase()) return false;
  return Date.now() - signalCache.at < CACHE_TTL_MS;
}

async function parseError(res: Response): Promise<string> {
  try {
    const text = await res.text();
    if (!text) return `HTTP ${res.status}`;
    try {
      const json = JSON.parse(text) as { detail?: string };
      return json.detail ?? text;
    } catch {
      return text;
    }
  } catch {
    return `HTTP ${res.status}`;
  }
}

export function getCachedSignal(symbol: string): NewsQuickRefreshResponse | null {
  if (isCacheValid(symbol)) return signalCache!.data;
  return null;
}

export function clearSignalCache(): void {
  signalCache = null;
}

export async function quickRefresh(symbol = "QQQ"): Promise<NewsQuickRefreshResponse> {
  const res = await fetch(`${API_BASE}/api/news-intelligence/quick-refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol }),
  });
  if (!res.ok) {
    throw new Error(await parseError(res));
  }
  const data = (await res.json()) as NewsQuickRefreshResponse;
  signalCache = { symbol: symbol.toUpperCase(), data, at: Date.now() };
  return data;
}

export async function getLatestSignal(symbol = "QQQ"): Promise<NewsQuickRefreshResponse> {
  if (isCacheValid(symbol)) {
    return signalCache!.data;
  }
  const res = await fetch(`${API_BASE}/api/news-intelligence/signal/${encodeURIComponent(symbol)}`);
  if (!res.ok) {
    throw new Error(await parseError(res));
  }
  const data = (await res.json()) as NewsQuickRefreshResponse;
  signalCache = { symbol: symbol.toUpperCase(), data, at: Date.now() };
  return data;
}

export function responseToCardView(data: NewsQuickRefreshResponse): NewsCardViewModel {
  const sig = data.newsSignal;
  return {
    label: sig.label,
    newsScore: sig.news_score_0_to_100,
    bullishCount: data.bullishCount ?? sig.bullish_count,
    bearishCount: data.bearishCount ?? sig.bearish_count,
    neutralCount: data.neutralCount ?? sig.neutral_count,
    criticalCount: data.criticalEventCount,
    highCount: data.highEventCount,
    lastUpdated: sig.last_updated,
    dataFreshnessMinutes: sig.data_freshness_minutes,
    providerStatus: sig.provider_status,
    topCatalyst: sig.top_catalyst,
    comments: data.comments ?? [],
    providerErrors: data.providerErrors ?? [],
    refreshData: data,
    loadError: null,
  };
}
