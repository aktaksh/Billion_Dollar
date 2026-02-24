import Link from "next/link";

import { getTradeCard } from "@/lib/api";

type Props = {
  params: Promise<{ ticker: string }>;
};

export default async function TradeCardPage({ params }: Props) {
  const { ticker } = await params;
  const card = await getTradeCard(ticker);

  return (
    <main className="grid" style={{ gap: 16 }}>
      <section className="card">
        <p style={{ marginTop: 0 }}>
          <Link href="/">Back to Watchlist</Link>
        </p>
        <h2 className="title-blue" style={{ marginTop: 0 }}>
          Trade Card: {card.ticker}
        </h2>
        <div className="grid grid-3">
          <div className="card">
            <div className="subtle">State</div>
            <div className="mono text-white">{card.state}</div>
          </div>
          <div className="card">
            <div className="subtle">Confidence</div>
            <div className={card.confidence_total >= 70 ? "mono text-green" : "mono text-red"}>
              {card.confidence_total.toFixed(1)}
            </div>
          </div>
          <div className="card">
            <div className="subtle">Last Price</div>
            <div className="mono text-white">{card.last_price ?? "-"}</div>
          </div>
        </div>
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Thesis</h3>
        <pre className="mono">{JSON.stringify(card.thesis, null, 2)}</pre>
        <h3>Why now</h3>
        <ul>
          {card.why_now_deltas.map((line, idx) => (
            <li key={`${line}-${idx}`}>{line}</li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Warnings</h3>
        {card.warnings.length ? (
          <ul>
            {card.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        ) : (
          <p>None</p>
        )}
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Recent Events</h3>
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>When</th>
              <th>Aggregate</th>
            </tr>
          </thead>
          <tbody>
            {card.recent_events.length === 0 ? (
              <tr>
                <td colSpan={3}>No recent events for this ticker.</td>
              </tr>
            ) : (
              card.recent_events.map((event) => (
                <tr key={event.event_id}>
                  <td>{event.event_type}</td>
                  <td>{new Date(event.occurred_at).toLocaleString()}</td>
                  <td className="mono">{event.aggregate_id}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}
