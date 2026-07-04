"use client";

import { useState } from "react";

import { bulkCreatePaperTrades, createPaperTrade } from "@/lib/paperTradeApi";
import type { QqqSpreadAnalysis, QqqSpreadCandidate } from "@/types/qqqSpreadAnalyzer";

type Props = {
  analysis: QqqSpreadAnalysis;
  candidate: QqqSpreadCandidate | null;
  bulk?: boolean;
  onClose: () => void;
  onSaved: (message: string) => void;
};

export default function SavePaperTradeDialog({ analysis, candidate, bulk = false, onClose, onSaved }: Props) {
  const [notes, setNotes] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const title = bulk ? "Save all accepted candidates" : "Save to Paper Trading";

  async function handleSave() {
    setBusy(true);
    setError("");
    try {
      if (bulk) {
        const result = await bulkCreatePaperTrades(analysis, notes);
        onSaved(`Saved ${result.count} trade${result.count === 1 ? "" : "s"} to Paper Trading Lab.`);
      } else if (candidate) {
        await createPaperTrade(analysis, candidate, notes, quantity);
        onSaved("Trade saved to Paper Trading Lab.");
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pt-modal-backdrop" role="presentation" onClick={onClose}>
      <div className="pt-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="panel-header">
          <h2 className="panel-title">{title}</h2>
        </div>
        {!bulk && candidate && (
          <p className="muted-text">
            {candidate.strategy} · {analysis.symbol} · {candidate.expiry} · debit ${candidate.net_debit.toFixed(2)}
          </p>
        )}
        {bulk && (
          <p className="muted-text">
            Saves all spread candidates with status Accepted ({analysis.spread_candidates.filter((c) => c.status === "Accepted").length}{" "}
            rows).
          </p>
        )}
        {!bulk && (
          <label className="pt-field">
            <span>Quantity (contracts)</span>
            <input
              type="number"
              min={1}
              value={quantity}
              onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))}
            />
          </label>
        )}
        <label className="pt-field">
          <span>Notes (optional)</span>
          <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Thesis, sizing, etc." />
        </label>
        {error && <div className="banner banner-danger">{error}</div>}
        <div className="qqq-actions" style={{ marginTop: "0.75rem" }}>
          <button type="button" className="qqq-btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="qqq-btn qqq-btn-primary" onClick={() => void handleSave()} disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
