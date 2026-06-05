"use client";

import { useEffect, useState } from "react";

import { getPositions } from "@/lib/api";
import type { PositionsResponse } from "@/types";

export default function PositionsPage() {
  const [data, setData] = useState<PositionsResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void getPositions()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load positions"));
  }, []);

  const rows = data?.positions ?? [];

  return (
    <main className="container page-stack">
      <section className="panel">
        <h2 className="panel-title">Positions</h2>
        <p className="muted-text">
          Open paper positions linked to original decisions and trade plans.
          {data ? <> Account: <span className="mono">{data.account_id}</span></> : null}
        </p>
        {error ? <div className="banner banner-danger">{error}</div> : null}
        {!rows.length && !error ? (
          <p className="muted-text">No open paper positions. Run a saved decision through Paper Trading to create a position.</p>
        ) : null}
        <div className="table-wrap">
          <table className="dense-table">
            <thead>
              <tr>
                <th>Decision</th>
                <th>Symbol</th>
                <th>Strategy</th>
                <th>Direction</th>
                <th>Qty</th>
                <th>Avg</th>
                <th>Current</th>
                <th>P/L</th>
                <th>P/L %</th>
                <th>Max DD</th>
                <th>DTE</th>
                <th>Entry Trigger</th>
                <th>Invalidation</th>
                <th>Profit Plan</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.decision_id ?? row.ticker}-${row.qty}`}>
                  <td className="mono">{row.decision_id ? row.decision_id.slice(0, 8) : "-"}</td>
                  <td className="mono">{row.ticker}</td>
                  <td>{row.strategy_label ?? "-"}</td>
                  <td>{row.direction ?? "-"}</td>
                  <td>{row.qty}</td>
                  <td>{row.avg_price ?? "-"}</td>
                  <td>{row.current_price ?? row.last_price ?? "-"}</td>
                  <td className={row.pnl_total >= 0 ? "success-text" : "danger-text"}>{row.pnl_total.toFixed(2)}</td>
                  <td className={row.pnl_total >= 0 ? "success-text" : "danger-text"}>{(row.pnl_percent ?? 0).toFixed(1)}%</td>
                  <td>{(row.max_drawdown ?? 0).toFixed(1)}%</td>
                  <td>{row.dte ?? "-"}</td>
                  <td>{row.entry_trigger ?? "-"}</td>
                  <td>{row.invalidation_rule ?? "-"}</td>
                  <td>{row.profit_plan ?? "-"}</td>
                  <td className="mono">{row.current_action ?? "hold"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
