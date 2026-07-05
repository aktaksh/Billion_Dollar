"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import OpportunityDetailDrawer from "@/components/opportunity-scanner/OpportunityDetailDrawer";
import OpportunityFilters, { applyOpportunityFilters } from "@/components/opportunity-scanner/OpportunityFilters";
import OpportunitySummaryCards from "@/components/opportunity-scanner/OpportunitySummaryCards";
import OpportunityTable from "@/components/opportunity-scanner/OpportunityTable";
import {
  exportOpportunityScanner,
  getOpportunityScannerLatest,
  refreshOpportunityScanner,
} from "@/lib/opportunityScannerApi";
import {
  analyzeTopN,
  getAnalyzeTopNStatus,
  marketOpenRefresh,
  type MarketOpenRefreshTimestamps,
} from "@/lib/globalRefreshApi";
import { getTickerSignals } from "@/lib/marketIntelligenceApi";
import type { MicTickerSignal } from "@/types/marketIntelligence";
import {
  DEFAULT_OPPORTUNITY_FILTERS,
  type OpportunityFiltersState,
  type OpportunityScanRow,
  type OpportunityScannerPayload,
} from "@/types/opportunityScanner";
import "@/styles/opportunity-scanner.css";

const TS_STORAGE_KEY = "market_open_refresh_timestamps";

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}

