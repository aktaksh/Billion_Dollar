"use client";

import { useState } from "react";

import { runIngestionOnce, runStrategyRuntime } from "@/lib/api";
import type { StrategyRuntimeOut } from "@/types";

export default function OptionsChainPage() {
  const [ticker, setTicker] = useState("QQQ");
  const [direction, setDirection] = useState<"bullish" | "bearish">("bullish");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [runtime, setRuntime] = useState<StrategyRuntimeOut | null>(null);

  const refreshChain = async () => {
    setLoading(true);
    setError("");
    try {
      const symbol = ticker.trim().toUpperCase();
      await runIngestionOnce({ tickers: [symbol], include_news: false });
      const next = await runStrategyRuntime({ ticker: symbol, direction, reconciliation_mismatch_active: false });
      setRuntime(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh options chain");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container page-stack">
      <section className="panel">
        <h2 className="panel-title">Options Chain</h2>
        <p className="muted-text">Broker-normalized chain ingestion with runtime freshness metadata.</p>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            void refreshChain();
          }}
        >
          <input className="feed-input" value={ticker} onChange={(event) => setTicker(event.target.value)} placeholder="Ticker" />
          <select className="feed-input" value={direction} onChange={(event) => setDirection(event.target.value as "bullish" | "bearish")}>
            <option value="bullish">Bullish</option>
            <option value="bearish">Bearish</option>
          </select>
          <button type="submit" className="primary-button" disabled={loading}>
            {loading ? "Refreshing..." : "Refresh chain"}
          </button>
        </form>
        {error ? <div className="banner banner-danger">{error}</div> : null}
        {runtime ? (
          <div className="panel-sub">
            <ul className="dense-list">
              <li>
                <span>Data status</span>
                <span className="mono">{runtime.data_status}</span>
              </li>
              <li>
                <span>Runtime allowed</span>
                <span className="mono">{runtime.runtime_allowed ? "yes" : "no"}</span>
              </li>
              <li>
                <span>Chain ref</span>
                <span className="mono">{runtime.option_chain_snapshot_ref}</span>
              </li>
              <li>
                <span>Candidates</span>
                <span className="mono">{runtime.candidates.length}</span>
              </li>
            </ul>
            {!runtime.runtime_allowed ? (
              <div className="banner banner-warning">{runtime.runtime_block_reason?.replaceAll("_", " ") ?? "Runtime blocked"}</div>
            ) : null}
          </div>
        ) : null}
      </section>

      {runtime?.candidates.length ? (
        <section className="panel">
          <h3 className="panel-title">Ranked structures from chain</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Expiry</th>
                  <th>DTE</th>
                  <th>Score</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {runtime.candidates.slice(0, 12).map((candidate) => (
                  <tr key={`${candidate.strategy_type}-${candidate.expiry}`}>
                    <td>{candidate.strategy_type}</td>
                    <td className="mono">{candidate.expiry}</td>
                    <td className="mono">{candidate.dte}</td>
                    <td className="mono">{candidate.strategy_score.toFixed(2)}</td>
                    <td>{candidate.risk_status}</td>
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
