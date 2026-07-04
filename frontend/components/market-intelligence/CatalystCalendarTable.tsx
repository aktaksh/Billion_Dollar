import type { MicCatalystRow } from "@/types/marketIntelligence";

type Props = { rows: MicCatalystRow[] };

export default function CatalystCalendarTable({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <p className="muted-text mic-empty">
        No upcoming catalysts in calendar. Macro events appear from CatalystCalendarService when regime data is available.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table className="qqq-table mic-table">
        <thead>
          <tr>
            <th>Event</th>
            <th>Symbol</th>
            <th>Date</th>
            <th>Time</th>
            <th>Expected Impact</th>
            <th>Risk Level</th>
            <th className="num">Countdown</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.event}-${i}`}>
              <td>{r.event}</td>
              <td>{r.symbol}</td>
              <td>{r.date ?? "—"}</td>
              <td>{r.time}</td>
              <td>{r.expected_impact}</td>
              <td>{r.risk_level}</td>
              <td className="num">{r.countdown_days ?? "—"}</td>
              <td>{r.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
