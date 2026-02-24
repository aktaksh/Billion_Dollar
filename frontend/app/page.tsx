"use client";

import { useEffect, useMemo, useState } from "react";

import AppShell from "@/components/AppShell";
import ExplainFeedPanel from "@/components/ExplainFeedPanel";
import TradeCardDrawer from "@/components/TradeCardDrawer";
import { getReconcileMismatches, getTradeCard, getWatchlist } from "@/lib/api";
import type { ReconcileMismatch, TradeCard, WatchlistOpportunity } from "@/types";

export default function WatchlistHomePage() {
  const [watchlist, setWatchlist] = useState<WatchlistOpportunity[]>([]);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [tradeCard, setTradeCard] = useState<TradeCard | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [mismatches, setMismatches] = useState<ReconcileMismatch[]>([]);
  const [errorMessage, setErrorMessage] = useState<string>("");

  const loadWatchlist = async () => {
    try {
      const [watchlistRows, mismatchRows] = await Promise.all([getWatchlist(), getReconcileMismatches()]);
      setWatchlist(watchlistRows);
      setMismatches(mismatchRows);
      setErrorMessage("");
      if (!selectedTicker && watchlistRows[0]) setSelectedTicker(watchlistRows[0].ticker);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to load watchlist");
    }
  };

  useEffect(() => {
    void loadWatchlist();
    const timer = setInterval(() => {
      void loadWatchlist();
    }, 15_000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!selectedTicker) return;
    let cancelled = false;
    const loadCard = async () => {
      try {
        const card = await getTradeCard(selectedTicker);
        if (!cancelled) setTradeCard(card);
      } catch {
        if (!cancelled) setTradeCard(null);
      }
    };
    void loadCard();
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
        <p className="muted-text">Dense trading view with data-health and risk context.</p>
      </div>
      {errorMessage ? <p className="danger-text">{errorMessage}</p> : null}
      {!watchlist.length && !errorMessage ? <p className="muted-text">No watchlist items yet. Upload and activate a universe first.</p> : null}
      <div className="table-wrap">
        <table className="dense-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>State</th>
              <th>Health</th>
              <th>Confidence</th>
              <th>Regime</th>
              <th>Post-Cost Edge</th>
              <th>Entry</th>
              <th>Invalidation</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {watchlist.map((row) => (
              <tr
                key={row.ticker}
                className={selectedTicker === row.ticker ? "is-active" : ""}
                onClick={() => {
                  setSelectedTicker(row.ticker);
                  setDrawerOpen(true);
                }}
              >
                <td className="mono">{row.ticker}</td>
                <td>{row.state}</td>
                <td>{row.data_health}</td>
                <td className="mono">{row.confidence_total.toFixed(1)}</td>
                <td>{row.regime_label}</td>
                <td className={`mono ${row.post_cost_edge_usd >= 0 ? "success-text" : "danger-text"}`}>${row.post_cost_edge_usd.toFixed(2)}</td>
                <td className="mono">{row.entry_zone}</td>
                <td className="mono">{row.invalidation}</td>
                <td>{row.next_action}</td>
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
      />
    </>
  );
}


