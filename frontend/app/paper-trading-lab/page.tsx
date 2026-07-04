"use client";

import { useCallback, useEffect, useState } from "react";

import ClosedTradesTable from "@/components/paper-trading/ClosedTradesTable";
import OpenTradesTable from "@/components/paper-trading/OpenTradesTable";
import PaperTradeCard, { summaryCards } from "@/components/paper-trading/PaperTradeCard";
import PaperTradingToolbar from "@/components/paper-trading/PaperTradingToolbar";
import PerformanceDashboard from "@/components/paper-trading/PerformanceDashboard";
import {
  closePaperTrade,
  getIbkrSyncStatus,
  getPaperTradeAnalytics,
  getPaperTradeSummary,
  ibkrSyncFromBroker,
  listPaperTrades,
  setIbkrAutoSync,
} from "@/lib/paperTradeApi";
import type { PaperTrade, PaperTradeAnalytics, PaperTradeSummary, PaperTradeSyncStatus } from "@/types/paperTrading";
import "@/styles/paper-trading.css";

type Tab = "open" | "closed";

const AUTO_SYNC_KEY = "paper_trading_auto_sync_seconds";

export default function PaperTradingPage() {
  const [tab, setTab] = useState<Tab>("open");
  const [symbol, setSymbol] = useState("");
  const [strategy, setStrategy] = useState("");
  const [profitOnly, setProfitOnly] = useState(false);
  const [lossOnly, setLossOnly] = useState(false);
  const [openTrades, setOpenTrades] = useState<PaperTrade[]>([]);
  const [closedTrades, setClosedTrades] = useState<PaperTrade[]>([]);
  const [summary, setSummary] = useState<PaperTradeSummary | null>(null);
  const [analytics, setAnalytics] = useState<PaperTradeAnalytics | null>(null);
  const [syncStatus, setSyncStatus] = useState<PaperTradeSyncStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [autoSyncSeconds, setAutoSyncSeconds] = useState(0);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(AUTO_SYNC_KEY);
      if (stored != null) setAutoSyncSeconds(Number(stored) || 0);
    } catch {
      // ignore
    }
  }, []);

  const filters = {
    symbol: symbol || undefined,
    strategy_type: strategy || undefined,
    profit_only: profitOnly || undefined,
    loss_only: lossOnly || undefined,
  };

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const [open, closed, sum, anal, sync] = await Promise.all([
        listPaperTrades({ ...filters, status: "OPEN" }),
        listPaperTrades({ ...filters }).then((rows) => rows.filter((r) => r.status === "CLOSED" || r.status === "EXPIRED")),
        getPaperTradeSummary(),
        getPaperTradeAnalytics(),
        getIbkrSyncStatus(),
      ]);
      setOpenTrades(open);
      setClosedTrades(closed);
      setSummary(sum);
      setAnalytics(anal);
      setSyncStatus(sync);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load paper trades");
    } finally {
      setBusy(false);
    }
  }, [symbol, strategy, profitOnly, lossOnly]);

  useEffect(() => {
    if (autoSyncSeconds <= 0) return undefined;
    const timer = setInterval(() => {
      void ibkrSyncFromBroker().then(() => load());
    }, autoSyncSeconds * 1000);
    return () => clearInterval(timer);
  }, [autoSyncSeconds, load]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleClose(trade: PaperTrade) {
    const reason = window.prompt("Exit reason?", "Manual close");
    if (!reason) return;
    try {
      await closePaperTrade(trade.id, reason);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Close failed");
    }
  }

  function handleAutoSyncChange(seconds: number) {
    setAutoSyncSeconds(seconds);
    try {
      localStorage.setItem(AUTO_SYNC_KEY, String(seconds));
    } catch {
      // ignore
    }
    void setIbkrAutoSync(seconds);
  }

  return (
    <div className="container page-stack pt-page">
      <div className="panel-header">
        <h1 className="panel-title">Paper Trading Lab</h1>
        <p className="muted-text">Journal + IBKR Client Portal sync — research only, no order routing.</p>
      </div>

      {error && <div className="banner banner-danger">{error}</div>}

      <PaperTradingToolbar
        filters={filters}
        syncStatus={syncStatus}
        busy={busy}
        onAction={() => void load()}
        onAutoSyncChange={handleAutoSyncChange}
        autoSyncSeconds={autoSyncSeconds}
      />

      {summary && (
        <div className="pt-card-grid">
          {summaryCards(summary).map((card) => (
            <PaperTradeCard key={card.label} {...card} />
          ))}
        </div>
      )}

      <section className="panel pt-filters">
        <div className="pt-filter-row">
          <label>
            Symbol
            <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="QQQ" />
          </label>
          <label>
            Strategy
            <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
              <option value="">All</option>
              <option value="Bull Call Spread">Bull Call Spread</option>
              <option value="Bear Put Spread">Bear Put Spread</option>
              <option value="Bull Put Spread">Bull Put Spread</option>
              <option value="Bear Call Spread">Bear Call Spread</option>
            </select>
          </label>
          <label className="pt-check">
            <input type="checkbox" checked={profitOnly} onChange={(e) => setProfitOnly(e.target.checked)} />
            Profit only
          </label>
          <label className="pt-check">
            <input type="checkbox" checked={lossOnly} onChange={(e) => setLossOnly(e.target.checked)} />
            Loss only
          </label>
          <button type="button" className="qqq-btn" onClick={() => void load()} disabled={busy}>
            {busy ? "Loading…" : "Apply filters"}
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="pt-tabs">
          <button type="button" className={tab === "open" ? "is-active" : ""} onClick={() => setTab("open")}>
            Open ({openTrades.length})
          </button>
          <button type="button" className={tab === "closed" ? "is-active" : ""} onClick={() => setTab("closed")}>
            Closed ({closedTrades.length})
          </button>
        </div>
        {tab === "open" ? <OpenTradesTable trades={openTrades} onClose={(t) => void handleClose(t)} /> : null}
        {tab === "closed" ? <ClosedTradesTable trades={closedTrades} /> : null}
      </section>

      <PerformanceDashboard analytics={analytics} />
    </div>
  );
}
