"use client";

import { useEffect, useMemo, useState } from "react";

import { getExplainFeed } from "@/lib/api";
import type { ExplainFeedItem } from "@/types";

type Props = {
  selectedTicker?: string | null;
};

type FeedScope = "global" | "ticker" | "decision" | "risk" | "broker" | "paper" | "review";

const SCOPES: FeedScope[] = ["global", "ticker", "decision", "risk", "broker", "paper", "review"];

function formatTs(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString();
}

export default function ExplainFeedPanel({ selectedTicker }: Props) {
  const [scope, setScope] = useState<FeedScope>(selectedTicker ? "ticker" : "global");
  const [tickerInput, setTickerInput] = useState(selectedTicker ?? "");
  const [decisionInput, setDecisionInput] = useState("");
  const [rows, setRows] = useState<ExplainFeedItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string>("");

  useEffect(() => {
    if (selectedTicker) setTickerInput(selectedTicker);
  }, [selectedTicker]);

  const activeTicker = useMemo(() => tickerInput.trim().toUpperCase(), [tickerInput]);
  const activeDecision = useMemo(() => decisionInput.trim(), [decisionInput]);

  useEffect(() => {
    let isCancelled = false;
    const load = async () => {
      try {
        const data = await getExplainFeed({
          scope: scope === "ticker" && !activeTicker ? undefined : scope,
          ticker: scope === "ticker" && activeTicker ? activeTicker : undefined,
          decision_id: scope === "decision" && activeDecision ? activeDecision : undefined,
          limit: 50,
        });
        if (!isCancelled) {
          setRows(data);
          setError(null);
          setUpdatedAt(new Date().toLocaleTimeString());
        }
      } catch (err) {
        if (!isCancelled) {
          setError(err instanceof Error ? err.message : "Failed to load explain feed");
        }
      }
    };

    void load();
    const poll = setInterval(() => void load(), 10_000);
    return () => {
      isCancelled = true;
      clearInterval(poll);
    };
  }, [scope, activeTicker, activeDecision]);

  return (
    <section className="panel explain-feed-panel">
      <div className="panel-header">
        <h2 className="panel-title">Explain Feed</h2>
      </div>
      <div className="feed-controls">
        {SCOPES.map((s) => (
          <label key={s} className="feed-scope">
            <input type="radio" checked={scope === s} onChange={() => setScope(s)} />
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </label>
        ))}
      </div>
      {scope === "ticker" ? (
        <input
          className="feed-input mono"
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
          placeholder="QQQ"
        />
      ) : null}
      {scope === "decision" ? (
        <input
          className="feed-input mono"
          value={decisionInput}
          onChange={(e) => setDecisionInput(e.target.value)}
          placeholder="decision_id"
        />
      ) : null}
      <p className="muted-text">{updatedAt ? `Updated ${updatedAt}` : "Loading feed..."}</p>
      {error ? <p className="danger-text">{error}</p> : null}
      <div className="feed-list">
        {rows.map((row) => (
          <details key={row.event_id} className={`feed-item severity-${row.severity}`}>
            <summary>
              <span className="mono feed-ts">{formatTs(row.ts)}</span>
              <span>{row.human_message ?? row.step}</span>
            </summary>
            <div className="feed-details">
              <p className="muted-text">
                {row.scope ? `${row.scope} · ` : ""}
                {row.ticker ? `${row.ticker} · ` : ""}
                {row.event_type ?? row.step}
                {row.linked_decision_id ? ` · decision ${row.linked_decision_id}` : ""}
              </p>
              <pre className="mono">{JSON.stringify(row.refs, null, 2)}</pre>
            </div>
          </details>
        ))}
        {!rows.length && !error ? <p className="muted-text">No feed entries yet.</p> : null}
      </div>
    </section>
  );
}
