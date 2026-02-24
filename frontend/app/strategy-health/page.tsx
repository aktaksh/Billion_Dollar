import { getStrategyHealth } from "@/lib/api";

export default async function StrategyHealthPage() {
  const rows = await getStrategyHealth();

  return (
    <main className="grid">
      <section className="card">
        <h2 className="title-green" style={{ marginTop: 0 }}>
          Strategy Health
        </h2>
        <p style={{ marginTop: 0 }}>
          Expectancy after costs segmented by sleeve, regime, and trading mode.
        </p>
        <table>
          <thead>
            <tr>
              <th>Sleeve</th>
              <th>Regime</th>
              <th>Mode</th>
              <th>Trades</th>
              <th>Win Rate</th>
              <th>Expectancy</th>
              <th>Payoff</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={`${row.strategy_sleeve}-${row.regime_label}-${idx}`}>
                <td>{row.strategy_sleeve}</td>
                <td>{row.regime_label}</td>
                <td>{row.trading_mode}</td>
                <td>{row.trades}</td>
                <td className={row.win_rate >= 0.5 ? "text-green" : "text-red"}>{(row.win_rate * 100).toFixed(1)}%</td>
                <td className={row.expectancy_after_costs_usd >= 0 ? "text-green" : "text-red"}>
                  ${row.expectancy_after_costs_usd.toFixed(2)}
                </td>
                <td>{Number.isFinite(row.payoff_ratio) ? row.payoff_ratio.toFixed(2) : "inf"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}


