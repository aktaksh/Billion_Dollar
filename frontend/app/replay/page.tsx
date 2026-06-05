"use client";

import { useState } from "react";

import { runReplay } from "@/lib/api";
import type { ReplayRunOut } from "@/types";

export default function ReplayPage() {
  const [ticker, setTicker] = useState("QQQ");
  const [direction, setDirection] = useState<"bullish" | "bearish">("bullish");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ReplayRunOut | null>(null);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const out = await runReplay({
        ticker: ticker.trim().toUpperCase(),
        direction,
        scenarios: [-0.04, -0.02, 0.0, 0.02, 0.04],
      });
      setResult(out);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Replay failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container page-stack">
      <section className="panel">
        <h2 className="panel-title">Replay Lab</h2>
        <p className="muted-text">Scenario replay for ranked strategy candidates.</p>
        <form className="inline-form" onSubmit={onSubmit}>
          <input className="feed-input" value={ticker} onChange={(event) => setTicker(event.target.value)} />
          <select className="feed-input" value={direction} onChange={(event) => setDirection(event.target.value as "bullish" | "bearish")}>
            <option value="bullish">Bullish</option>
            <option value="bearish">Bearish</option>
          </select>
          <button type="submit" className="primary-button" disabled={loading}>
            {loading ? "Running..." : "Run replay"}
          </button>
        </form>
        {error ? <div className="banner banner-danger">{error}</div> : null}
        {result ? (
          <p className="muted-text">
            Data status: <span className="mono">{result.data_status}</span> / as_of: <span className="mono">{result.as_of}</span>
          </p>
        ) : null}
      </section>

      {result?.results.length ? (
        <section className="panel">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Risk</th>
                  <th>Score</th>
                  <th>Avg replay PnL</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((row) => (
                  <tr key={row.strategy_type}>
                    <td>{row.strategy_type}</td>
                    <td>{row.risk_status}</td>
                    <td className="mono">{row.strategy_score.toFixed(2)}</td>
                    <td className="mono">${row.replay_avg_pnl.toFixed(2)}</td>
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
