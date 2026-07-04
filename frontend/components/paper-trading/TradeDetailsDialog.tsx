"use client";

import { useState } from "react";

import { closePaperTrade, updatePaperTradeNotes } from "@/lib/paperTradeApi";
import type { PaperTradeDetail } from "@/types/paperTrading";

import TradeAnalytics from "./TradeAnalytics";

type Props = {
  trade: PaperTradeDetail;
  onUpdated: (trade: PaperTradeDetail) => void;
};

export default function TradeDetailsDialog({ trade, onUpdated }: Props) {
  const [notes, setNotes] = useState(trade.notes ?? "");
  const [exitReason, setExitReason] = useState("Manual close");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const latest = trade.snapshots[trade.snapshots.length - 1];
  const entrySnap = trade.entry_snapshot_json as { analysis?: Record<string, unknown> } | null;
  const entryAnalysis = entrySnap?.analysis as Record<string, unknown> | undefined;
  const entryDaily = (entryAnalysis?.daily_indicators ?? {}) as Record<string, number | null>;
  const latestDaily = (latest?.snapshot_json?.daily_indicators ?? {}) as Record<string, number | null>;

  async function saveNotes() {
    setBusy(true);
    setError("");
    try {
      const updated = await updatePaperTradeNotes(trade.id, notes);
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleClose() {
    setBusy(true);
    setError("");
    try {
      const updated = await closePaperTrade(trade.id, exitReason);
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Close failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pt-detail-grid">
      <section className="panel">
        <div className="panel-header">
          <h2 className="panel-title">
            {trade.symbol} · {trade.strategy_type}
          </h2>
          <span className="badge-yes">{trade.status}</span>
        </div>
        <div className="pt-kv-grid">
          <div>
            <span className="muted-text">Entry underlying</span>
            <div>${trade.underlying_price_at_entry.toFixed(2)}</div>
          </div>
          <div>
            <span className="muted-text">Current underlying</span>
            <div>${(trade.current_underlying_price ?? 0).toFixed(2)}</div>
          </div>
          <div>
            <span className="muted-text">Spread value</span>
            <div>${(trade.current_spread_value ?? 0).toFixed(2)}</div>
          </div>
          <div>
            <span className="muted-text">Unrealized / Realized</span>
            <div>
              ${(trade.status === "OPEN" ? trade.unrealized_pnl : trade.realized_pnl)?.toFixed(2) ?? "0.00"}
            </div>
          </div>
        </div>
        <p className="muted-text">{trade.reason_for_trade}</p>
      </section>

      <TradeAnalytics snapshots={trade.snapshots} />

      <section className="panel">
        <h3 className="pt-subtitle">Indicators: entry vs latest mark</h3>
        <div className="table-wrap">
          <table className="qqq-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th className="num">Entry</th>
                <th className="num">Latest</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["RSI", trade.entry_rsi, latestDaily.rsi14],
                ["MACD", trade.entry_macd, latestDaily.macd_line],
                ["ATR", trade.entry_atr, latestDaily.atr14],
              ].map(([label, entry, latestVal]) => (
                <tr key={String(label)}>
                  <td>{label}</td>
                  <td className="num">{entry != null ? Number(entry).toFixed(2) : "—"}</td>
                  <td className="num">{latestVal != null ? Number(latestVal).toFixed(2) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <h3 className="pt-subtitle">Notes</h3>
        <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <div className="qqq-actions" style={{ marginTop: "0.5rem" }}>
          <button type="button" className="qqq-btn" onClick={() => void saveNotes()} disabled={busy}>
            Save notes
          </button>
        </div>
      </section>

      {trade.status === "OPEN" && (
        <section className="panel">
          <h3 className="pt-subtitle">Close trade</h3>
          <label className="pt-field">
            <span>Exit reason</span>
            <input value={exitReason} onChange={(e) => setExitReason(e.target.value)} />
          </label>
          <button type="button" className="qqq-btn qqq-btn-primary" onClick={() => void handleClose()} disabled={busy}>
            Close paper trade
          </button>
        </section>
      )}

      {trade.review && (
        <section className="panel">
          <h3 className="pt-subtitle">Trade review</h3>
          <div className="pt-review">
            <p>
              <strong>What went right:</strong> {trade.review.what_went_right}
            </p>
            <p>
              <strong>What went wrong:</strong> {trade.review.what_went_wrong}
            </p>
            <p>
              <strong>Indicators:</strong> {trade.review.indicators_agreed}
            </p>
            <p>
              <strong>Regime:</strong> {trade.review.regime_change}
            </p>
            <p>
              <strong>Would recommend again?</strong> {trade.review.would_recommend_again}
            </p>
          </div>
        </section>
      )}

      {error && <div className="banner banner-danger">{error}</div>}
    </div>
  );
}
