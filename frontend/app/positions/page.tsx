import { getPositions } from "@/lib/api";

export default async function PositionsPage() {
  const data = await getPositions();

  return (
    <main className="grid">
      <section className="card">
        <h2 className="title-green" style={{ marginTop: 0 }}>
          Positions
        </h2>
        <p style={{ marginTop: 0 }}>Account: <span className="mono">{data.account_id}</span></p>
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Strategy</th>
              <th>Qty</th>
              <th>Avg Price</th>
              <th>PnL Total</th>
              <th>DTE</th>
              <th>Alerts</th>
            </tr>
          </thead>
          <tbody>
            {data.positions.length === 0 ? (
              <tr>
                <td colSpan={7}>No open positions.</td>
              </tr>
            ) : (
              data.positions.map((row) => (
                <tr key={`${row.ticker}-${row.qty}`}>
                  <td className="text-white">{row.ticker}</td>
                  <td>{row.strategy_label ?? "-"}</td>
                  <td>{row.qty}</td>
                  <td>{row.avg_price ?? "-"}</td>
                  <td className={row.pnl_total >= 0 ? "text-green" : "text-red"}>{row.pnl_total.toFixed(2)}</td>
                  <td>{row.dte ?? "-"}</td>
                  <td>{row.alerts.length ? row.alerts.join(", ") : "none"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}
