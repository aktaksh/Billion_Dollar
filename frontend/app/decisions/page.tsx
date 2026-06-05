"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import TradeCardDrawer from "@/components/TradeCardDrawer";
import {
  classifyReview,
  getDecisions,
  getTradeCard,
  patchDecision,
  runPaperTrade,
  runReplay,
} from "@/lib/api";
import { markDecisionRejected } from "@/lib/decisionHelpers";
import type { TradeCard, TradeDecision } from "@/types";

export default function DecisionsPage() {
  const router = useRouter();
  const [rows, setRows] = useState<TradeDecision[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [selected, setSelected] = useState<TradeDecision | null>(null);
  const [tradeCard, setTradeCard] = useState<TradeCard | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await getDecisions();
      setRows(data);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load decisions");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 15_000);
    return () => clearInterval(timer);
  }, [load]);

  const openDecision = async (row: TradeDecision) => {
    setSelected(row);
    setDrawerOpen(true);
    try {
      const card = await getTradeCard(row.symbol);
      setTradeCard(card);
    } catch {
      setTradeCard(null);
    }
  };

  const runAction = async (action: string, row: TradeDecision) => {
    setBusy(`${action}-${row.decision_id}`);
    setError("");
    try {
      if (action === "view") {
        await openDecision(row);
        return;
      }
      if (action === "replay") {
        await runReplay({ ticker: row.symbol, direction: row.direction as "bullish" | "bearish" });
        await patchDecision(row.decision_id, { current_status: "replayed" });
      } else if (action === "paper") {
        if (row.risk_status === "reject") throw new Error("Rejected candidates cannot be paper traded");
        if (row.paper_order_id) throw new Error("Decision already has paper trade");
        await runPaperTrade({ mode: "decision", decision_id: row.decision_id });
      } else if (action === "review") {
        await classifyReview(row.decision_id);
        router.push("/review");
        return;
      } else if (action === "reject") {
        await markDecisionRejected(row.decision_id);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="container page-stack">
      <section className="panel">
        <h2 className="panel-title">Decision Ledger</h2>
        <p className="muted-text">Saved recommendations linked to replay, paper trades, blotter, positions, and review outcomes.</p>
        {error ? <div className="banner banner-danger">{error}</div> : null}
        {!rows.length && !error ? (
          <p className="muted-text">No saved decisions yet. Save a candidate from Strategy Builder or Live Recommendations.</p>
        ) : null}
        <div className="table-wrap">
          <table className="dense-table">
            <thead>
              <tr>
                <th>Decision ID</th>
                <th>Created</th>
                <th>Symbol</th>
                <th>Direction</th>
                <th>Strategy</th>
                <th>Confidence</th>
                <th>Edge</th>
                <th>Risk</th>
                <th>Status</th>
                <th>Review</th>
                <th>Outcome</th>
                <th>Paper P/L</th>
                <th>Max DD</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.decision_id}>
                  <td className="mono">{row.decision_id.slice(0, 8)}</td>
                  <td>{new Date(row.created_at).toLocaleString()}</td>
                  <td className="mono">{row.symbol}</td>
                  <td>{row.direction}</td>
                  <td>{row.strategy_type}</td>
                  <td className="mono">{row.confidence.toFixed(1)}</td>
                  <td className="mono">${row.edge.toFixed(2)}</td>
                  <td>{row.risk_status}</td>
                  <td className="mono">{row.current_status}</td>
                  <td>{row.review_status}</td>
                  <td>{row.final_outcome ?? "-"}</td>
                  <td className={`mono ${(row.paper_pnl_percent ?? 0) >= 0 ? "success-text" : "danger-text"}`}>
                    {row.paper_pnl_percent != null ? `${row.paper_pnl_percent >= 0 ? "+" : ""}${row.paper_pnl_percent.toFixed(1)}%` : "-"}
                  </td>
                  <td className="mono">{row.max_drawdown != null ? `${row.max_drawdown.toFixed(1)}%` : "-"}</td>
                  <td>
                    <div className="inline-form">
                      <button type="button" className="ghost-button" disabled={!!busy} onClick={() => void runAction("view", row)}>View</button>
                      <button type="button" className="ghost-button" disabled={!!busy} onClick={() => void runAction("replay", row)}>Replay</button>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={!!busy || row.risk_status === "reject" || !!row.paper_order_id}
                        onClick={() => void runAction("paper", row)}
                      >
                        Paper
                      </button>
                      <button type="button" className="ghost-button" disabled={!!busy} onClick={() => void runAction("review", row)}>Review</button>
                      <button type="button" className="ghost-button" disabled={!!busy || row.current_status === "rejected"} onClick={() => void runAction("reject", row)}>Reject</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <TradeCardDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        ticker={selected?.symbol ?? null}
        card={tradeCard}
        globalBlocked={false}
        tickerDataBlocked={false}
        onUpdated={() => void load()}
        direction={selected?.direction === "bearish" ? "bearish" : "bullish"}
      />
    </div>
  );
}
