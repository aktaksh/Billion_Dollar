import type { OpportunityScannerPayload } from "@/types/opportunityScanner";

import DirectionCandidateBadge from "./OpportunityScoreBadge";

type Props = { summary: OpportunityScannerPayload["summary"] };

function Card({ label, row }: { label: string; row: { symbol: string; opportunity_score?: number; direction_candidate?: string } | null }) {
  if (!row) {
    return (
      <div className="os-card">
        <div className="os-card-label">{label}</div>
        <div className="os-card-value muted-text">—</div>
      </div>
    );
  }
  return (
    <div className="os-card">
      <div className="os-card-label">{label}</div>
      <div className="os-card-value">{row.symbol}</div>
      <div style={{ marginTop: "0.25rem", display: "flex", gap: "0.4rem", alignItems: "center" }}>
        {row.direction_candidate && <DirectionCandidateBadge direction={row.direction_candidate} />}
        {row.opportunity_score != null && (
          <span className="num">{row.opportunity_score.toFixed(0)}</span>
        )}
      </div>
    </div>
  );
}

export default function OpportunitySummaryCards({ summary }: Props) {
  return (
    <section className="panel os-section">
      <h2 className="panel-title">Summary</h2>
      <div className="os-cards-grid">
        <Card label="Best Bullish Candidate" row={summary.best_bullish} />
        <Card label="Best Bearish Candidate" row={summary.best_bearish} />
        <Card label="Highest Opportunity" row={summary.highest_opportunity} />
        <Card label="Highest Risk Symbol" row={summary.highest_risk} />
        <div className="os-card">
          <div className="os-card-label">Symbols Scanned</div>
          <div className="os-card-value">{summary.symbols_scanned}</div>
          <div className="muted-text" style={{ fontSize: "0.75rem", marginTop: "0.2rem" }}>
            {summary.bullish_count} bull · {summary.bearish_count} bear · {summary.neutral_count} neutral
          </div>
        </div>
        <div className="os-card">
          <div className="os-card-label">Data Quality</div>
          <div className="os-card-value">{summary.data_quality}</div>
        </div>
      </div>
    </section>
  );
}
