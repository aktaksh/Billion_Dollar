"use client";

import { useEffect, useState } from "react";

import { getShellStatus } from "@/lib/api";
import type { ShellStatus } from "@/types";

function badgeClass(status: ShellStatus["data_status"]) {
  if (status === "live") return "status-pill status-live";
  if (status === "mock") return "status-pill status-mock";
  if (status === "stale") return "status-pill status-stale";
  return "status-pill status-danger";
}

export default function GlobalStatus() {
  const [status, setStatus] = useState<ShellStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const next = await getShellStatus();
        if (!cancelled) {
          setStatus(next);
          setError("");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Shell status unavailable");
        }
      }
    };
    void load();
    const timer = setInterval(() => void load(), 15_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (error) {
    return (
      <div className="global-status panel">
        <span className="status-pill status-danger">Shell offline</span>
        <span className="muted-text">{error}</span>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="global-status panel">
        <span className="muted-text">Loading workstation state...</span>
      </div>
    );
  }

  return (
    <div className="global-status panel">
      <div className="global-status-row">
        <span className={badgeClass(status.data_status)}>Data: {status.data_status}</span>
        <span className={`status-pill ${status.broker_connected ? "status-live" : "status-danger"}`}>
          Broker: {status.broker_connected ? "connected" : "disconnected"}
        </span>
        <span className="status-pill">Mode: {status.execution_mode}</span>
        <span className="status-pill">Trading: {status.trading_mode}</span>
        <span className={`status-pill ${status.reconcile_blocking_count > 0 ? "status-stale" : "status-live"}`}>
          Reconcile: {status.reconcile_worker_status} ({status.reconcile_blocking_count})
        </span>
        <span className={`status-pill ${status.can_open_new_entries ? "status-live" : "status-danger"}`}>
          Entries: {status.can_open_new_entries ? "allowed" : "blocked"}
        </span>
      </div>
      {status.runtime_block_reason ? (
        <div className="banner banner-warning">{status.runtime_block_reason.replaceAll("_", " ")}</div>
      ) : null}
      {status.active_halts.length ? (
        <div className="banner banner-danger">Active halts: {status.active_halts.join(", ")}</div>
      ) : null}
    </div>
  );
}
