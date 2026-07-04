"use client";

import {
  exportPaperTradesUrl,
  ibkrFetchPositions,
  ibkrRecalculateAll,
  ibkrRefreshPrices,
  ibkrSyncFromBroker,
  setIbkrAutoSync,
} from "@/lib/paperTradeApi";
import type { PaperTradeFilters, PaperTradeSyncStatus } from "@/types/paperTrading";

type Props = {
  filters: PaperTradeFilters;
  syncStatus: PaperTradeSyncStatus | null;
  busy: boolean;
  onAction: () => void;
  onAutoSyncChange: (seconds: number) => void;
  autoSyncSeconds: number;
};

export default function PaperTradingToolbar({
  filters,
  syncStatus,
  busy,
  onAction,
  onAutoSyncChange,
  autoSyncSeconds,
}: Props) {
  async function run(action: () => Promise<unknown>) {
    try {
      await action();
      onAction();
    } catch {
      onAction();
    }
  }

  const broker = syncStatus?.broker ?? syncStatus?.gateway;
  const brokerOk = broker?.available ?? false;
  const backend = broker?.backend ?? "none";

  return (
    <section className="panel pt-toolbar">
      <div className="pt-toolbar-row">
        <button type="button" className="qqq-btn qqq-btn-primary" disabled={busy} onClick={() => void run(ibkrFetchPositions)}>
          Fetch Open Positions
        </button>
        <button type="button" className="qqq-btn" disabled={busy} onClick={() => void run(ibkrRefreshPrices)}>
          Refresh Market Prices
        </button>
        <button type="button" className="qqq-btn" disabled={busy} onClick={() => void run(ibkrRecalculateAll)}>
          Recalculate All
        </button>
        <button type="button" className="qqq-btn" disabled={busy} onClick={() => void run(ibkrSyncFromBroker)}>
          Sync From IBKR
        </button>
        <a className="qqq-btn" href={exportPaperTradesUrl("csv", filters)}>
          Export
        </a>
        <label className="pt-auto-sync">
          Auto refresh
          <select
            value={String(autoSyncSeconds)}
            onChange={(e) => {
              const sec = Number(e.target.value);
              onAutoSyncChange(sec);
              void setIbkrAutoSync(sec);
            }}
          >
            <option value="0">Manual only</option>
            <option value="60">Every 1 min</option>
            <option value="300">Every 5 min</option>
            <option value="900">Every 15 min</option>
          </select>
        </label>
      </div>
      {brokerOk ? (
        <div className="banner banner-success pt-gateway-warn">
          Broker connected ({backend}) — {broker?.message}
        </div>
      ) : (
        <div className="banner banner-danger pt-gateway-warn">
          Broker unavailable — {broker?.message ?? "not connected"}. Start IB Gateway/TWS on port 4001 (same as Spread
          Analyzer). Existing data will not be overwritten.
        </div>
      )}
      {syncStatus?.last_sync && (
        <div className="pt-sync-log muted-text">
          Last sync: {new Date(syncStatus.last_sync.synced_at).toLocaleString()} · {syncStatus.last_sync.action} ·
          updated {syncStatus.last_sync.records_updated} · new {syncStatus.last_sync.new_trades} · closed{" "}
          {syncStatus.last_sync.closed_trades} · failed {syncStatus.last_sync.failed_requests}
          {syncStatus.last_sync.message ? ` — ${syncStatus.last_sync.message}` : ""}
        </div>
      )}
    </section>
  );
}