function loadSavedTimestamps(): MarketOpenRefreshTimestamps | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(TS_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export default function OpportunityScannerPage() {
  const [data, setData] = useState<OpportunityScannerPayload | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"load" | "refresh" | "news" | "export" | "mor" | "top5" | null>(null);
  const [toast, setToast] = useState("");
  const [filters, setFilters] = useState<OpportunityFiltersState>(DEFAULT_OPPORTUNITY_FILTERS);
  const [selected, setSelected] = useState<OpportunityScanRow | null>(null);
  const [tickerSignals, setTickerSignals] = useState<Map<string, MicTickerSignal>>(new Map());
  const [timestamps, setTimestamps] = useState<MarketOpenRefreshTimestamps | null>(loadSavedTimestamps);
  const [top5Progress, setTop5Progress] = useState<string | null>(null);
  const top5PollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadTickerSignals = useCallback(async () => {
    try {
      const signals = await getTickerSignals();
      setTickerSignals(new Map(signals.map((s) => [s.symbol, s])));
    } catch {
      // Ticker-level news signals are supplementary display data only.
    }
  }, []);

  const load = useCallback(async () => {
    setBusy("load");
    setError("");
    try {
      const payload = await getOpportunityScannerLatest();
      setData(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load scanner");
    } finally {
      setBusy(null);
    }
    void loadTickerSignals();
  }, [loadTickerSignals]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(""), 4000);
    return () => window.clearTimeout(t);
  }, [toast]);

  async function handleMarketOpenRefresh() {
    setBusy("mor");
    setError("");
    try {
      const result = await marketOpenRefresh();
      if (result.timestamps) {
        setTimestamps(result.timestamps);
        localStorage.setItem(TS_STORAGE_KEY, JSON.stringify(result.timestamps));
      }
      if (result.scanner_payload) {
        setData(result.scanner_payload as unknown as OpportunityScannerPayload);
      } else {
        await load();
      }
      if (result.status === "ok") {
        setToast("Market Open Refresh completed successfully.");
      } else if (result.status === "partial") {
        const failed = result.modules.filter((m) => m.status === "error").map((m) => m.module);
        setToast(`Market Open Refresh partial — errors in: ${failed.join(", ")}`);
      } else {
        setError("Market Open Refresh failed. Check backend logs.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Market Open Refresh failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleAnalyzeTop5() {
    setBusy("top5");
    setError("");
    setTop5Progress("Starting...");
    try {
      const result = await analyzeTopN(5);
      if (result.status === "already_running") {
        setTop5Progress(result.job?.progress || "Running...");
      } else {
        setTop5Progress(result.job?.progress || "Analyzing...");
      }
      // Start polling
      if (top5PollRef.current) clearInterval(top5PollRef.current);
      top5PollRef.current = setInterval(async () => {
        try {
          const status = await getAnalyzeTopNStatus();
          if (status.job) {
            setTop5Progress(status.job.progress || "Running...");
            if (status.status === "done" || status.status === "stopped") {
              if (top5PollRef.current) clearInterval(top5PollRef.current);
              top5PollRef.current = null;
              setTop5Progress(null);
              setBusy(null);
              if (status.status === "done") {
                setToast("Analyze Top 5 completed. Technical data refreshed.");
              } else {
                setToast(`Analyze Top 5 stopped: ${status.job.error || "IBKR unavailable"}`);
              }
              void load();
            }
          }
        } catch {
          // Keep polling
        }
      }, 4000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analyze Top 5 failed");
      setBusy(null);
      setTop5Progress(null);
    }
  }

  useEffect(() => {
    return () => {
      if (top5PollRef.current) clearInterval(top5PollRef.current);
    };
  }, []);

  async function handleRefresh(refreshNews: boolean) {
    setBusy(refreshNews ? "news" : "refresh");
    setError("");
    try {
      const payload = await refreshOpportunityScanner(refreshNews);
      setData(payload);
      setToast(refreshNews ? "Scanner refreshed with news update." : "Scanner refreshed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setBusy(null);
    }
    void loadTickerSignals();
  }

  async function handleExport() {
    setBusy("export");
    try {
      const json = await exportOpportunityScanner();
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `opportunity-scanner-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setToast("Export downloaded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  const sectors = useMemo(() => {
    const set = new Set<string>();
    for (const row of data?.results ?? []) {
      if (row.sector) set.add(row.sector);
    }
    return [...set].sort();
  }, [data]);

  const filteredRows = useMemo(() => {
    if (!data?.results) return [];
    return applyOpportunityFilters(data.results, filters);
  }, [data, filters]);

  const header = data?.header;
  const loading = busy === "load" && !data;
  const upstreamWarnings = (header as Record<string, unknown>)?.upstream_warnings as string[] | undefined;

  return (
    <div className="container page-stack os-page">
      <section className="panel os-header">
        <div className="panel-header">
          <div>
            <h1 className="panel-title">Opportunity Scanner</h1>
            <p className="muted-text os-subtitle">
              Watchlist-based scanner for bullish and bearish options opportunities.
            </p>
          </div>
          <div className="qqq-actions os-header-actions">
            <button
              type="button"
              className="qqq-btn qqq-btn-primary os-mor-btn"
              disabled={!!busy}
              onClick={() => void handleMarketOpenRefresh()}
              title="Refreshes news, market regime, and opportunity ranking only. Full options analysis runs when Analyze Live is clicked."
            >
              {busy === "mor" ? "Refreshing…" : "Market Open Refresh"}
            </button>
            <button
              type="button"
              className="qqq-btn qqq-btn-primary"
              disabled={!!busy}
              onClick={() => void handleAnalyzeTop5()}
              title="Run full IBKR analysis sequentially for top 5 symbols"
            >
              {busy === "top5" ? (top5Progress || "Analyzing…") : "Analyze Top 5"}
            </button>
            <button
              type="button"
              className="qqq-btn"
              disabled={!!busy}
              onClick={() => void handleRefresh(false)}
            >
              {busy === "refresh" ? "Refreshing…" : "Refresh Scanner"}
            </button>
            <button type="button" className="qqq-btn" disabled={!!busy} onClick={() => void handleRefresh(true)}>
              {busy === "news" ? "Refreshing…" : "Refresh News"}
            </button>
            <button type="button" className="qqq-btn" disabled={!!busy} onClick={() => void handleExport()}>
              {busy === "export" ? "Exporting…" : "Export"}
            </button>
          </div>
        </div>

        {/* Market Open Refresh helper text */}
        <p className="muted-text os-mor-helper" style={{ fontSize: "0.72rem", marginTop: "0.25rem" }}>
          Market Open Refresh: news, regime, ranking only. Full options analysis runs on Analyze Live.
        </p>

        {/* Refresh timestamps */}
        {timestamps && (
          <div className="os-refresh-timestamps muted-text">
            <span>News: {formatTime(timestamps.news_refreshed_at)}</span>
            <span>Regime: {formatTime(timestamps.regime_refreshed_at)}</span>
            <span>Scanner: {formatTime(timestamps.scanner_refreshed_at)}</span>
            <span>Next refresh: {formatTime(timestamps.next_recommended_refresh_at)}</span>
            <span className="os-refresh-duration">({timestamps.duration_ms}ms)</span>
          </div>
        )}

        {header && (
          <div className="os-header-meta muted-text">
            <span>Last Updated: {new Date(header.last_updated).toLocaleString()}</span>
            <span>Symbols Scanned: {header.symbols_scanned}</span>
            <span>Data Freshness: {header.data_freshness}</span>
          </div>
        )}

        {/* Upstream warnings */}
        {upstreamWarnings && upstreamWarnings.length > 0 && (
          <div className="os-upstream-warnings">
            {upstreamWarnings.map((w, i) => (
              <div key={i} className="banner banner-warning" style={{ fontSize: "0.8rem", padding: "0.4rem 0.7rem" }}>
                {w}
              </div>
            ))}
          </div>
        )}

        <p className="os-disclaimer">
          {data?.disclaimer ??
            "Direction Candidate only — not a final trade recommendation. Analyze Live opens Options Spread Strategy; Trade Decision Engine makes final decisions."}
        </p>
      </section>

      {error && <div className="banner banner-danger">{error}</div>}
      {toast && <div className="banner banner-success">{toast}</div>}

      {loading && (
        <section className="panel">
          <p className="qqq-empty">Loading opportunity scan…</p>
        </section>
      )}

      {data?.empty_message && data.results.length === 0 && (
        <section className="panel">
          <p className="qqq-empty">{data.empty_message}</p>
        </section>
      )}

      {data && data.results.length > 0 && (
        <>
          <OpportunitySummaryCards summary={data.summary} />
          <OpportunityFilters filters={filters} sectors={sectors} onChange={setFilters} />
          <OpportunityTable rows={filteredRows} tickerSignals={tickerSignals} onSelect={setSelected} />
        </>
      )}

      <OpportunityDetailDrawer
        row={selected}
        tickerSignal={selected ? tickerSignals.get(selected.symbol) ?? null : null}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
