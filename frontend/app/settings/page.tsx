"use client";

import { useCallback, useEffect, useState } from "react";

import { useTheme } from "@/components/ThemeProvider";
import { connectBroker, getBrokerStatus, getRuntimeMode, getShellStatus, refreshOptionsChain, setRuntimeMode } from "@/lib/api";
import type { BrokerConnectResult, BrokerStatus, RuntimeMode, RuntimeModeOut, ShellStatus } from "@/types";

export default function SettingsPage() {
  const { preference, setPreference } = useTheme();
  const [shell, setShell] = useState<ShellStatus | null>(null);
  const [broker, setBroker] = useState<BrokerStatus | null>(null);
  const [runtimeMode, setRuntimeModeState] = useState<RuntimeModeOut | null>(null);
  const [connectResult, setConnectResult] = useState<BrokerConnectResult | null>(null);
  const [error, setError] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [modeSaving, setModeSaving] = useState(false);
  const [refreshingChain, setRefreshingChain] = useState(false);

  const load = useCallback(async () => {
    try {
      const [shellStatus, brokerStatus, modeStatus] = await Promise.all([
        getShellStatus(),
        getBrokerStatus(),
        getRuntimeMode("QQQ"),
      ]);
      setShell(shellStatus);
      setBroker(brokerStatus);
      setRuntimeModeState(modeStatus);
      setConnectResult((prev) => {
        if (brokerStatus.broker_authenticated && prev && prev.status !== "connected") {
          return null;
        }
        return prev;
      });
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
      const result = await connectBroker(false);
      setConnectResult(result);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Broker connect failed");
    } finally {
      setConnecting(false);
    }
  };

  const onModeChange = async (mode: RuntimeMode) => {
    setModeSaving(true);
    setError("");
    try {
      const result = await setRuntimeMode(mode, "QQQ");
      setRuntimeModeState(result);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update runtime mode");
    } finally {
      setModeSaving(false);
    }
  };

  const onRefreshChain = async () => {
    setRefreshingChain(true);
    setError("");
    try {
      await refreshOptionsChain("QQQ");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh QQQ chain");
    } finally {
      setRefreshingChain(false);
    }
  };

  return (
    <div className="container page-stack">
      <section className="panel">
        <h2 className="panel-title">Settings</h2>
        <p className="muted-text">Workstation preferences, TWS read-only broker connection, and execution safety context.</p>
        {error ? <div className="banner banner-danger">{error}</div> : null}

        <article className="panel-sub">
          <h3>Data runtime mode</h3>
          <p className="muted-text">
            Switch between live IBKR production data and off-hours testing fixtures without editing config files.
          </p>
          {runtimeMode ? (
            <ul className="dense-list">
              <li>
                <span>Current mode</span>
                <span className="mono">{runtimeMode.runtime_mode}</span>
              </li>
              <li>
                <span>Chain origin</span>
                <span className="mono">{runtimeMode.chain_origin}</span>
              </li>
              <li>
                <span>Scanner status</span>
                <span className="mono">{runtimeMode.scanner_status ?? "-"}</span>
              </li>
              <li>
                <span>Live broker chain loaded</span>
                <span className="mono">{runtimeMode.is_production_valid_chain ? "yes" : "no"}</span>
              </li>
            </ul>
          ) : null}
          {runtimeMode ? (
            <p className="muted-text" style={{ marginTop: 8 }}>
              {runtimeMode.runtime_mode === "production" && !runtimeMode.is_production_valid_chain
                ? "Production mode requires a live IBKR scan. Connect broker, then refresh the QQQ chain."
                : runtimeMode.runtime_mode === "testing"
                  ? "Testing mode uses fixtures or stale cache. Live broker chain is not required."
                  : "Chain cache is from a live broker scan and suitable for production strategy runtime."}
            </p>
          ) : null}
          <div className="inline-form" style={{ marginTop: 8 }}>
            <button
              type="button"
              className={runtimeMode?.runtime_mode === "production" ? "primary-button" : "secondary-button"}
              disabled={modeSaving}
              onClick={() => void onModeChange("production")}
            >
              Production (live IBKR)
            </button>
            <button
              type="button"
              className={runtimeMode?.runtime_mode === "testing" ? "primary-button" : "secondary-button"}
              disabled={modeSaving}
              onClick={() => void onModeChange("testing")}
            >
              Testing (fixture)
            </button>
            <button type="button" className="secondary-button" disabled={refreshingChain} onClick={() => void onRefreshChain()}>
              {refreshingChain ? "Refreshing..." : "Refresh QQQ chain"}
            </button>
          </div>
          {runtimeMode?.message ? <div className="banner banner-warning">{runtimeMode.message}</div> : null}
        </article>

        <article className="panel-sub">
          <h3>IBKR read-only connection</h3>
          <p className="muted-text">
            Billion Dollar reads market data, option chains, positions, and orders through the IBKR socket API. The app
            never places or modifies broker orders.
          </p>
          {broker ? (
            <ul className="dense-list">
              <li>
                <span>Client ID</span>
                <span className="mono">{broker.tws_client_id}</span>
              </li>
              <li>
                <span>Broker session active</span>
                <span className="mono">{broker.broker_authenticated ? "yes" : "no"}</span>
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
            <li>Open IB Gateway or TWS and log in.</li>
            <li>
              Configure → Settings → API: enable ActiveX/Socket clients, check Read-Only API, set socket port{" "}
              <strong>{broker?.tws_port ?? "…"}</strong> (configured in backend config.yaml), trusted IP{" "}
              <strong>127.0.0.1</strong>.
            </li>
            <li>Click Connect Broker below to open a read-only session, then refresh the QQQ chain in Production mode.</li>
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
            <div
              className={`banner ${
                connectResult.status === "connected"
                  ? "banner-success"
                  : connectResult.next_action === "client_id_in_use" ||
                      connectResult.message.toLowerCase().includes("client id")
                    ? "banner-danger"
                    : connectResult.status === "tws_unreachable"
                      ? "banner-danger"
                      : "banner-danger"
              }`}
            >
              {connectResult.next_action === "client_id_in_use" ||
              connectResult.message.toLowerCase().includes("already in use") ? (
                <strong>Client ID conflict — </strong>
              ) : null}
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
