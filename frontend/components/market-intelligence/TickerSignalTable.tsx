import type { MicTickerSignal } from "@/types/marketIntelligence";

type Props = {
  rows: MicTickerSignal[];
  onSelect: (row: MicTickerSignal) => void;
};

export function biasClass(bias: string): string {
  const b = bias.toLowerCase();
  if (b === "bullish") return "mic-bias-badge mic-bias-bullish";
  if (b === "bearish") return "mic-bias-badge mic-bias-bearish";
  return "mic-bias-badge mic-bias-neutral";
}

export function confidenceClass(confidence: string): string {
  const c = confidence.toLowerCase();
  if (c === "high") return "mic-conf-badge mic-conf-high";
  if (c === "medium") return "mic-conf-badge mic-conf-medium";
  return "mic-conf-badge mic-conf-low";
}

function fmt(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function TickerSignalTable({ rows, onSelect }: Props) {
  if (rows.length === 0) {
    return (
      <p className="muted-text mic-empty">
        No ticker-level news signals yet. Run Quick, Standard, or Deep refresh to build them.
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table className="qqq-table mic-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>News Bias</th>
            <th className="num">Quality</th>
            <th className="num">Catalyst Strength</th>
            <th className="num">Net Impact</th>
            <th className="num">Bull / Bear / Neutral</th>
            <th>Top Catalyst</th>
            <th>Top Risk</th>
            <th>Confidence</th>
            <th>Last Updated</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className="mic-row-clickable" onClick={() => onSelect(r)}>
              <td><strong>{r.symbol}</strong></td>
              <td><span className={biasClass(r.news_bias)}>{r.news_bias}</span></td>
              <td className="num">{r.news_quality_score.toFixed(0)}</td>
              <td className="num">{r.catalyst_strength_score.toFixed(0)}</td>
              <td className="num">{r.net_impact_score.toFixed(0)}</td>
              <td className="num">{r.bullish_count} / {r.bearish_count} / {r.neutral_count}</td>
              <td className="mic-catalyst-cell">{r.top_catalyst ?? "—"}</td>
              <td className="mic-risk-cell">{r.top_risk ?? "—"}</td>
              <td><span className={confidenceClass(r.confidence)}>{r.confidence}</span></td>
              <td>{fmt(r.last_updated)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted-text mic-footnote">Click a row for the full ticker detail, including raw source articles.</p>
    </div>
  );
}
