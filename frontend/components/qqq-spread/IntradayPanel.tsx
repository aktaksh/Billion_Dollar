import type { QqqSpreadAnalysis } from "@/types/qqqSpreadAnalyzer";

type Props = { data: QqqSpreadAnalysis };

function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(digits);
}

function Badge({ ok }: { ok: boolean }) {
  return <span className={ok ? "badge-yes" : "badge-no"}>{ok ? "yes" : "no"}</span>;
}

export default function IntradayPanel({ data }: Props) {
  const d = data.intraday_indicators;
  const checks = data.score.intraday_checks;
  const tf = data.diagnostics.intraday_timeframe ?? "2h";

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Intraday Timing ({tf})</h2>
      </div>
      <div className="table-wrap">
        <table className="qqq-table">
          <tbody>
            <tr><th>Close</th><td className="num">{fmt(d.close)}</td></tr>
            <tr><th>EMA9</th><td className="num">{fmt(d.ema9)}</td></tr>
            <tr><th>EMA21</th><td className="num">{fmt(d.ema21)}</td></tr>
            <tr><th>RSI14</th><td className="num">{fmt(d.rsi14)}</td></tr>
            <tr><th>MACD line</th><td className="num">{fmt(d.macd_line, 3)}</td></tr>
            <tr><th>MACD signal</th><td className="num">{fmt(d.macd_signal, 3)}</td></tr>
            <tr><th>MACD histogram</th><td className="num">{fmt(d.macd_hist, 3)}</td></tr>
            <tr><th>ATR14</th><td className="num">{fmt(d.atr14)}</td></tr>
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
