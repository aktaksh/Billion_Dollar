import { getBlotter } from "@/lib/api";

export default async function BlotterPage() {
  const rows = await getBlotter();

  return (
    <main className="grid">
      <section className="card">
        <h2 className="title-blue" style={{ marginTop: 0 }}>
          Blotter
        </h2>
        <p style={{ marginTop: 0 }}>Order intent timeline with status, fills, fees, and slippage.</p>
        <table>
          <thead>
            <tr>
              <th>Order Intent</th>
              <th>Ticker</th>
              <th>Status</th>
              <th>Broker IDs</th>
              <th>Fees</th>
              <th>Slippage</th>
              <th>Last Update</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7}>No blotter rows yet.</td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.order_intent_id}>
                  <td className="mono">{row.order_intent_id}</td>
                  <td>{row.ticker}</td>
                  <td>{row.status}</td>
                  <td className="mono">{row.broker_order_ids.join(", ") || "-"}</td>
                  <td>{row.fees_usd.toFixed(2)}</td>
                  <td>{row.slippage_vs_expected_usd.toFixed(2)}</td>
                  <td>{new Date(row.last_update_ts).toLocaleString()}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}
