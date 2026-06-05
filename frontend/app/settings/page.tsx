"use client";

import { useCallback, useEffect, useState } from "react";

import { useTheme } from "@/components/ThemeProvider";
import { connectBroker, getBrokerStatus, getShellStatus } from "@/lib/api";
import type { BrokerConnectResult, BrokerStatus, ShellStatus } from "@/types";

export default function SettingsPage() {
  const { preference, setPreference } = useTheme();
  const [shell, setShell] = useState<ShellStatus | null>(null);
  const [broker, setBroker] = useState<BrokerStatus | null>(null);
  const [connectResult, setConnectResult] = useState<BrokerConnectResult | null>(null);
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [shellStatus, brokerStatus] = await Promise.all([getShellStatus(), getBrokerStatus()]);
      setShell(shellStatus);
      setBroker(brokerStatus);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings context");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onConnect = async () => {
    setConnecting(true);
    setConnectResult(null);
    setError("");
    try {
      const result = await connectBroker(true);
      setConnectResult(result);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Broker connect failed");
    } finally {
      setConnecting(false);
    }
  };

  return (
    <div className="container page-stack">
      <section className="panel">
        <h2 className="panel-title">Settings</h2>
        <p className="muted-text">Workstation preferences, TWS read-only broker connection, and execution safety context.</p>
        {error ? <div className="banner banner-danger">{error}</div> : null}

        <article className="panel-sub">
          <h3>TWS read-only connection</h3>
          <p className="muted-text">
            Billion Dollar reads market data, option chains, positions, and orders through the TWS API (socket). The app
            never places or modifies broker orders.
          </p>
          {broker ? (
            <ul className="dense-list">
              <li>
                <span>TWS reachable</span>
                <span className="mono">{broker.tws_reachable ? "yes" : "no"}</span>
              </li>
              <li>
                <span>Endpoint</span>
                <span className="mono">
                  {broker.tws_host}:{broker.tws_port} (client {broker.tws_client_id})
                </span>
              </li>
              <li>
                <span>Read-only API</span>
                <span className="mono">{broker.tws_read_only ? "yes" : "no"}</span>
              </li>
              <li>
                <span>Broker authenticated</span>
                <span className="mono">{broker.broker_authenticated ? "yes" : "no"}</span>
              </li>
              <li>
                <span>Data status</span>
                <span className="mono">{broker.data_status}</span>
              </li>
              <li>
                <span>Connection worker</span>
                <span className="mono">{broker.connection_worker_status}</span>
              </li>
            </ul>
          ) : null}
          <p className="muted-text">{broker?.message ?? "Loading broker status..."}</p>
          <ol className="muted-text" style={{ marginTop: 8, paddingLeft: 18 }}>
            <li>Install and open TWS paper trading.</li>
            <li>
              Edit → Global Configuration → API → Settings: enable ActiveX/Socket clients, check Read-Only API, set port{" "}
              <strong>7497</strong>, trusted IP <strong>127.0.0.1</strong>.
            </li>
            <li>Click Connect Broker below to open a read-only session and refresh market snapshots.</li>
          </ol>
          <div className="inline-form">
            <button type="button" className="primary-button" onClick={onConnect} disabled={connecting}>
              {connecting ? "Connecting..." : "Connect Broker"}
            </button>
            <button type="button" className="secondary-button" onClick={() => void load()} disabled={connecting}>
              Refresh status
            </button>
          </div>
          {connectResult ? (
            <div className={`banner ${connectResult.status === "connected" ? "banner-warning" : "banner-danger"}`}>
              {connectResult.message}
              {connectResult.status === "connected" ? (
                <span>
                  {" "}
                  Ingestion processed {connectResult.ingestion_processed} tickers. Data status: {connectResult.data_status}
                </span>
              ) : null}
            </div>
          ) : null}
        </article>

        <article className="panel-sub">
          <h3>Theme</h3>
          <div className="inline-form">
            {(["system", "light", "dark"] as const).map((option) => (
              <button
                key={option}
                type="button"
                className={preference === option ? "primary-button" : "secondary-button"}
                onClick={() => setPreference(option)}
              >
                {option}
              </button>
            ))}
          </div>
        </article>

        {shell ? (
          <article className="panel-sub">
            <h3>Execution safety</h3>
            <ul className="dense-list">
              <li>
                <span>Execution mode</span>
                <span className="mono">{shell.execution_mode}</span>
              </li>
              <li>
                <span>Trading mode</span>
                <span className="mono">{shell.trading_mode}</span>
              </li>
              <li>
                <span>Reconcile blocking count</span>
                <span className="mono">{shell.reconcile_blocking_count}</span>
              </li>
              <li>
                <span>New entries</span>
                <span className="mono">{shell.can_open_new_entries ? "allowed" : "blocked"}</span>
              </li>
            </ul>
          </article>
        ) : null}
      </section>
    </div>
  );
}
