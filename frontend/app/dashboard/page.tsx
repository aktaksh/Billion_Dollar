"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import TradeCardDrawer from "@/components/TradeCardDrawer";
import {
  getDashboardRecommendations,
  getDashboardSummary,
  getRiskStatus,
  getShellStatus,
  getStrategyHealth,
  getTradeCard,
  getWatchlist,
  patchDecision,
  runPaperTrade,
  runReplay,
} from "@/lib/api";
import { saveDecisionFromRuntime } from "@/lib/decisionHelpers";
import type {
  DashboardSummary,
  EnrichedRecommendation,
  RiskStatus,
  ShellStatus,
  StrategyHealthRow,
  TradeCard,
  WatchlistOpportunity,
} from "@/types";

export default function DashboardPage() {
  const [shell, setShell] = useState<ShellStatus | null>(null);
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistOpportunity[]>([]);
  const [recommendations, setRecommendations] = useState<EnrichedRecommendation[]>([]);
  const [health, setHealth] = useState<StrategyHealthRow[]>([]);
  const [selected, setSelected] = useState<EnrichedRecommendation | null>(null);
  const [tradeCard, setTradeCard] = useState<TradeCard | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [shellStatus, riskStatus, dashSummary, watchlistRows, recs, strategyHealth] = await Promise.all([
        getShellStatus(),
        getRiskStatus(),
        getDashboardSummary(),
        getWatchlist(),
        getDashboardRecommendations(),
        getStrategyHealth(),
      ]);
      setShell(shellStatus);
      setRisk(riskStatus);
      setSummary(dashSummary);
      setWatchlist(watchlistRows);
      setRecommendations(recs);
      setHealth(strategyHealth);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 20_000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!selected?.ticker) return;
    let cancelled = false;
    void getTradeCard(selected.ticker).then((card) => {
      if (!cancelled) setTradeCard(card);
    });
    return () => {
      cancelled = true;
    };
  }, [selected?.ticker]);

  const dq = summary?.decision_quality;

  const openTradeCard = (row: EnrichedRecommendation) => {
    setSelected(row);
    setDrawerOpen(true);
  };

  const runRowAction = async (action: string, row: EnrichedRecommendation) => {
    setBusy(`${action}-${row.ticker}`);
    setError("");
    try {
      const direction = row.direction === "bearish" ? "bearish" : "bullish";
      if (action === "save") {
        await saveDecisionFromRuntime(row.ticker, direction, { signal_id: row.signal_id, thesis: row.thesis });
      } else if (action === "replay") {
        await runReplay({ ticker: row.ticker, direction });
        if (row.decision_id) await patchDecision(row.decision_id, { current_status: "replayed" });
      } else if (action === "paper") {
        if (!row.decision_id) throw new Error("Save decision before paper trade");
        await runPaperTrade({ mode: "decision", decision_id: row.decision_id });
      } else if (action === "card") {
        openTradeCard(row);
        return;
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy("");
    }
  };

  const reasonPanel = useMemo(() => {
    if (!selected) return null;
    return (
      <section className="panel-sub">
        <h3>Recommendation Reason — {selected.ticker}</h3>
        <ul className="dense-list">
          <li><span>Why appeared</span><span>{selected.thesis || selected.reason_preview[0] || "-"}</span></li>
          <li><span>Market regime</span><span className="mono">{selected.regime_label}</span></li>
          <li><span>Signal reason</span><span>{selected.reason_preview.join(" · ") || "-"}</span></li>
          <li><span>Liquidity</span><span className="mono">{selected.liquidity_status}</span></li>
          <li><span>Risk status</span><span className="mono">{selected.risk_status}</span></li>
          <li><span>Before entry</span><span>{selected.entry_trigger}</span></li>
          <li><span>Invalidates trade</span><span>{selected.invalidation_rule}</span></li>
        </ul>
      </section>
    );
  }, [selected]);

  return (
    <div className="container page-stack">
      <section className="panel">
        <h2 className="panel-title">Command Center</h2>
        <p className="muted-text">Global broker, reconcile, and risk posture for Billion Dollar workstation.</p>
        {error ? <div className="banner banner-danger">{error}</div> : null}
        {shell ? (
          <div className="dashboard-grid">
            <article className="panel-sub">
              <h3>Runtime</h3>
              <ul className="dense-list">
                <li><span>Data status</span><span className="mono">{shell.data_status}</span></li>
                <li><span>Execution mode</span><span className="mono">{shell.execution_mode}</span></li>
                <li><span>Reconcile worker</span><span className="mono">{shell.reconcile_worker_status}</span></li>
                <li><span>New entries</span><span className="mono">{shell.can_open_new_entries ? "allowed" : "blocked"}</span></li>
              </ul>
            </article>
            <article className="panel-sub">
              <h3>Risk</h3>
              {risk ? (
                <ul className="dense-list">
                  <li><span>Drawdown</span><span className="mono">{risk.drawdown_pct.toFixed(2)}%</span></li>
                  <li><span>Stress loss NAV</span><span className="mono">{risk.worst_case_stress_loss_nav_pct.toFixed(2)}%</span></li>
                  <li><span>Active halts</span><span className="mono">{risk.active_halts.length}</span></li>
                </ul>
              ) : (
                <p className="muted-text">Risk status unavailable</p>
              )}
            </article>
            <article className="panel-sub">
              <h3>Watchlist health</h3>
              <ul className="dense-list">
                <li><span>Tracked tickers</span><span className="mono">{watchlist.length}</span></li>
                <li><span>Blocked</span><span className="mono">{watchlist.filter((row) => row.data_health === "Blocked").length}</span></li>
                <li><span>Degraded</span><span className="mono">{watchlist.filter((row) => row.data_health === "Degraded").length}</span></li>
              </ul>
            </article>
          </div>
        ) : null}
      </section>

      {dq ? (
        <section className="panel">
          <h3 className="panel-title">Decision Quality</h3>
          <div className="dashboard-grid">
            <article className="panel-sub">
              <ul className="dense-list">
                <li><span>Total Decisions</span><span className="mono">{dq.total_decisions_today}</span></li>
                <li><span>Paper Trades</span><span className="mono">{dq.paper_trades_opened}</span></li>
                <li><span>Open Positions</span><span className="mono">{dq.open_paper_positions}</span></li>
                <li><span>Ready for Review</span><span className="mono">{dq.decisions_ready_for_review}</span></li>
                <li><span>Reviewed</span><span className="mono">{dq.reviewed_decisions}</span></li>
              </ul>
            </article>
            <article className="panel-sub">
              <ul className="dense-list">
                <li><span>Win Rate</span><span className="mono">{(dq.win_rate * 100).toFixed(0)}%</span></li>
                <li><span>Avg Paper P/L</span><span className={`mono ${dq.avg_paper_pnl_percent >= 0 ? "success-text" : "danger-text"}`}>{dq.avg_paper_pnl_percent >= 0 ? "+" : ""}{dq.avg_paper_pnl_percent.toFixed(1)}%</span></li>
                <li><span>Avg Max Drawdown</span><span className="mono">{dq.avg_max_drawdown.toFixed(1)}%</span></li>
                <li><span>Engine Accuracy</span><span className="mono">{(dq.engine_accuracy * 100).toFixed(0)}%</span></li>
              </ul>
            </article>
            <article className="panel-sub">
              <ul className="dense-list">
                <li><span>Best Strategy</span><span>{dq.best_strategy || "-"}</span></li>
                <li><span>Worst Strategy</span><span>{dq.worst_strategy || "-"}</span></li>
                <li><span>Most Common Reject</span><span>{dq.most_common_reject_reason || "-"}</span></li>
              </ul>
            </article>
          </div>
        </section>
      ) : null}

      <section className="panel">
        <h3 className="panel-title">Live Recommendations</h3>
        {!recommendations.length ? (
          <p className="muted-text">No live recommendations. Activate a universe and run Strategy Builder to generate candidates.</p>
        ) : null}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Strategy</th>
                <th>Direction</th>
                <th>Confidence</th>
                <th>Edge</th>
                <th>Max Loss</th>
                <th>Max Profit</th>
                <th>POP</th>
                <th>Risk</th>
                <th>Decision</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {recommendations.slice(0, 12).map((row) => (
                <tr
                  key={row.signal_id}
                  className={selected?.signal_id === row.signal_id ? "is-active" : ""}
                  onClick={() => setSelected(row)}
                >
                  <td className="mono">{row.ticker}</td>
                  <td>{row.strategy}</td>
                  <td>{row.direction}</td>
                  <td className="mono">{row.confidence.toFixed(1)}</td>
                  <td className="mono">${row.edge.toFixed(2)}</td>
                  <td className="mono">{row.max_loss != null ? `$${row.max_loss.toFixed(0)}` : "-"}</td>
                  <td className="mono">{row.max_profit != null ? `$${row.max_profit.toFixed(0)}` : "-"}</td>
                  <td className="mono">{row.pop != null ? `${(row.pop * 100).toFixed(0)}%` : "-"}</td>
                  <td>{row.risk_status}</td>
                  <td className="mono">{row.decision_status}</td>
                  <td>
                    <div className="inline-form" onClick={(e) => e.stopPropagation()}>
                      <button type="button" className="ghost-button" disabled={!!busy} onClick={() => void runRowAction("card", row)}>Card</button>
                      <button type="button" className="ghost-button" disabled={!!busy || row.decision_status !== "none"} onClick={() => void runRowAction("save", row)}>Save</button>
                      <button type="button" className="ghost-button" disabled={!!busy} onClick={() => void runRowAction("replay", row)}>Replay</button>
                      <button type="button" className="ghost-button" disabled={!!busy || !row.decision_id || row.risk_status === "reject"} onClick={() => void runRowAction("paper", row)}>Paper</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {reasonPanel}
      </section>

      <section className="panel">
        <h3 className="panel-title">Strategy Health</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Sleeve</th>
                <th>Regime</th>
                <th>Trades</th>
                <th>Win rate</th>
                <th>Expectancy</th>
              </tr>
            </thead>
            <tbody>
              {health.map((row) => (
                <tr key={`${row.strategy_sleeve}-${row.regime_label}`}>
                  <td>{row.strategy_sleeve}</td>
                  <td>{row.regime_label}</td>
                  <td className="mono">{row.trades}</td>
                  <td className="mono">{(row.win_rate * 100).toFixed(1)}%</td>
                  <td className="mono">${row.expectancy_after_costs_usd.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <TradeCardDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        ticker={selected?.ticker ?? null}
        card={tradeCard}
        globalBlocked={shell ? !shell.can_open_new_entries : false}
        tickerDataBlocked={false}
        onUpdated={() => void load()}
        direction={selected?.direction === "bearish" ? "bearish" : "bullish"}
      />
    </div>
  );
}
