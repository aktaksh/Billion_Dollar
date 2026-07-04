import type { MicActivityRow } from "@/types/marketIntelligence";

type Props = { rows: MicActivityRow[] };

export default function RefreshActivityLog({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <p className="muted-text mic-empty">
        No refresh activity logged yet. Activity appears in news_fetch_log after Quick, Standard, or Deep refresh.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table className="qqq-table mic-table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Mode</th>
            <th>Provider</th>
            <th className="num">Planned</th>
            <th className="num">Executed</th>
            <th className="num">Skipped</th>
            <th className="num">Saved</th>
            <th>Errors</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.timestamp}-${r.provider}-${i}`}>
              <td>{r.timestamp ? new Date(r.timestamp).toLocaleString() : "—"}</td>
              <td>{r.mode}</td>
              <td>{r.provider}</td>
              <td className="num">{r.calls_planned ?? "—"}</td>
              <td className="num">{r.calls_executed}</td>
              <td className="num">{r.calls_skipped}</td>
              <td className="num">{r.items_saved}</td>
              <td className="mic-error-cell">{r.errors ?? "—"}</td>
              <td>{r.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
