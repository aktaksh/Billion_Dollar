import type { NewsTopEvent } from "@/types/newsIntelligence";

type Props = {
  events: NewsTopEvent[];
  emptyMessage?: string;
};

function formatPublished(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function NewsEventsTable({ events, emptyMessage = "No events to display." }: Props) {
  if (events.length === 0) {
    return <p className="muted-text ni-empty-msg">{emptyMessage}</p>;
  }

  return (
    <div className="table-wrap">
      <table className="qqq-table ni-events-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Event Type</th>
            <th>Title</th>
            <th>Source</th>
            <th>Sentiment</th>
            <th>Importance</th>
            <th className="num">Impact</th>
            <th>Published At</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev, idx) => (
            <tr key={`${ev.title}-${idx}`}>
              <td>{ev.symbol}</td>
              <td>{ev.eventType}</td>
              <td className="ni-event-title">{ev.title}</td>
              <td>{ev.source}</td>
              <td>{ev.sentiment}</td>
              <td>
                <span className={`ni-importance ni-importance-${ev.importance.toLowerCase()}`}>{ev.importance}</span>
              </td>
              <td className="num">{ev.impactScore.toFixed(3)}</td>
              <td>{formatPublished(ev.publishedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
