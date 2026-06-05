"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getTradeCard, patchDecision, runPaperTrade, runReplay } from "@/lib/api";
import { markDecisionRejected, saveDecisionFromRuntime } from "@/lib/decisionHelpers";
import type { StrategyCandidateOut, TradeCard } from "@/types";

type Props = {
  card: TradeCard | null;
  ticker: string | null;
  open: boolean;
  onClose: () => void;
  globalBlocked: boolean;
  tickerDataBlocked: boolean;
  onUpdated?: () => void;
  candidate?: StrategyCandidateOut | null;
  direction?: "bullish" | "bearish";
};

function kvRows(record: Record<string, unknown> | null | undefined) {
  if (!record) return [];
  return Object.entries(record);
}

function fmtMoney(value: unknown): string {
  const n = Number(value);
  if (Number.isNaN(n)) return "-";
  return `$${n.toFixed(2)}`;
}

function fmtPct(value: unknown): string {
  const n = Number(value);
  if (Number.isNaN(n)) return "-";
  return `${(n * 100).toFixed(1)}%`;
}

export default function TradeCardDrawer({
  card,
  ticker,
  open,
  onClose,
  globalBlocked,
  tickerDataBlocked,
  onUpdated,
  candidate,
  direction = "bullish",
}: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState("");
  const [actionError, setActionError] = useState("");
  const [localCard, setLocalCard] = useState<TradeCard | null>(card);

  useEffect(() => {
    if (open) setLocalCard(card);
  }, [card, open]);

  const refreshCard = useCallback(async () => {
    if (!ticker) return;
    try {
      const next = await getTradeCard(ticker);
      setLocalCard(next);
      onUpdated?.();
    } catch {
      /* ignore */
    }
  }, [ticker, onUpdated]);

  const actionsBlocked = globalBlocked || tickerDataBlocked;
  const display = localCard ?? card;
  const decisionId = display?.decision_id ?? null;
  const riskReject = display?.risk_status === "reject";

  const handleSave = async () => {
    if (!ticker) return;
    setBusy("save");
    setActionError("");
    try {
      await saveDecisionFromRuntime(ticker, direction, {
        candidate: candidate ?? undefined,
        signal_id: null,
        thesis: String(display?.thesis?.why_exists ?? `Decision for ${ticker}`),
      });
      await refreshCard();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy("");
    }
  };

  const handleReplay = async () => {
    if (!ticker) return;
    setBusy("replay");
    setActionError("");
    try {
      await runReplay({ ticker, direction });
      if (decisionId) {
        await patchDecision(decisionId, { current_status: "replayed" });
      }
      await refreshCard();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Replay failed");
    } finally {
      setBusy("");
    }
  };

  const handlePaper = async () => {
    if (!decisionId) {
      setActionError("Save decision before running paper trade");
      return;
    }
    setBusy("paper");
    setActionError("");
    try {
      await runPaperTrade({ mode: "decision", decision_id: decisionId });
      await refreshCard();
      onUpdated?.();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Paper trade failed");
    } finally {
      setBusy("");
    }
  };

  const handleReject = async () => {
    setBusy("reject");
    setActionError("");
    try {
      if (decisionId) {
        await markDecisionRejected(decisionId);
      } else if (ticker) {
        await saveDecisionFromRuntime(ticker, direction, { candidate: candidate ?? undefined, rejected: true });
      }
      await refreshCard();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Reject failed");
    } finally {
      setBusy("");
    }
  };

  if (!open) return null;

  const summary = (display?.decision_summary ?? display?.thesis ?? {}) as Record<string, unknown>;
  const plan = (display?.trade_plan ?? {}) as Record<string, unknown>;
  const legs = display?.strategy_legs ?? [];

  return (
    <div className="drawer-backdrop" role="dialog" aria-modal="true">
      <aside className="trade-drawer panel">
        <div className="drawer-header">
          <div>
            <h2 className="panel-title">
              Trade Card {ticker ? `- ${ticker}` : ""}
            </h2>
            <p className="muted-text">Decision summary, trade plan, and lifecycle actions</p>
          </div>
          <button type="button" className="ghost-button" onClick={onClose}>
            Close
          </button>
        </div>

        {tickerDataBlocked ? (
          <div className="banner banner-warning">Data health is BLOCKED for this ticker. Execution actions are disabled.</div>
        ) : null}
        {actionError ? <div className="banner banner-danger">{actionError}</div> : null}

        {!display ? (
          <p className="muted-text">Select a watchlist row to open details.</p>
        ) : (
          <div className="drawer-content">
            <div className="drawer-grid">
              <div className="stat-cell">
                <span className="muted-text">Direction</span>
                <strong className="mono">{display.direction ?? "-"}</strong>
              </div>
              <div className="stat-cell">
                <span className="muted-text">Strategy</span>
                <strong className="mono">{display.strategy_type ?? "-"}</strong>
              </div>
              <div className="stat-cell">
                <span className="muted-text">Risk</span>
                <strong className="mono">{display.risk_status ?? "-"}</strong>
              </div>
              <div className="stat-cell">
                <span className="muted-text">Confidence</span>
                <strong className="mono">{display.confidence_total.toFixed(1)}</strong>
              </div>
              <div className="stat-cell">
                <span className="muted-text">Data</span>
                <strong className="mono">{display.data_status ?? "-"}</strong>
              </div>
              <div className="stat-cell">
                <span className="muted-text">Broker</span>
                <strong className="mono">{display.broker_status ?? "-"}</strong>
              </div>
              <div className="stat-cell">
                <span className="muted-text">Reconcile</span>
                <strong className="mono">{display.reconcile_status ?? "-"}</strong>
              </div>
              <div className="stat-cell">
                <span className="muted-text">Decision</span>
                <strong className="mono">{decisionId ?? "not saved"}</strong>
              </div>
            </div>

            <section className="panel-sub">
              <h3>Decision Summary</h3>
              <ul className="dense-list">
                <li><span>Why exists</span><span>{String(summary.why_exists ?? "-")}</span></li>
                <li><span>Market regime</span><span className="mono">{String(summary.market_regime ?? "-")}</span></li>
                <li><span>Technical</span><span>{String(summary.technical_reason ?? "-")}</span></li>
                <li><span>Catalyst</span><span>{String(summary.catalyst_reason ?? "-")}</span></li>
                <li><span>Liquidity</span><span>{String(summary.options_liquidity_reason ?? "-")}</span></li>
                <li><span>Risk</span><span>{String(summary.risk_reason ?? "-")}</span></li>
              </ul>
            </section>

            <section className="panel-sub">
              <h3>Trade Plan</h3>
              <ul className="dense-list">
                <li><span>Entry trigger</span><span>{String(plan.entry_trigger ?? "-")}</span></li>
                <li><span>Invalidation</span><span>{String(plan.invalidation_rule ?? "-")}</span></li>
                <li><span>Profit plan</span><span>{String(plan.profit_plan ?? "-")}</span></li>
                <li><span>Max loss</span><span className="mono">{fmtMoney(plan.max_loss)}</span></li>
                <li><span>Max profit</span><span className="mono">{fmtMoney(plan.max_profit)}</span></li>
                <li><span>POP</span><span className="mono">{fmtPct(plan.pop)}</span></li>
                <li><span>Expected value</span><span className="mono">{fmtMoney(plan.expected_value)}</span></li>
                <li><span>Before entry</span><span>{String(plan.before_entry ?? "-")}</span></li>
              </ul>
            </section>

            <section className="panel-sub">
              <h3>Strategy Legs</h3>
              {legs.length ? (
                <div className="table-wrap">
                  <table className="dense-table">
                    <thead>
                      <tr>
                        <th>Action</th>
                        <th>Type</th>
                        <th>Strike</th>
                        <th>Expiry</th>
                        <th>Bid</th>
                        <th>Ask</th>
                        <th>Mid</th>
                        <th>Delta</th>
                        <th>IV</th>
                        <th>OI</th>
                        <th>Vol</th>
                      </tr>
                    </thead>
                    <tbody>
                      {legs.map((leg, idx) => (
                        <tr key={idx}>
                          <td>{String(leg.action ?? "-")}</td>
                          <td>{String(leg.option_type ?? leg.type ?? "-")}</td>
                          <td className="mono">{String(leg.strike ?? "-")}</td>
                          <td className="mono">{String(leg.expiry ?? "-")}</td>
                          <td className="mono">{leg.bid != null ? Number(leg.bid).toFixed(2) : "-"}</td>
                          <td className="mono">{leg.ask != null ? Number(leg.ask).toFixed(2) : "-"}</td>
                          <td className="mono">{leg.mid != null ? Number(leg.mid).toFixed(2) : "-"}</td>
                          <td className="mono">{leg.delta != null ? Number(leg.delta).toFixed(2) : "-"}</td>
                          <td className="mono">{leg.iv != null ? Number(leg.iv).toFixed(2) : "-"}</td>
                          <td className="mono">{String(leg.oi ?? leg.open_interest ?? "-")}</td>
                          <td className="mono">{String(leg.volume ?? "-")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="muted-text">Save a decision from Strategy Builder to populate legs.</p>
              )}
            </section>

            {display.warnings.length ? (
              <section className="panel-sub">
                <h3>Warnings</h3>
                <ul className="dense-list">
                  {display.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            <div className="drawer-actions">
              <button type="button" className="primary-button" disabled={actionsBlocked || !!busy || !!decisionId} onClick={() => void handleSave()}>
                {busy === "save" ? "Saving..." : "Save Decision"}
              </button>
              <button type="button" className="secondary-button" disabled={actionsBlocked || !!busy} onClick={() => void handleReplay()}>
                {busy === "replay" ? "Running..." : "Run Replay"}
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={actionsBlocked || !!busy || !decisionId || riskReject}
                onClick={() => void handlePaper()}
              >
                {busy === "paper" ? "Paper..." : "Run Paper"}
              </button>
              <button type="button" className="ghost-button" disabled={!!busy} onClick={() => void handleReject()}>
                {busy === "reject" ? "Rejecting..." : "Reject Candidate"}
              </button>
              {decisionId ? (
                <button type="button" className="ghost-button" onClick={() => router.push("/decisions")}>
                  Open Ledger
                </button>
              ) : null}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
