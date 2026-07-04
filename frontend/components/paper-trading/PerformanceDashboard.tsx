import type { PaperTradeAnalytics } from "@/types/paperTrading";

type Props = { analytics: PaperTradeAnalytics | null };

export default function PerformanceDashboard({ analytics }: Props) {
  if (!analytics) return null;

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Performance</h2>
      </div>
      <div className="pt-metrics-row">
        <div className="pt-metric">
          <span className="pt-metric-label">Profit factor</span>
          <strong>{analytics.profit_factor.toFixed(2)}</strong>
        </div>
        <div className="pt-metric">
          <span className="pt-metric-label">Gross profit</span>
          <strong className="pt-pnl-pos">${analytics.gross_profit.toFixed(2)}</strong>
        </div>
        <div className="pt-metric">
          <span className="pt-metric-label">Gross loss</span>
          <strong className="pt-pnl-neg">${analytics.gross_loss.toFixed(2)}</strong>
        </div>
      </div>
      {analytics.strategy_breakdown.length > 0 && (
        <>
          <h3 className="pt-subtitle">By strategy</h3>
          <div className="table-wrap">
            <table className="qqq-table">
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th className="num">Trades</th>
                  <th className="num">Win %</th>
                  <th className="num">Total PnL</th>
                </tr>
              </thead>
              <tbody>
                {analytics.strategy_breakdown.map((row) => (
                  <tr key={row.strategy_type}>
                    <td>{row.strategy_type}</td>
                    <td className="num">{row.count}</td>
                    <td className="num">{row.win_rate.toFixed(1)}%</td>
                    <td className="num">${row.total_pnl.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {analytics.monthly_returns.length > 0 && (
        <>
          <h3 className="pt-subtitle">Monthly returns</h3>
          <div className="table-wrap">
            <table className="qqq-table">
              <thead>
                <tr>
                  <th>Month</th>
                  <th className="num">PnL</th>
                </tr>
              </thead>
              <tbody>
                {analytics.monthly_returns.map((row) => (
                  <tr key={row.month}>
                    <td>{row.month}</td>
                    <td className="num">${row.pnl.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
