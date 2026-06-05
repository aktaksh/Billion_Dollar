"use client";

import { useEffect, useState } from "react";

import { getDecisions, getShellStatus, runPaperTrade } from "@/lib/api";
import type { PaperTradeRunOut, ShellStatus, TradeDecision } from "@/types";

type PaperMode = "decision" | "quick";

export default function PaperPage() {
  const [mode, setMode] = useState<PaperMode>("decision");
  const [decisions, setDecisions] = useState<TradeDecision[]>([]);
  const [decisionId, setDecisionId] = useState("");
  const [ticker, setTicker] = useState("QQQ");
  const [direction, setDirection] = useState<"bullish" | "bearish">("bullish");
  const [scenarioReturn, setScenarioReturn] = useState("0.02");
  const [shell, setShell] = useState<ShellStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PaperTradeRunOut | null>(null);

  useEffect(() => {
    void getShellStatus().then(setShell).catch(() => setShell(null));
    void getDecisions().then((rows) => {
      setDecisions(rows);
      const eligible = rows.find(
        (d) => d.risk_status !== "reject" && !d.paper_order_id && d.current_status !== "rejected",
      );
      if (eligible) setDecisionId(eligible.decision_id);
    });
  }, []);

  const selectedDecision = decisions.find((d) => d.decision_id === decisionId) ?? null;
  const entriesBlocked = shell ? !shell.can_open_new_entries : false;

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (entriesBlocked) {
      setError("New entries blocked by reconcile halt or runtime gate");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const out =
        mode === "decision"
          ? await runPaperTrade({
              mode: "decision",
              decision_id: decisionId,
              scenario_return: Number(scenarioReturn),
            })
          : await runPaperTrade({
              mode: "quick",
              ticker: ticker.trim().toUpperCase(),
              direction,
              scenario_return: Number(scenarioReturn),
            });
      setResult(out);
      if (mode === "decision") {
        const refreshed = await getDecisions();
        setDecisions(refreshed);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Paper trade failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container page-stack">
      <section className="panel">
        <h2 className="panel-title">Paper Trading</h2>
        <p className="muted-text">Decision-based paper execution with lifecycle trace. Quick mode is for developer testing only.</p>

        <div className="feed-controls" style={{ marginBottom: 12 }}>
          <label className="feed-scope">
            <input type="radio" checked={mode === "decision"} onChange={() => setMode("decision")} />
            Decision-Based Paper Trade
          </label>
          <label className="feed-scope">
            <input type="radio" checked={mode === "quick"} onChange={() => setMode("quick")} />
            Quick Paper Test (dev only)
          </label>
        </div>

        {entriesBlocked ? <div className="banner banner-danger">Reconcile halt active — new entries blocked.</div> : null}

        <form className="page-stack" onSubmit={onSubmit}>
          {mode === "decision" ? (
            <>
              <label className="sb-field">
                Decision
                <select className="feed-input" value={decisionId} onChange={(e) => setDecisionId(e.target.value)} required>
                  <option value="">Select saved decision</option>
                  {decisions
                    .filter((d) => d.risk_status !== "reject" && !d.paper_order_id && d.current_status !== "rejected")
                    .map((d) => (
                      <option key={d.decision_id} value={d.decision_id}>
                        {d.symbol} · {d.strategy_type} · {d.decision_id.slice(0, 8)}
                      </option>
                    ))}
                </select>
              </label>
              {selectedDecision ? (
                <article className="panel-sub">
                  <h3>Trade Plan Preview</h3>
                  <ul className="dense-list">
                    <li><span>Strategy</span><span>{selectedDecision.strategy_type}</span></li>
                    <li><span>Direction</span><span>{selectedDecision.direction}</span></li>
                    <li><span>Risk</span><span>{selectedDecision.risk_status}</span></li>
                    <li><span>Max loss</span><span className="mono">{selectedDecision.max_loss != null ? `$${selectedDecision.max_loss.toFixed(0)}` : "-"}</span></li>
                    <li><span>Max profit</span><span className="mono">{selectedDecision.max_profit != null ? `$${selectedDecision.max_profit.toFixed(0)}` : "-"}</span></li>
                    <li><span>Entry trigger</span><span>{selectedDecision.entry_trigger ?? "-"}</span></li>
                    <li><span>Invalidation</span><span>{selectedDecision.invalidation_rule ?? "-"}</span></li>
                  </ul>
                </article>
              ) : (
                <p className="muted-text">Select a saved decision. Save one from Strategy Builder if none exist.</p>
              )}
            </>
          ) : (
            <div className="inline-form">
              <input className="feed-input" value={ticker} onChange={(e) => setTicker(e.target.value)} />
              <select className="feed-input" value={direction} onChange={(e) => setDirection(e.target.value as "bullish" | "bearish")}>
                <option value="bullish">Bullish</option>
                <option value="bearish">Bearish</option>
              </select>
            </div>
          )}
          <input
            className="feed-input"
            value={scenarioReturn}
            onChange={(e) => setScenarioReturn(e.target.value)}
            placeholder="Scenario return"
          />
          <button
            type="submit"
            className="primary-button"
            disabled={loading || entriesBlocked || (mode === "decision" && !decisionId)}
          >
            {loading ? "Simulating..." : "Run paper trade"}
          </button>
        </form>

        {error ? <div className="banner banner-danger">{error}</div> : null}
        {result ? (
          <article className="panel-sub">
            <h3>Paper Lifecycle</h3>
            <ul className="dense-list">
              <li><span>Decision</span><span className="mono">{result.decision_id ?? "-"}</span></li>
              <li><span>Signal</span><span className="mono">{result.signal_id}</span></li>
              <li><span>Realized PnL</span><span className="mono">${result.realized_pnl_after_costs_usd.toFixed(2)}</span></li>
              <li><span>PnL %</span><span className="mono">{(result.realized_pnl_percent ?? 0).toFixed(1)}%</span></li>
              <li><span>Entry / Exit</span><span className="mono">{result.entry_price.toFixed(2)} → {result.exit_price.toFixed(2)}</span></li>
              <li><span>Data status</span><span className="mono">{result.data_status}</span></li>
            </ul>
            {result.lifecycle?.length ? (
              <ol className="dense-list">
                {result.lifecycle.map((step) => (
                  <li key={step} className="mono">{step}</li>
                ))}
              </ol>
            ) : null}
          </article>
        ) : null}
      </section>
    </div>
  );
}
