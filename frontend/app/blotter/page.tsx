"use client";

import { useEffect, useState } from "react";

import { getBlotter, patchDecision } from "@/lib/api";
import type { BlotterRow } from "@/types";

export default function BlotterPage() {
  const [rows, setRows] = useState<BlotterRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    void getBlotter()
      .then(setRows)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load blotter"));
  }, []);

  const sendToReview = async (decisionId: string | null | undefined) => {
    if (!decisionId) return;
    try {
      await patchDecision(decisionId, { review_status: "ready_for_review" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send to review");
    }
  };

  return (
    <main className="container page-stack">
      <section className="panel">
        <h2 className="panel-title">Blotter</h2>
        <p className="muted-text">Order intents linked to saved decisions with fills, fees, and slippage.</p>
        {error ? <div className="banner banner-danger">{error}</div> : null}
        {!rows.length && !error ? (
          <p className="muted-text">No blotter rows yet. Run a decision-based paper trade to create order intents.</p>
        ) : null}
        <div className="table-wrap">
          <table className="dense-table">
            <thead>
              <tr>
                <th>Decision</th>
                <th>Symbol</th>
                <th>Strategy</th>
                <th>Direction</th>
                <th>Status</th>
                <th>Broker Ref</th>
                <th>Fill</th>
                <th>Fees</th>
                <th>Slippage</th>
                <th>Created</th>
                <th>Updated</th>
                <th>Review</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.order_intent_id}>
                  <td className="mono">{row.decision_id ? row.decision_id.slice(0, 8) : "-"}</td>
                  <td>{row.ticker}</td>
                  <td>{row.strategy_type ?? row.structure_label ?? "-"}</td>
                  <td>{row.direction ?? "-"}</td>
                  <td>{row.status}</td>
                  <td className="mono">{row.broker_order_ids.join(", ") || "-"}</td>
                  <td className="mono">{row.fill_price != null ? row.fill_price.toFixed(2) : "-"}</td>
                  <td>{row.fees_usd.toFixed(2)}</td>
                  <td>{row.slippage_vs_expected_usd.toFixed(2)}</td>
                  <td>{new Date(row.created_ts).toLocaleString()}</td>
                  <td>{new Date(row.last_update_ts).toLocaleString()}</td>
                  <td>{row.review_status ?? "pending"}</td>
                  <td>
                    <div className="inline-form">
                      {row.decision_id ? (
                        <a className="ghost-button" href={`/decisions`}>View Decision</a>
                      ) : null}
                      <a className="ghost-button" href="/positions">View Position</a>
                      <button type="button" className="ghost-button" disabled={!row.decision_id} onClick={() => void sendToReview(row.decision_id)}>
                        Send to Review
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
