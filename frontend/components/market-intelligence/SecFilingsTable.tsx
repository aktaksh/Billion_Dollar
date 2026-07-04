import type { MicSecFiling } from "@/types/marketIntelligence";

type Props = { rows: MicSecFiling[] };

export default function SecFilingsTable({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <p className="muted-text mic-empty">
        No SEC filings in database. Run Standard or Deep refresh — ETFs are skipped for SEC.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table className="qqq-table mic-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Form</th>
            <th>Filed Date</th>
            <th>Description</th>
            <th>Importance</th>
            <th>Link</th>
            <th className="num">Impact</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.symbol}-${r.form}-${i}`}>
              <td>{r.symbol}</td>
              <td>{r.form}</td>
              <td>{r.filed_date ? new Date(r.filed_date).toLocaleDateString() : "—"}</td>
              <td className="mic-title-cell">{r.description}</td>
              <td>{r.importance}</td>
              <td>{r.link ? <a href={r.link} target="_blank" rel="noreferrer">SEC</a> : "—"}</td>
              <td className="num">{r.impact_score.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
