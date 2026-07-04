"use client";

type ExpiryRanking = {
  expiry: string;
  dte: number;
  bucket: string;
  score: number;
  liquidity: number;
  valid_strikes: number;
  liquid_quotes: number;
  event_risk: boolean;
  status: string;
  reason: string;
};

type ExpirySearchData = {
  buckets_scanned?: string[];
  expiries_scanned?: number;
  best_expiry?: string | null;
  best_bucket?: string | null;
  expiry_rankings?: ExpiryRanking[];
  rejected_expiries?: Array<{
    expiry: string;
    dte: number;
    bucket: string;
    score: number;
    status: string;
    reason: string;
  }>;
  valid_spreads_count?: number;
  force_wait?: boolean;
  wait_reason?: string | null;
  no_candidate_reasons?: string[];
};

type Props = {
  expirySearch: ExpirySearchData | undefined;
};

function statusBadge(status: string) {
  const cls =
    status === "available"
      ? "qqq-badge-green"
      : status === "poor_liquidity"
        ? "qqq-badge-yellow"
        : "qqq-badge-red";
  return <span className={`qqq-badge ${cls}`}>{status}</span>;
}

export default function ExpiryRankingPanel({ expirySearch }: Props) {
  if (!expirySearch || !expirySearch.expiry_rankings?.length) {
    return (
      <section className="panel" style={{ padding: "16px" }}>
        <h2 className="panel-title">Expiry Search Results</h2>
        <p className="muted-text">No expiry search data available. Run analysis to generate.</p>
      </section>
    );
  }

  const {
    buckets_scanned = [],
    best_expiry,
    best_bucket,
    expiry_rankings = [],
    rejected_expiries = [],
    valid_spreads_count = 0,
    force_wait,
    wait_reason,
    no_candidate_reasons = [],
  } = expirySearch;

  return (
    <section className="panel" style={{ padding: "16px" }}>
      <div className="panel-header">
        <h2 className="panel-title">Expiry Search Results</h2>
        <span className="muted-text" style={{ fontSize: "0.8rem" }}>
          Buckets: {buckets_scanned.join(", ")}
        </span>
      </div>

      <div className="qqq-grid-3" style={{ marginTop: "0.75rem", marginBottom: "1rem" }}>
        <div className="card" style={{ padding: "10px" }}>
          <div className="muted-text" style={{ fontSize: "0.7rem" }}>Best Expiry</div>
          <div style={{ fontWeight: 600 }}>{best_expiry ?? "—"}</div>
        </div>
        <div className="card" style={{ padding: "10px" }}>
          <div className="muted-text" style={{ fontSize: "0.7rem" }}>Best Bucket</div>
          <div style={{ fontWeight: 600 }}>{best_bucket ?? "—"}</div>
        </div>
        <div className="card" style={{ padding: "10px" }}>
          <div className="muted-text" style={{ fontSize: "0.7rem" }}>Valid Spreads</div>
          <div style={{ fontWeight: 600 }}>{valid_spreads_count}</div>
        </div>
      </div>

      {force_wait && wait_reason && (
        <div className="qqq-regime-filter-wait" style={{ padding: "8px 12px", borderRadius: "6px", marginBottom: "0.75rem", fontSize: "0.8rem" }}>
          {wait_reason}
        </div>
      )}

      {no_candidate_reasons.length > 0 && !force_wait && (
        <div style={{ marginBottom: "0.75rem" }}>
          <strong style={{ fontSize: "0.8rem" }}>Rejection Reasons:</strong>
          <ul style={{ margin: "4px 0 0 16px", fontSize: "0.75rem" }}>
            {no_candidate_reasons.slice(0, 5).map((r, i) => (
              <li key={i} className="muted-text">{r}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="table-wrap">
        <table className="qqq-table">
          <thead>
            <tr>
              <th>Expiry</th>
              <th className="num">DTE</th>
              <th>Bucket</th>
              <th className="num">Score</th>
              <th className="num">Liquidity</th>
              <th className="num">Strikes</th>
              <th>Event Risk</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {expiry_rankings.map((e) => (
              <tr key={e.expiry} style={e.expiry === best_expiry ? { background: "rgba(34,197,94,0.08)" } : {}}>
                <td style={{ fontWeight: e.expiry === best_expiry ? 600 : 400 }}>{e.expiry}</td>
                <td className="num">{e.dte}</td>
                <td>{e.bucket}</td>
                <td className="num">{e.score.toFixed(1)}</td>
                <td className="num">{e.liquidity.toFixed(0)}</td>
                <td className="num">{e.valid_strikes}</td>
                <td>{e.event_risk ? "⚠️" : "—"}</td>
                <td>{statusBadge(e.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {rejected_expiries.length > 0 && (
        <details style={{ marginTop: "0.75rem" }}>
          <summary className="muted-text" style={{ fontSize: "0.8rem", cursor: "pointer" }}>
            Rejected Expiries ({rejected_expiries.length})
          </summary>
          <div className="table-wrap" style={{ marginTop: "0.5rem" }}>
            <table className="qqq-table">
              <thead>
                <tr>
                  <th>Expiry</th>
                  <th className="num">DTE</th>
                  <th>Bucket</th>
                  <th className="num">Score</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {rejected_expiries.map((e) => (
                  <tr key={e.expiry}>
                    <td>{e.expiry}</td>
                    <td className="num">{e.dte}</td>
                    <td>{e.bucket}</td>
                    <td className="num">{e.score.toFixed(1)}</td>
                    <td className="muted-text">{e.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}
