import type { QqqSpreadAnalysis } from "@/types/qqqSpreadAnalyzer";

type Props = { data: QqqSpreadAnalysis };

function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(digits);
}

function Badge({ ok }: { ok: boolean }) {
  return <span className={ok ? "badge-yes" : "badge-no"}>{ok ? "yes" : "no"}</span>;
}

export default function DailyIndicatorsPanel({ data }: Props) {
  const d = data.daily_indicators;
  const checks = data.score.daily_checks;

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Daily Indicators</h2>
      </div>
      <div className="table-wrap">
        <table className="qqq-table">
          <tbody>
            <tr><th>Close</th><td className="num">{fmt(d.close)}</td></tr>
            <tr><th>EMA20</th><td className="num">{fmt(d.ema20)}</td></tr>
            <tr><th>EMA50</th><td className="num">{fmt(d.ema50)}</td></tr>
            <tr><th>SMA200</th><td className="num">{fmt(d.sma200)}</td></tr>
            <tr><th>RSI14</th><td className="num">{fmt(d.rsi14)}</td></tr>
            <tr><th>MACD line</th><td className="num">{fmt(d.macd_line, 3)}</td></tr>
            <tr><th>MACD signal</th><td className="num">{fmt(d.macd_signal, 3)}</td></tr>
            <tr><th>MACD histogram</th><td className="num">{fmt(d.macd_hist, 3)}</td></tr>
            <tr><th>ATR14</th><td className="num">{fmt(d.atr14)}</td></tr>
            <tr><th>BB upper</th><td className="num">{fmt(d.bb_upper)}</td></tr>
            <tr><th>BB middle</th><td className="num">{fmt(d.bb_mid)}</td></tr>
            <tr><th>BB lower</th><td className="num">{fmt(d.bb_lower)}</td></tr>
          </tbody>
        </table>
      </div>
      <div className="table-wrap" style={{ marginTop: "0.75rem" }}>
        <table className="qqq-table">
          <thead>
            <tr><th>Check</th><th>Status</th></tr>
          </thead>
          <tbody>
            {Object.entries(checks).map(([key, val]) => (
              <tr key={key}>
                <td>{key.replaceAll("_", " ")}</td>
                <td><Badge ok={val} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
