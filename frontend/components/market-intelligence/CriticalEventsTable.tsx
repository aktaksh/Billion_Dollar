import type { MicCriticalEvent } from "@/types/marketIntelligence";

type Props = { events: MicCriticalEvent[] };

function fmt(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function CriticalEventsTable({ events }: Props) {
  if (events.length === 0) {
    return (
      <p className="muted-text mic-empty">
        No Critical or High impact events in the current window. Run Standard or Deep refresh to fetch more headlines.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table className="qqq-table mic-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Event Type</th>
            <th>Headline</th>
            <th>Source</th>
            <th>Sentiment</th>
            <th>Importance</th>
            <th className="num">Impact</th>
            <th>Published At</th>
            <th>Related</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev, i) => (
            <tr key={`${ev.title}-${i}`}>
              <td>{ev.symbol}</td>
              <td>{ev.eventType}</td>
              <td className="mic-title-cell">{ev.title}</td>
              <td>{ev.source}</td>
              <td>{ev.sentiment}</td>
              <td><span className={`mic-imp mic-imp-${ev.importance.toLowerCase()}`}>{ev.importance}</span></td>
              <td className="num">{ev.impactScore.toFixed(3)}</td>
              <td>{fmt(ev.publishedAt)}</td>
              <td>{(ev.relatedSymbols ?? []).join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
