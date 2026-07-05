"use client";

import { useEffect, useState } from "react";

import NewsEventsTable from "@/components/qqq-spread/news/NewsEventsTable";
import { getLatestSignal } from "@/lib/newsIntelligenceApi";
import type { MicTickerSignal } from "@/types/marketIntelligence";
import type { NewsTopEvent } from "@/types/newsIntelligence";

import { biasClass, confidenceClass } from "./TickerSignalTable";

type Props = {
  signal: MicTickerSignal | null;
  onClose: () => void;
};

function fmt(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function TickerSignalDrawer({ signal, onClose }: Props) {
  const [articles, setArticles] = useState<NewsTopEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    if (!signal) return;
    setLoading(true);
    setLoadError("");
    setArticles([]);
    getLatestSignal(signal.symbol)
      .then((res) => setArticles(res.topEvents ?? []))
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load raw articles"))
      .finally(() => setLoading(false));
  }, [signal]);

  if (!signal) return null;

  return (
    <>
      <div className="mic-drawer-backdrop" onClick={onClose} aria-hidden />
      <aside className="mic-drawer" role="dialog" aria-label={`${signal.symbol} ticker news signal detail`}>
        <div className="panel-header">
          <h3>{signal.symbol}</h3>
          <button type="button" className="qqq-btn" onClick={onClose}>Close</button>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
          <span className={biasClass(signal.news_bias)}>{signal.news_bias}</span>
          <span className={confidenceClass(signal.confidence)}>{signal.confidence} confidence</span>
        </div>

        <div className="mic-cards-grid mic-cards-6">
          <article className="mic-card mic-card-compact"><div className="mic-card-label">Quality</div><div className="mic-card-value">{signal.news_quality_score.toFixed(0)}</div></article>
          <article className="mic-card mic-card-compact"><div className="mic-card-label">Catalyst Strength</div><div className="mic-card-value">{signal.catalyst_strength_score.toFixed(0)}</div></article>
          <article className="mic-card mic-card-compact"><div className="mic-card-label">Net Impact</div><div className="mic-card-value">{signal.net_impact_score.toFixed(0)}</div></article>
          <article className="mic-card mic-card-compact"><div className="mic-card-label">Bullish</div><div className="mic-card-value">{signal.bullish_count}</div></article>
          <article className="mic-card mic-card-compact"><div className="mic-card-label">Bearish</div><div className="mic-card-value">{signal.bearish_count}</div></article>
          <article className="mic-card mic-card-compact"><div className="mic-card-label">Neutral</div><div className="mic-card-value">{signal.neutral_count}</div></article>
        </div>

        <div className="mic-drawer-section">
          <h4>Top Catalyst</h4>
          <p>{signal.top_catalyst ?? "—"}</p>
        </div>
        <div className="mic-drawer-section">
          <h4>Top Risk</h4>
          <p>{signal.top_risk ?? "—"}</p>
        </div>
        {signal.llm_summary && (
          <div className="mic-drawer-section">
            <h4>Summary</h4>
            <p>{signal.llm_summary}</p>
          </div>
        )}
        <div className="mic-drawer-section">
          <h4>Last Updated</h4>
          <p>{fmt(signal.last_updated)}</p>
        </div>

        <details className="mic-diagnostics">
          <summary>Raw source articles (diagnostics)</summary>
          {loading && <p className="muted-text">Loading articles…</p>}
          {loadError && <p className="muted-text">{loadError}</p>}
          {!loading && !loadError && (
            <NewsEventsTable events={articles} emptyMessage="No cached raw articles for this symbol yet." />
          )}
        </details>
      </aside>
    </>
  );
}
