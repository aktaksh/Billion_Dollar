import type { QqqSpreadAnalysis } from "@/types/qqqSpreadAnalyzer";

type Props = { data: QqqSpreadAnalysis };

function rejectionHints(data: QqqSpreadAnalysis): string[] {
  const hints: string[] = [];
  if (data.risk_notes?.length) {
    hints.push(...data.risk_notes);
  }
  if (data.score.invalid_conditions.length) {
    hints.push(...data.score.invalid_conditions);
  }
  const diag = data.diagnostics;
  if ((diag.liquid_quotes ?? 0) === 0 && (diag.raw_quotes ?? 0) > 0) {
    hints.push("Wide bid/ask spread, low open interest, or low volume may have filtered all legs");
  }
  if ((diag.raw_quotes ?? 0) === 0) {
    hints.push("No raw option quotes received");
  }
  for (const fail of diag.qualification_failures ?? []) {
    hints.push(
      `${fail.failed_count} contracts failed qualification for expiry ${fail.expiry}. ${fail.reason_hint}`,
    );
  }
  return [...new Set(hints)];
}

export default function SpreadCandidatesTable({ data }: Props) {
  const rows = data.spread_candidates;
  const hints = rejectionHints(data);

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Spread Candidates</h2>
      </div>
      {rows.length === 0 ? (
        <>
          <p className="qqq-empty">No spread candidates passed filters.</p>
          {hints.length > 0 && (
            <ul className="qqq-muted-list">
              {hints.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="table-wrap">
          <table className="qqq-table">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Expiry</th>
                <th>DTE</th>
                <th>Long</th>
                <th>Short</th>
                <th className="num">Debit</th>
                <th className="num">Max loss</th>
                <th className="num">Max profit</th>
                <th className="num">BE</th>
                <th className="num">R/R</th>
                <th className="num">Δ</th>
                <th className="num">Θ</th>
                <th className="num">Liq</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={`${row.expiry}-${row.long_leg}-${idx}`}>
                  <td>{row.strategy}</td>
                  <td>{row.expiry}</td>
                  <td>{row.dte}</td>
                  <td>{row.long_leg}</td>
                  <td>{row.short_leg}</td>
                  <td className="num">{row.net_debit.toFixed(2)}</td>
                  <td className="num">{row.max_loss.toFixed(0)}</td>
                  <td className="num">{row.max_profit.toFixed(0)}</td>
                  <td className="num">{row.breakeven.toFixed(2)}</td>
                  <td className="num">{row.reward_risk.toFixed(2)}</td>
                  <td className="num">{row.combined_delta.toFixed(2)}</td>
                  <td className="num">{row.combined_theta.toFixed(2)}</td>
                  <td className="num">{row.liquidity_score.toFixed(0)}</td>
                  <td><span className="badge-yes">{row.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
