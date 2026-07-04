import type { MicNewsSignalOutput } from "@/types/marketIntelligence";

type Props = { output: MicNewsSignalOutput };

export default function NewsSignalOutputPanel({ output }: Props) {
  const p = output.primary;

  return (
    <>
      <div className="mic-signal-primary">
        <div className="mic-cards-grid mic-cards-6">
          <article className="mic-card"><div className="mic-card-label">Symbol</div><div className="mic-card-value">{p.symbol}</div></article>
          <article className="mic-card"><div className="mic-card-label">News Score</div><div className="mic-card-value">{p.news_score_0_to_100}</div></article>
          <article className="mic-card"><div className="mic-card-label">Sentiment</div><div className="mic-card-value">{p.label}</div></article>
          <article className="mic-card"><div className="mic-card-label">Confidence</div><div className="mic-card-value">{p.confidence}</div></article>
          <article className="mic-card"><div className="mic-card-label">Critical Events</div><div className="mic-card-value">{p.critical_event_count}</div></article>
          <article className="mic-card"><div className="mic-card-label">Last Updated</div><div className="mic-card-value mic-card-value-sm">{p.last_updated ? new Date(p.last_updated).toLocaleString() : "—"}</div></article>
        </div>
        {p.top_catalyst && <p className="mic-catalyst-line"><strong>Top catalyst:</strong> {p.top_catalyst}</p>}
        {p.top_risk_event && <p className="mic-catalyst-line"><strong>Top risk:</strong> {p.top_risk_event}</p>}
      </div>

      <p className="muted-text mic-consumers">
        Consumed by (planned): {output.consumers.join(", ")}. TDE still uses risk_notes heuristic until wired.
      </p>

      {output.watchlist_signals.length > 0 && (
        <div className="table-wrap">
          <table className="qqq-table mic-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th className="num">Score</th>
                <th>Sentiment</th>
                <th>Confidence</th>
                <th className="num">Critical</th>
              </tr>
            </thead>
            <tbody>
              {output.watchlist_signals.map((s) => (
                <tr key={s.symbol}>
                  <td>{s.symbol}</td>
                  <td className="num">{s.news_score_0_to_100}</td>
                  <td>{s.label}</td>
                  <td>{s.confidence}</td>
                  <td className="num">{s.critical_event_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
