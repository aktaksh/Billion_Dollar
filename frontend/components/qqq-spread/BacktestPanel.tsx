import type { QqqSpreadAnalysis } from "@/types/qqqSpreadAnalyzer";

type Props = { data: QqqSpreadAnalysis };

export default function BacktestPanel({ data }: Props) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Backtest / Forward Test</h2>
      </div>
      {data.backtest.available ? (
        <p>Backtest data available.</p>
      ) : (
        <p className="qqq-empty">{data.backtest.message}</p>
      )}
    </section>
  );
}
