"use client";

import Link from "next/link";

import type { OpportunityScanRow } from "@/types/opportunityScanner";

import DirectionCandidateBadge, { OpportunityScoreBadge, scoreClass } from "./OpportunityScoreBadge";

type Props = {
  rows: OpportunityScanRow[];
  onSelect: (row: OpportunityScanRow) => void;
};

function TechnicalConfidenceBadge({ confidence, hint }: { confidence?: string; hint?: string | null }) {
  const label = confidence || "Not Evaluated";
  let cls = "os-tech-badge os-tech-not-evaluated";
  if (label === "Fresh") cls = "os-tech-badge os-tech-fresh";
  else if (label === "Stale") cls = "os-tech-badge os-tech-stale";
  return (
    <span className={cls} title={hint || undefined}>
      {label}
    </span>
  );
}

export default function OpportunityTable({ rows, onSelect }: Props) {
  if (rows.length === 0) {
    return (
      <section className="panel">
        <p className="qqq-empty">No symbols match the current filters.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Opportunity Rankings</h2>
        <span className="muted-text">{rows.length} symbols</span>
      </div>
      <div className="table-wrap">
        <table className="qqq-table os-table-compact">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Symbol</th>
              <th>Direction</th>
              <th className="num">Market Opportunity</th>
              <th>Technical</th>
              <th className="num">Bull</th>
              <th className="num">Bear</th>
              <th className="num">Confidence</th>
              <th className="num">Risk</th>
              <th className="num">News</th>
              <th>Next Earnings</th>
              <th>Top Catalyst</th>
              <th>Reason</th>
              <th>Analyze Live</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.symbol} className="os-row-clickable" onClick={() => onSelect(row)}>
                <td>{row.rank}</td>
                <td><strong>{row.symbol}</strong></td>
                <td><DirectionCandidateBadge direction={row.direction_candidate} /></td>
                <td className="num">
                  <OpportunityScoreBadge score={row.market_opportunity_score ?? row.opportunity_score} />
                </td>
                <td>
                  <TechnicalConfidenceBadge
                    confidence={row.technical_confidence}
                    hint={row.technical_hint}
                  />
                </td>
                <td className={`num ${scoreClass(row.bull_score)}`}>{row.bull_score.toFixed(0)}</td>
                <td className={`num ${scoreClass(row.bear_score)}`}>{row.bear_score.toFixed(0)}</td>
                <td className="num">{row.confidence_score.toFixed(0)}</td>
                <td className={`num ${scoreClass(row.risk_score, true)}`}>{row.risk_score.toFixed(0)}</td>
                <td className="num">{row.news_score.toFixed(0)}</td>
                <td>{row.next_earnings ?? "—"}</td>
                <td>{row.top_catalyst ? row.top_catalyst.slice(0, 40) : "—"}</td>
                <td className="reason-cell muted-text">{row.reason}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  <Link
                    href={`/options-spread-strategy?symbol=${encodeURIComponent(row.symbol)}&autorun=true`}
                    className="qqq-btn qqq-btn-primary"
                    style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
                  >
                    Analyze Live
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
