"use client";

import { useCallback, useEffect, useState } from "react";

import ApiBudgetPanel from "@/components/market-intelligence/ApiBudgetPanel";
import CatalystCalendarTable from "@/components/market-intelligence/CatalystCalendarTable";
import CriticalEventsTable from "@/components/market-intelligence/CriticalEventsTable";
import MarketIntelligenceSummaryCards from "@/components/market-intelligence/MarketIntelligenceSummaryCards";
import MarketRegimeContextCard from "@/components/market-intelligence/MarketRegimeContextCard";
import NewsSignalOutputPanel from "@/components/market-intelligence/NewsSignalOutputPanel";
import RefreshActivityLog from "@/components/market-intelligence/RefreshActivityLog";
import SecFilingsTable from "@/components/market-intelligence/SecFilingsTable";
import SentimentAnalyticsPanel from "@/components/market-intelligence/SentimentAnalyticsPanel";
import WatchlistManagerTable from "@/components/market-intelligence/WatchlistManagerTable";
import {
  exportMarketIntelligence,
  getMarketIntelligenceDashboard,
  refreshMarketIntelligence,
} from "@/lib/marketIntelligenceApi";
import type { MarketIntelligenceDashboard, RefreshMode } from "@/types/marketIntelligence";
import "@/styles/market-intelligence.css";

export default function MarketIntelligencePage() {
  const [data, setData] = useState<MarketIntelligenceDashboard | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<RefreshMode | "export" | "load" | null>(null);
  const [toast, setToast] = useState("");

  const load = useCallback(async () => {
    setBusy("load");
    setError("");
    try {
      const dash = await getMarketIntelligenceDashboard();
      setData(dash);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setBusy(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(""), 4000);
    return () => window.clearTimeout(t);
  }, [toast]);

  async function handleRefresh(mode: RefreshMode) {
    setBusy(mode);
    setError("");
    try {
      const dash = await refreshMarketIntelligence(mode);
      setData(dash);
      setToast(`${mode.charAt(0).toUpperCase()}${mode.slice(1)} refresh completed.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleExport() {
    setBusy("export");
    try {
      const json = await exportMarketIntelligence();
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `market-intelligence-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setToast("Export downloaded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  const header = data?.header;
  const refreshing = busy === "quick" || busy === "standard" || busy === "deep";

  return (
    <div className="container page-stack mic-page">
      <header className="mic-header panel">
        <div>
          <h1 className="panel-title">Market Intelligence Center</h1>
          <p className="muted-text mic-subtitle">
            News, earnings, filings, catalysts, and event impact engine — research only, no trade execution.
          </p>
        </div>
        <div className="mic-header-meta">
          <span className="muted-text">Last Updated: {header?.last_updated ? new Date(header.last_updated).toLocaleString() : "—"}</span>
          <span className="muted-text">API Status: {header?.api_status ?? "—"}</span>
        </div>
        <div className="qqq-actions mic-header-actions">
          <button type="button" className="qqq-btn qqq-btn-primary" disabled={refreshing} onClick={() => void handleRefresh("quick")}>
            {busy === "quick" ? "Refreshing…" : "Quick Refresh"}
          </button>
          <button type="button" className="qqq-btn" disabled={refreshing} onClick={() => void handleRefresh("standard")}>
            {busy === "standard" ? "Refreshing…" : "Standard Refresh"}
          </button>
          <button type="button" className="qqq-btn" disabled={refreshing} onClick={() => void handleRefresh("deep")}>
            {busy === "deep" ? "Refreshing…" : "Deep Refresh"}
          </button>
          <button type="button" className="qqq-btn" disabled={busy === "export"} onClick={() => void handleExport()}>
            Export
          </button>
        </div>
      </header>

      {error && <div className="banner banner-danger">{error}</div>}
      {toast && <div className="banner banner-success">{toast}</div>}

      {!data && !error && busy === "load" && (
        <section className="panel"><p className="muted-text">Loading Market Intelligence dashboard…</p></section>
      )}

      {data && (
        <>
          <MarketIntelligenceSummaryCards summary={data.summary} />
          <MarketRegimeContextCard context={data.regime_context} />

          <section className="mic-section panel">
            <h2 className="mic-section-title">Watchlist Manager</h2>
            <WatchlistManagerTable rows={data.watchlist} onUpdated={() => void load()} />
          </section>

          <section className="mic-section panel">
            <h2 className="mic-section-title">Critical Events</h2>
            <CriticalEventsTable events={data.critical_events} />
          </section>

          <section className="mic-section panel">
            <h2 className="mic-section-title">Earnings &amp; Catalyst Calendar</h2>
            <CatalystCalendarTable rows={data.catalyst_calendar} />
          </section>

          <section className="mic-section panel">
            <h2 className="mic-section-title">SEC Filings</h2>
            <SecFilingsTable rows={data.sec_filings} />
          </section>

          <section className="mic-section panel">
            <h2 className="mic-section-title">Sentiment Analytics</h2>
            <SentimentAnalyticsPanel data={data.sentiment_analytics} />
          </section>

          <section className="mic-section panel">
            <h2 className="mic-section-title">API Budget &amp; Query Planner</h2>
            <ApiBudgetPanel budget={data.api_budget} ibkrStatus={data.ibkr_news_status} />
          </section>

          <section className="mic-section panel">
            <h2 className="mic-section-title">Refresh Activity Log</h2>
            <RefreshActivityLog rows={data.activity_log} />
          </section>

          <section className="mic-section panel">
            <h2 className="mic-section-title">News Signal Output</h2>
            <NewsSignalOutputPanel output={data.news_signal_output} />
          </section>

          {data.comments.length > 0 && (
            <section className="mic-section panel">
              <h2 className="mic-section-title">Comments</h2>
              <ul className="qqq-muted-list">
                {data.comments.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
