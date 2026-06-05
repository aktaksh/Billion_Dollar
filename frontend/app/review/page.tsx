"use client";

import { useCallback, useEffect, useState } from "react";

import { classifyReview, completeReview, getTradeReview } from "@/lib/api";
import type { DecisionFinalOutcome, TradeReviewItem } from "@/types";

const OUTCOMES: DecisionFinalOutcome[] = [
  "correct",
  "partially_correct",
  "wrong",
  "invalid_entry",
  "invalid_exit",
  "skipped_trigger_not_met",
];

export default function ReviewPage() {
  const [items, setItems] = useState<TradeReviewItem[]>([]);
  const [selected, setSelected] = useState<TradeReviewItem | null>(null);
  const [lesson, setLesson] = useState("");
  const [outcome, setOutcome] = useState<DecisionFinalOutcome>("correct");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await getTradeReview();
      setItems(data);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load review queue");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openItem = (item: TradeReviewItem) => {
    setSelected(item);
    setLesson(item.lesson ?? "");
    setOutcome((item.outcome as DecisionFinalOutcome) ?? "correct");
  };

  const runClassify = async (decisionId: string) => {
    setBusy(true);
    try {
      const result = await classifyReview(decisionId);
      setOutcome(result.final_outcome as DecisionFinalOutcome);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Classification failed");
    } finally {
      setBusy(false);
    }
  };

  const saveReview = async () => {
    if (!selected?.decision_id) return;
    setBusy(true);
    try {
      await completeReview(selected.decision_id, { final_outcome: outcome, lesson });
      setSelected(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to complete review");
    } finally {
      setBusy(false);
    }
  };

  const readyItems = items.filter((i) => i.decision_id);

  return (
    <main className="container page-stack">
      <section className="panel">
        <h2 className="panel-title">Review</h2>
        <p className="muted-text">Engine-quality review of closed paper trades against original decision plans.</p>
        {error ? <div className="banner banner-danger">{error}</div> : null}
        {!readyItems.length && !error ? (
          <p className="muted-text">No decisions are ready for review. Run paper trades from saved decisions and close them to generate review items.</p>
        ) : null}
        <div className="table-wrap">
          <table className="dense-table">
            <thead>
              <tr>
                <th>Decision</th>
                <th>Symbol</th>
                <th>Strategy</th>
                <th>Direction</th>
                <th>Created</th>
                <th>Closed</th>
                <th>Score</th>
                <th>Risk</th>
                <th>Max Loss</th>
                <th>Max Profit</th>
                <th>Final P/L</th>
                <th>P/L %</th>
                <th>Max DD</th>
                <th>Time</th>
                <th>Outcome</th>
                <th>Review</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {readyItems.map((item) => (
                <tr key={item.decision_id} className={selected?.decision_id === item.decision_id ? "is-active" : ""}>
                  <td className="mono">{item.decision_id.slice(0, 8)}</td>
                  <td className="mono">{item.symbol}</td>
                  <td>{item.strategy_type}</td>
                  <td>{item.direction}</td>
                  <td>{item.created_at ? new Date(item.created_at).toLocaleString() : "-"}</td>
                  <td>{item.closed_at ? new Date(item.closed_at).toLocaleString() : "-"}</td>
                  <td className="mono">{item.original_score?.toFixed(1) ?? "-"}</td>
                  <td>{item.risk_status ?? "-"}</td>
                  <td className="mono">{item.max_loss != null ? `$${item.max_loss.toFixed(0)}` : "-"}</td>
                  <td className="mono">{item.max_profit != null ? `$${item.max_profit.toFixed(0)}` : "-"}</td>
                  <td className={`mono ${(item.final_pnl ?? 0) >= 0 ? "success-text" : "danger-text"}`}>
                    {item.final_pnl != null ? `$${item.final_pnl.toFixed(2)}` : "-"}
                  </td>
                  <td className="mono">{item.final_pnl_percent != null ? `${item.final_pnl_percent.toFixed(1)}%` : "-"}</td>
                  <td className="mono">{item.max_drawdown != null ? `${item.max_drawdown.toFixed(1)}%` : "-"}</td>
                  <td>{item.time_in_trade ?? "-"}</td>
                  <td>{item.outcome ?? "-"}</td>
                  <td>{item.review_status ?? "pending"}</td>
                  <td>
                    <button type="button" className="ghost-button" onClick={() => openItem(item)}>Open</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {selected ? (
        <section className="panel">
          <h3 className="panel-title">Review Detail — {selected.symbol}</h3>
          <div className="dashboard-grid">
            <article className="panel-sub">
              <h4>Original Decision</h4>
              <ul className="dense-list">
                <li><span>Thesis</span><span>{selected.thesis ?? "-"}</span></li>
                <li><span>Entry trigger</span><span>{selected.entry_trigger ?? "-"}</span></li>
                <li><span>Invalidation</span><span>{selected.invalidation_rule ?? "-"}</span></li>
                <li><span>Profit plan</span><span>{selected.profit_plan ?? "-"}</span></li>
                <li><span>Regime</span><span className="mono">{selected.market_regime ?? "-"}</span></li>
                <li><span>Technical</span><span className="mono">{selected.technical_score?.toFixed(1) ?? "-"}</span></li>
                <li><span>Catalyst</span><span className="mono">{selected.catalyst_score?.toFixed(1) ?? "-"}</span></li>
                <li><span>Liquidity</span><span className="mono">{selected.liquidity_score?.toFixed(1) ?? "-"}</span></li>
              </ul>
            </article>
            <article className="panel-sub">
              <h4>Actual Result</h4>
              <ul className="dense-list">
                <li><span>Entry price</span><span className="mono">{selected.entry_price ?? "-"}</span></li>
                <li><span>Exit price</span><span className="mono">{selected.exit_price ?? "-"}</span></li>
                <li><span>P/L</span><span className="mono">{selected.final_pnl ?? "-"}</span></li>
                <li><span>Max drawdown</span><span className="mono">{selected.max_drawdown ?? "-"}</span></li>
                <li><span>Entry trigger met</span><span className="mono">{String(selected.entry_trigger_met ?? "-")}</span></li>
                <li><span>Invalidation hit</span><span className="mono">{String(selected.invalidation_hit ?? "-")}</span></li>
                <li><span>Profit target hit</span><span className="mono">{String(selected.profit_target_hit ?? "-")}</span></li>
                <li><span>Exit followed plan</span><span className="mono">{String(selected.exit_followed_plan ?? "-")}</span></li>
              </ul>
            </article>
          </div>

          <div className="inline-form" style={{ marginTop: 16 }}>
            <button type="button" className="secondary-button" disabled={busy} onClick={() => void runClassify(selected.decision_id)}>
              Auto Classify
            </button>
            <select className="feed-input" value={outcome} onChange={(e) => setOutcome(e.target.value as DecisionFinalOutcome)}>
              {OUTCOMES.map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
            <textarea
              className="feed-input"
              value={lesson}
              onChange={(e) => setLesson(e.target.value)}
              placeholder="Lesson learned..."
              style={{ minWidth: 280, minHeight: 60 }}
            />
            <button type="button" className="primary-button" disabled={busy} onClick={() => void saveReview()}>
              Complete Review
            </button>
            <button type="button" className="ghost-button" onClick={() => setSelected(null)}>Close</button>
          </div>
        </section>
      ) : null}
    </main>
  );
}
