"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import ExplainFeedPanel from "@/components/ExplainFeedPanel";
import TradeCardDrawer from "@/components/TradeCardDrawer";
import { getReconcileMismatches, getTradeCard, getWatchlist, patchDecision, runPaperTrade, runReplay } from "@/lib/api";
import { markDecisionRejected, saveDecisionFromRuntime } from "@/lib/decisionHelpers";
import type { ReconcileMismatch, TradeCard, WatchlistOpportunity } from "@/types";

export default function WatchlistHomePage() {
  const [watchlist, setWatchlist] = useState<WatchlistOpportunity[]>([]);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [tradeCard, setTradeCard] = useState<TradeCard | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [mismatches, setMismatches] = useState<ReconcileMismatch[]>([]);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [busy, setBusy] = useState("");

  const loadWatchlist = useCallback(async () => {
    try {
      const [watchlistRows, mismatchRows] = await Promise.all([getWatchlist(), getReconcileMismatches()]);
      setWatchlist(watchlistRows);
      setMismatches(mismatchRows);
      setErrorMessage("");
      if (!selectedTicker && watchlistRows[0]) setSelectedTicker(watchlistRows[0].ticker);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to load watchlist");
    }
  }, [selectedTicker]);

  useEffect(() => {
    void loadWatchlist();
    const timer = setInterval(() => void loadWatchlist(), 15_000);
    return () => clearInterval(timer);
  }, [loadWatchlist]);

  useEffect(() => {
    if (!selectedTicker) return;
    let cancelled = false;
    void getTradeCard(selectedTicker).then((card) => {
      if (!cancelled) setTradeCard(card);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedTicker]);

  const blockingReconcile = useMemo(() => mismatches.some((item) => item.blocking), [mismatches]);
  const blockedTickers = useMemo(
    () => watchlist.filter((row) => row.data_health === "Blocked").map((row) => row.ticker),
    [watchlist],
  );
  const selectedRow = useMemo(
    () => watchlist.find((row) => row.ticker === selectedTicker) ?? null,
    [watchlist, selectedTicker],
  );

  const runAction = async (action: string, row: WatchlistOpportunity) => {
    setBusy(`${action}-${row.ticker}`);
    setErrorMessage("");
    try {
      const direction = "bullish";
      if (action === "view_trade_card") {
        setSelectedTicker(row.ticker);
        setDrawerOpen(true);
        return;
      }
      if (action === "save_decision") {
        await saveDecisionFromRuntime(row.ticker, direction, { signal_id: row.signal_id, thesis: `Watchlist save ${row.ticker}` });
      } else if (action === "run_replay") {
        await runReplay({ ticker: row.ticker, direction });
        if (row.decision_id) await patchDecision(row.decision_id, { current_status: "replayed" });
      } else if (action === "run_paper") {
        if (!row.decision_id) throw new Error("Save decision before paper trade");
        await runPaperTrade({ mode: "decision", decision_id: row.decision_id });
      } else if (action === "reject") {
        if (row.decision_id) await markDecisionRejected(row.decision_id);
        else await saveDecisionFromRuntime(row.ticker, direction, { rejected: true });
      }
      await loadWatchlist();
      if (selectedTicker === row.ticker) {
        const card = await getTradeCard(row.ticker);
        setTradeCard(card);
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Action failed");
    } finally {
      setBusy("");
    }
  };

  const leftContent = (
    <>
      <div className="panel-header">
        <h2 className="panel-title">Watchlist</h2>
      </div>
      <ul className="ticker-list">
        {watchlist.map((row) => (
          <li key={row.ticker}>
            <button
              type="button"
              className={`ticker-item ${selectedTicker === row.ticker ? "is-active" : ""}`}
              onClick={() => setSelectedTicker(row.ticker)}
            >
              <span className="mono">{row.ticker}</span>
              <span className={`severity-${row.data_health === "Blocked" ? "block" : row.data_health === "Degraded" ? "warn" : "info"}`}>
                {row.data_health}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </>
  );

  const mainContent = (
    <>
      <div className="panel-header">
        <h2 className="panel-title">Actionable Opportunities</h2>
        <p className="muted-text">Ranked opportunities with entry triggers, strategy context, and decision lifecycle actions.</p>
      </div>
      {errorMessage ? <p className="danger-text">{errorMessage}</p> : null}
      {!watchlist.length && !errorMessage ? (
        <p className="muted-text">No watchlist items yet. Upload and activate a universe first.</p>
      ) : null}
      <div className="table-wrap">
        <table className="dense-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>State</th>
              <th>Health</th>
              <th>Confidence</th>
              <th>Regime</th>
              <th>Edge</th>
              <th>Strategy</th>
              <th>Max Loss</th>
              <th>POP</th>
              <th>Liquidity</th>
              <th>Entry</th>
              <th>Invalidation</th>
              <th>Review</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {watchlist.map((row) => (
              <tr
                key={row.ticker}
                className={selectedTicker === row.ticker ? "is-active" : ""}
                onClick={() => setSelectedTicker(row.ticker)}
              >
                <td className="mono">{row.ticker}</td>
                <td>{row.state}</td>
                <td>{row.data_health}</td>
                <td className="mono">{row.confidence_total.toFixed(1)}</td>
                <td>{row.regime_label}</td>
                <td className={`mono ${row.post_cost_edge_usd >= 0 ? "success-text" : "danger-text"}`}>${row.post_cost_edge_usd.toFixed(2)}</td>
                <td>{row.suggested_strategy ?? "-"}</td>
                <td className="mono">{row.max_loss != null ? `$${row.max_loss.toFixed(0)}` : "-"}</td>
                <td className="mono">{row.pop != null ? `${(row.pop * 100).toFixed(0)}%` : "-"}</td>
                <td>{row.liquidity ?? "-"}</td>
                <td className="mono">{row.entry_zone}</td>
                <td className="mono">{row.invalidation}</td>
                <td>{row.review_status ?? "pending"}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  <div className="inline-form">
                    <button type="button" className="ghost-button" disabled={!!busy} onClick={() => void runAction("view_trade_card", row)}>Card</button>
                    <button type="button" className="ghost-button" disabled={!!busy || !!row.decision_id} onClick={() => void runAction("save_decision", row)}>Save</button>
                    <button type="button" className="ghost-button" disabled={!!busy} onClick={() => void runAction("run_replay", row)}>Replay</button>
                    <button type="button" className="ghost-button" disabled={!!busy || !row.decision_id} onClick={() => void runAction("run_paper", row)}>Paper</button>
                    <button type="button" className="ghost-button" disabled={!!busy} onClick={() => void runAction("reject", row)}>Reject</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );

  const banners = (
    <>
      {blockingReconcile ? (
        <div className="banner banner-danger">Blocking reconcile mismatch detected. Action buttons are disabled until reconciliation clears.</div>
      ) : null}
      {blockedTickers.length ? (
        <div className="banner banner-warning">Data health blocked for: {blockedTickers.join(", ")}. Trade actions are disabled for blocked tickers.</div>
      ) : null}
    </>
  );

  return (
    <>
      <AppShell left={leftContent} main={mainContent} right={<ExplainFeedPanel selectedTicker={selectedTicker} />} banners={banners} />
      <TradeCardDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        ticker={selectedTicker}
        card={tradeCard}
        globalBlocked={blockingReconcile}
        tickerDataBlocked={selectedRow?.data_health === "Blocked"}
        onUpdated={() => void loadWatchlist()}
      />
    </>
  );
}
