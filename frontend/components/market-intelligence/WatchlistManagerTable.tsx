"use client";

import { useState } from "react";

import { patchWatchlistRow, resetWatchlist } from "@/lib/marketIntelligenceApi";
import type { MicWatchlistRow } from "@/types/marketIntelligence";

type Props = {
  rows: MicWatchlistRow[];
  onUpdated: () => void;
};

export default function WatchlistManagerTable({ rows, onUpdated }: Props) {
  const [busy, setBusy] = useState<string | null>(null);

  async function toggleEnabled(symbol: string, enabled: boolean) {
    setBusy(symbol);
    try {
      await patchWatchlistRow(symbol, { enabled: !enabled });
      onUpdated();
    } finally {
      setBusy(null);
    }
  }

  async function changePriority(symbol: string, priority: number) {
    setBusy(symbol);
    try {
      await patchWatchlistRow(symbol, { priority });
      onUpdated();
    } finally {
      setBusy(null);
    }
  }

  async function handleReset() {
    setBusy("reset");
    try {
      await resetWatchlist();
      onUpdated();
    } finally {
      setBusy(null);
    }
  }

  if (rows.length === 0) {
    return (
      <p className="muted-text mic-empty">
        Watchlist is empty. Reset to load default symbols (NVDA, AAPL, MSFT, …).
      </p>
    );
  }

  return (
    <>
      <div className="mic-toolbar">
        <button type="button" className="qqq-btn" onClick={() => void handleReset()} disabled={busy === "reset"}>
          Reset defaults
        </button>
      </div>
      <div className="table-wrap">
        <table className="qqq-table mic-table">
          <thead>
            <tr>
              <th>Enabled</th>
              <th className="num">Priority</th>
              <th>Symbol</th>
              <th>Company</th>
              <th>Sector</th>
              <th>Last News</th>
              <th className="num">Score</th>
              <th>Sentiment</th>
              <th>Next Earnings</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol}>
                <td>
                  <input
                    type="checkbox"
                    checked={r.enabled}
                    disabled={busy === r.symbol}
                    onChange={() => void toggleEnabled(r.symbol, r.enabled)}
                  />
                </td>
                <td className="num">
                  <input
                    type="number"
                    min={1}
                    max={99}
                    className="mic-priority-input"
                    value={r.priority}
                    disabled={busy === r.symbol}
                    onChange={(e) => void changePriority(r.symbol, Number(e.target.value) || r.priority)}
                  />
                </td>
                <td><strong>{r.symbol}</strong></td>
                <td>{r.company}</td>
                <td>{r.sector}</td>
                <td>{r.last_news_time ? new Date(r.last_news_time).toLocaleString() : "—"}</td>
                <td className="num">{r.news_score}</td>
                <td>{r.sentiment}</td>
                <td>{r.next_earnings ?? "—"}</td>
                <td>{r.refresh_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted-text mic-footnote">Live Finnhub earnings calendar not wired — Next Earnings uses news headlines when available.</p>
    </>
  );
}
