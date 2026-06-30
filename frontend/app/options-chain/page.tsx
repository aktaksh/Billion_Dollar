"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getOptionsChain, getShellStatus, refreshOptionsChain } from "@/lib/api";
import type { OptionsChainSnapshotOut, ShellStatus } from "@/types";

function formatTs(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function statusBannerClass(status: string) {
  if (status === "fresh") return "banner banner-success";
  if (status === "scanning") return "banner banner-info";
  if (status === "stale" || status === "partial") return "banner banner-warning";
  if (status === "failed") return "banner banner-danger";
  return "banner";
}

export default function OptionsChainPage() {
  const [symbol, setSymbol] = useState("QQQ");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [snapshot, setSnapshot] = useState<OptionsChainSnapshotOut | null>(null);
  const [shell, setShell] = useState<ShellStatus | null>(null);
  const [polling, setPolling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadSnapshot = useCallback(async (sym: string) => {
    const [data, shellStatus] = await Promise.all([getOptionsChain(sym), getShellStatus()]);
    setSnapshot(data);
    setShell(shellStatus);
    return data;
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setPolling(false);
  }, []);

  const startPolling = useCallback(
    (sym: string) => {
      stopPolling();
      setPolling(true);
      pollRef.current = setInterval(() => {
        void loadSnapshot(sym)
          .then((data) => {
            if (data.scanner_status !== "scanning") {
              setPolling(false);
              stopPolling();
            }
          })
          .catch(() => undefined);
      }, 3000);
    },
    [loadSnapshot, stopPolling],
  );

  useEffect(() => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setLoading(true);
    setError("");
    void loadSnapshot(sym)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load options chain"))
      .finally(() => setLoading(false));
    return () => stopPolling();
  }, [symbol, loadSnapshot, stopPolling]);

  useEffect(() => {
    if (snapshot?.scanner_status === "scanning" || polling) {
      startPolling(symbol.trim().toUpperCase());
    } else {
      stopPolling();
    }
  }, [snapshot?.scanner_status, polling, symbol, startPolling, stopPolling]);

  const handleRefresh = async () => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setLoading(true);
    setError("");
    try {
      const refresh = await refreshOptionsChain(sym);
      if (refresh.enqueued) {
        setPolling(true);
        startPolling(sym);
      }
      await loadSnapshot(sym);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to enqueue scan");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container page-stack">
      <section className="panel">
        <h2 className="panel-title">Options Chain Scanner</h2>
        <p className="muted-text">
          Cached QQQ subset (14–42 DTE, max 4 expiries, 8 strikes below + 12 above spot on $5
          listed grid, ~160 contracts). Manual refresh enqueues a background scan only.
        </p>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            void handleRefresh();
          }}
        >
          <input className="feed-input" value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="Symbol" />
          <button type="submit" className="primary-button" disabled={loading}>
            {loading ? "Working..." : "Refresh scan"}
          </button>
        </form>
        {error ? <div className="banner banner-danger">{error}</div> : null}
        {snapshot?.runtime_mode === "testing" ? (
          <div className="banner banner-warning">
            Testing mode — fixture or stale broker cache may be used for Strategy Builder.
          </div>
        ) : null}
        {snapshot?.runtime_mode === "production" && snapshot.chain_origin === "seeded_fixture" ? (
          <div className="banner banner-danger">
            Production mode but testing fixture is still loaded. Connect broker and refresh scan for live data.
          </div>
        ) : null}
        {snapshot ? (
          <div className="panel-sub">
            <div className={statusBannerClass(snapshot.scanner_status)}>
              Scanner: <span className="mono">{snapshot.scanner_status}</span>
              {" · "}
              Data: <span className="mono">{snapshot.data_status}</span>
              {" · "}
              Source: <span className="mono">{snapshot.chain_source}</span>
            </div>
            {snapshot.chain_source === "none" && snapshot.contracts_usable === 0 ? (
              <div className="banner banner-warning">
                No broker chain cached yet — connect TWS, then click Refresh scan.
              </div>
            ) : null}
            {snapshot.last_error ? (
              <div
                className={`banner ${
                  shell?.broker_connected && snapshot.last_error.toLowerCase().includes("serving last cache")
                    ? "banner-warning"
                    : shell?.broker_connected && snapshot.last_error.toLowerCase().includes("broker disconnected")
                      ? "banner-warning"
                      : "banner-danger"
                }`}
              >
                Last scan note: <span className="mono">{snapshot.last_error}</span>
              </div>
            ) : null}
            <ul className="dense-list">
              <li>
                <span>Last scan</span>
                <span className="mono">{formatTs(snapshot.last_scan_completed_at)}</span>
              </li>
              <li>
                <span>Underlying</span>
                <span className="mono">{snapshot.underlying_price?.toFixed(2) ?? "—"}</span>
              </li>
              <li>
                <span>Strike range</span>
                <span className="mono">
                  {snapshot.strike_low ?? "—"} – {snapshot.strike_high ?? "—"}
                </span>
              </li>
              <li>
                <span>Expiries selected</span>
                <span className="mono">{snapshot.expiries_selected.join(", ") || "—"}</span>
              </li>
              <li>
                <span>Chain origin</span>
                <span className="mono">{snapshot.chain_origin ?? "—"}</span>
              </li>
              <li>
                <span>Runtime mode</span>
                <span className="mono">{snapshot.runtime_mode ?? "—"}</span>
              </li>
              <li>
                <span>Planned / scanned / usable / rejected</span>
                <span className="mono">
                  {snapshot.contracts_planned} / {snapshot.contracts_scanned} / {snapshot.contracts_usable} /{" "}
                  {snapshot.contracts_rejected}
                </span>
              </li>
            </ul>
            {snapshot.runtime_mode === "testing" && snapshot.scan_notes.length ? (
              <div className="banner banner-warning">
                {snapshot.scan_notes.map((note) => (
                  <div key={note}>{note}</div>
                ))}
              </div>
            ) : null}
            {(snapshot.scanner_status === "stale" || snapshot.scanner_status === "partial") && (
              <div className="banner banner-warning">
                {snapshot.runtime_mode === "testing"
                  ? "Snapshot is stale or partial; testing mode may still allow Strategy Builder when enough broker contracts remain cached."
                  : "Snapshot may be off-hours or incomplete; strategy runtime blocks on stale/partial chain data."}
              </div>
            )}
          </div>
        ) : null}
      </section>

      {snapshot?.contracts.length ? (
        <section className="panel">
          <h3 className="panel-title">Cached contracts ({snapshot.contracts.length})</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Expiry</th>
                  <th>DTE</th>
                  <th>Right</th>
                  <th>Strike</th>
                  <th>Bid</th>
                  <th>Ask</th>
                  <th>Mid</th>
                  <th>Spread</th>
                  <th>Vol</th>
                  <th>OI</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.contracts.slice(0, 200).map((row) => (
                  <tr key={`${row.expiry}-${row.strike}-${row.option_type}`}>
                    <td className="mono">{row.expiry}</td>
                    <td className="mono">{row.dte}</td>
                    <td>{row.option_type}</td>
                    <td className="mono">{row.strike}</td>
                    <td className="mono">{row.bid.toFixed(2)}</td>
                    <td className="mono">{row.ask.toFixed(2)}</td>
                    <td className="mono">{row.mid.toFixed(2)}</td>
                    <td className="mono">{(row.spread_pct * 100).toFixed(1)}%</td>
                    <td className="mono">{row.volume}</td>
                    <td className="mono">{row.open_interest}</td>
                    <td>{row.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}
