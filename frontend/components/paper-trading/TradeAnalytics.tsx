import type { PaperTradeSnapshot } from "@/types/paperTrading";

type Props = { snapshots: PaperTradeSnapshot[] };

function Sparkline({ values, height = 48 }: { values: number[]; height?: number }) {
  if (values.length < 2) return <p className="muted-text">Not enough marks for chart yet.</p>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 280;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="pt-sparkline" role="img" aria-label="Time series">
      <polyline fill="none" stroke="currentColor" strokeWidth="2" points={points} />
    </svg>
  );
}

export default function TradeAnalytics({ snapshots }: Props) {
  const underlying = snapshots.map((s) => s.underlying_price ?? 0);
  const spread = snapshots.map((s) => s.spread_value ?? 0);
  const pnl = snapshots.map((s) => s.unrealized_pnl ?? 0);

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Mark history</h2>
        <span className="muted-text">{snapshots.length} snapshot{snapshots.length === 1 ? "" : "s"}</span>
      </div>
      <div className="pt-chart-grid">
        <div>
          <div className="pt-chart-label">Underlying</div>
          <Sparkline values={underlying} />
        </div>
        <div>
          <div className="pt-chart-label">Spread value</div>
          <Sparkline values={spread} />
        </div>
        <div>
          <div className="pt-chart-label">Unrealized PnL</div>
          <Sparkline values={pnl} />
        </div>
      </div>
    </section>
  );
}
