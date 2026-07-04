"use client";

import { useCallback, useEffect, useState } from "react";

import NewsDetailsModal from "@/components/qqq-spread/news/NewsDetailsModal";
import NewsQuickRefreshButton from "@/components/qqq-spread/news/NewsQuickRefreshButton";
import NewsStatusBadge from "@/components/qqq-spread/news/NewsStatusBadge";
import {
  getLatestSignal,
  quickRefresh,
  responseToCardView,
} from "@/lib/newsIntelligenceApi";
import {
  EMPTY_NEWS_CARD,
  type NewsCardViewModel,
  type NewsQuickRefreshResponse,
} from "@/types/newsIntelligence";

type Props = {
  symbol?: string;
};

function formatLastUpdated(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatFreshness(minutes: number | null): string {
  if (minutes === null || minutes === undefined) return "—";
  if (minutes < 60) return `${minutes}m ago`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m ago` : `${h}h ago`;
}

export default function NewsIntelligenceCard({ symbol = "QQQ" }: Props) {
  const [view, setView] = useState<NewsCardViewModel>(EMPTY_NEWS_CARD);
  const [refreshData, setRefreshData] = useState<NewsQuickRefreshResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [toast, setToast] = useState<{ kind: "success" | "error"; message: string } | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const applyResponse = useCallback((data: NewsQuickRefreshResponse) => {
    setRefreshData(data);
    setView(responseToCardView(data));
  }, []);

  const loadCached = useCallback(async () => {
    try {
      const data = await getLatestSignal(symbol);
      applyResponse(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load news signal";
      setView((prev) => ({
        ...prev,
        loadError: msg,
        comments: prev.comments.length > 0 ? prev.comments : ["News signal not loaded yet. Click Quick Refresh."],
      }));
    } finally {
      setInitialLoading(false);
    }
  }, [applyResponse, symbol]);

  useEffect(() => {
    void loadCached();
  }, [loadCached]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(t);
  }, [toast]);

  const handleQuickRefresh = useCallback(async () => {
    setLoading(true);
    setView((prev) => ({ ...prev, loadError: null }));
    try {
      const data = await quickRefresh(symbol);
      applyResponse(data);
      setToast({ kind: "success", message: "News refresh completed." });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "News refresh failed.";
      setToast({ kind: "error", message: "News refresh failed." });
      setView((prev) => ({
        ...prev,
        loadError: msg,
        providerErrors: [msg, ...prev.providerErrors].slice(0, 5),
        comments: ["News refresh failed.", ...prev.comments],
      }));
    } finally {
      setLoading(false);
    }
  }, [applyResponse, symbol]);

  const hasHighImpact =
    view.criticalCount + view.highCount > 0 ||
    (refreshData?.topEvents?.length ?? 0) > 0;

  const showEmpty =
    !loading &&
    !initialLoading &&
    !view.loadError &&
    view.bullishCount + view.bearishCount + view.neutralCount === 0 &&
    !hasHighImpact;

  return (
    <section className="panel ni-panel">
      <div className="panel-header ni-header">
        <div>
          <h2 className="panel-title">News Intelligence</h2>
          <p className="muted-text ni-subtitle">Headline sentiment and catalyst scan for {symbol}.</p>
        </div>
        <div className="ni-actions">
          <NewsQuickRefreshButton onRefresh={() => void handleQuickRefresh()} loading={loading} />
          <button
            type="button"
            className="qqq-btn"
            onClick={() => setDetailsOpen(true)}
            disabled={!refreshData}
          >
            View Details
          </button>
        </div>
      </div>

      {toast && (
        <div className={`banner ${toast.kind === "success" ? "banner-success" : "banner-danger"}`}>
          {toast.message}
        </div>
      )}

      {view.loadError && (
        <div className="ni-error-banner">
          <strong>News refresh failed.</strong>
          <p className="muted-text">{view.loadError}</p>
          {view.providerErrors.length > 0 && (
            <ul className="qqq-muted-list">
              {view.providerErrors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
          <button type="button" className="qqq-btn qqq-btn-primary" onClick={() => void handleQuickRefresh()} disabled={loading}>
            Retry
          </button>
        </div>
      )}

      {initialLoading && !refreshData && (
        <p className="muted-text ni-loading-hint">Loading cached news signal…</p>
      )}

      <div className="ni-cards">
        <article className="ni-card">
          <div className="qqq-card-label">News Signal</div>
          <NewsStatusBadge label={view.label} />
        </article>
        <article className="ni-card">
          <div className="qqq-card-label">News Score</div>
          <div className="ni-score-value">{view.newsScore}</div>
        </article>
        <article className="ni-card">
          <div className="qqq-card-label">Bullish Events</div>
          <div className="ni-count ni-count-bull">{view.bullishCount}</div>
        </article>
        <article className="ni-card">
          <div className="qqq-card-label">Bearish Events</div>
          <div className="ni-count ni-count-bear">{view.bearishCount}</div>
        </article>
        <article className="ni-card">
          <div className="qqq-card-label">Neutral Events</div>
          <div className="ni-count">{view.neutralCount}</div>
        </article>
        <article className="ni-card">
          <div className="qqq-card-label">Critical Events</div>
          <div className="ni-count ni-count-critical">{view.criticalCount}</div>
        </article>
        <article className="ni-card">
          <div className="qqq-card-label">High Events</div>
          <div className="ni-count ni-count-high">{view.highCount}</div>
        </article>
        <article className="ni-card">
          <div className="qqq-card-label">Last Updated</div>
          <div className="ni-meta-value">{formatLastUpdated(view.lastUpdated)}</div>
        </article>
        <article className="ni-card">
          <div className="qqq-card-label">Data Freshness</div>
          <div className="ni-meta-value">{formatFreshness(view.dataFreshnessMinutes)}</div>
        </article>
        <article className="ni-card">
          <div className="qqq-card-label">Provider Status</div>
          <NewsStatusBadge label={view.providerStatus} kind="provider" />
        </article>
      </div>

      {view.topCatalyst && (
        <p className="ni-catalyst">
          <strong>Top catalyst:</strong> {view.topCatalyst}
        </p>
      )}

      {showEmpty && (
        <div className="ni-empty-state">
          <p>No new high-impact news found.</p>
        </div>
      )}

      {view.comments.length > 0 && (
        <ul className="qqq-muted-list ni-comments">
          {view.comments.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}

      {detailsOpen && refreshData && (
        <NewsDetailsModal data={refreshData} onClose={() => setDetailsOpen(false)} />
      )}
    </section>
  );
}
