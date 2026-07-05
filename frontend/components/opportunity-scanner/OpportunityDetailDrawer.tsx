"use client";

import Link from "next/link";

import { biasClass, confidenceClass } from "@/components/market-intelligence/TickerSignalTable";
import type { MicTickerSignal } from "@/types/marketIntelligence";
import type { OpportunityScanRow } from "@/types/opportunityScanner";

import DirectionCandidateBadge, { OpportunityScoreBadge, readinessBadgeClass } from "./OpportunityScoreBadge";

type Props = {
  row: OpportunityScanRow | null;
  tickerSignal?: MicTickerSignal | null;
  onClose: () => void;
};

function ListSection({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) {
    return (
      <div className="os-drawer-section">
        <h4>{title}</h4>
        <p className="muted-text">—</p>
      </div>
    );
  }
  return (
    <div className="os-drawer-section">
      <h4>{title}</h4>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export default function OpportunityDetailDrawer({ row, tickerSignal, onClose }: Props) {
  if (!row) return null;
  const detail = row.reason_json ?? {};

  return (
    <>
      <div className="os-drawer-backdrop" onClick={onClose} aria-hidden />
      <aside className="os-drawer" role="dialog" aria-label={`${row.symbol} opportunity detail`}>
        <div className="panel-header">
          <h3>{row.symbol}</h3>
          <button type="button" className="qqq-btn" onClick={onClose}>Close</button>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
          <DirectionCandidateBadge direction={row.direction_candidate} />
          <span>Opportunity <OpportunityScoreBadge score={row.opportunity_score} /></span>
          <span className={readinessBadgeClass(row.trade_readiness ?? "Needs Analyze Live")}>
            {row.trade_readiness ?? "Needs Analyze Live"}
          </span>
          <span className="muted-text">Bull {row.bull_score.toFixed(0)} / Bear {row.bear_score.toFixed(0)}</span>
        </div>
        {row.market_context && <p className="muted-text">{row.market_context}</p>}

        <div className="os-drawer-section">
          <h4>Ticker News Signal</h4>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center", marginBottom: "0.35rem" }}>
            {tickerSignal && <span className={biasClass(tickerSignal.news_bias)}>{tickerSignal.news_bias}</span>}
            {tickerSignal && <span className={confidenceClass(tickerSignal.confidence)}>{tickerSignal.confidence} confidence</span>}
            <span className="muted-text">Quality {(row.news_quality_score ?? 0).toFixed(0)}</span>
            <span className="muted-text">Catalyst Strength {(row.catalyst_strength_score ?? 0).toFixed(0)}</span>
          </div>
          {tickerSignal && (
            <p className="muted-text">
              Bullish {tickerSignal.bullish_count} / Bearish {tickerSignal.bearish_count} / Neutral {tickerSignal.neutral_count}
            </p>
          )}
          {row.top_risk && <p><strong>Top risk:</strong> {row.top_risk}</p>}
        </div>

        <ListSection title="Bull Evidence" items={detail.bull_evidence} />
        <ListSection title="Bear Evidence" items={detail.bear_evidence} />
        <ListSection title="Risk Factors" items={detail.risk_factors} />

        <div className="os-drawer-section">
          <h4>News Summary</h4>
          <p>{detail.news_summary ?? (row.has_news_data ? "News cached" : "News data unavailable. News not used in score.")}</p>
        </div>
        <div className="os-drawer-section">
          <h4>Technical Summary</h4>
          <p>{detail.technical_summary ?? (row.has_analyzer_snapshot ? "—" : "Technical data unavailable. Run analysis for this symbol.")}</p>
        </div>
        <div className="os-drawer-section">
          <h4>Liquidity Summary</h4>
          <p>{detail.liquidity_summary ?? (row.has_options_data ? "—" : "Options liquidity unavailable.")}</p>
        </div>
        <div className="os-drawer-section">
          <h4>Market Regime Context</h4>
          <p>{detail.regime_context ?? row.market_context ?? "—"}</p>
        </div>
        <div className="os-drawer-section">
          <h4>Data Availability</h4>
          <ul>
            <li>Analyzer snapshot: {row.has_analyzer_snapshot ? "Yes" : "No — run analysis"}</li>
            <li>Options data: {row.has_options_data ? "Yes" : "No"}</li>
            <li>News data: {row.has_news_data ? "Yes" : "No"}</li>
          </ul>
        </div>

        <Link
          href={`/options-spread-strategy?symbol=${encodeURIComponent(row.symbol)}`}
          className="qqq-btn qqq-btn-primary"
        >
          Open in Options Spread Strategy
        </Link>
        <p className="os-disclaimer" style={{ marginTop: "0.5rem" }}>
          Direction Candidate only. Final strategy decisions are made by the Trade Decision Engine on the analyzer page.
        </p>
      </aside>
    </>
  );
}
