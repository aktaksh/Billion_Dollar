"use client";

import { useEffect, useMemo, useState } from "react";

import { getExplainFeed } from "@/lib/api";
import type { ExplainFeedItem } from "@/types";

type Props = {
  selectedTicker?: string | null;
};

type FeedScope = "global" | "ticker";

function formatTs(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString();
}

export default function ExplainFeedPanel({ selectedTicker }: Props) {
  const [scope, setScope] = useState<FeedScope>(selectedTicker ? "ticker" : "global");
  const [tickerInput, setTickerInput] = useState(selectedTicker ?? "");
  const [rows, setRows] = useState<ExplainFeedItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string>("");

  useEffect(() => {
    if (selectedTicker) setTickerInput(selectedTicker);
  }, [selectedTicker]);

  const activeTicker = useMemo(() => tickerInput.trim().toUpperCase(), [tickerInput]);

  useEffect(() => {
    let isCancelled = false;
    const load = async () => {
      try {
        const data = await getExplainFeed({
          ticker: scope === "ticker" && activeTicker ? activeTicker : undefined,
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
    const poll = setInterval(() => {
      void load();
    }, 10_000);
    return () => {
      isCancelled = true;
      clearInterval(poll);
    };
  }, [scope, activeTicker]);

  return (
    <section className="panel explain-feed-panel">
      <div className="panel-header">
        <h2 className="panel-title">Explain Feed</h2>
      </div>
      <div className="feed-controls">
        <label className="feed-scope">
          <input type="radio" checked={scope === "global"} onChange={() => setScope("global")} />
          Global
        </label>
        <label className="feed-scope">
          <input type="radio" checked={scope === "ticker"} onChange={() => setScope("ticker")} />
          Ticker
        </label>
        <input
          className="feed-input mono"
          value={tickerInput}
          disabled={scope === "global"}
          onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
          placeholder="QQQ"
        />
      </div>
      <p className="muted-text">{updatedAt ? `Updated ${updatedAt}` : "Loading feed..."}</p>
      {error ? <p className="danger-text">{error}</p> : null}
      <div className="feed-list">
        {rows.map((row) => (
          <details key={row.event_id} className={`feed-item severity-${row.severity}`}>
            <summary>
              <span className="mono feed-ts">{formatTs(row.ts)}</span>
              <span>{row.step}</span>
            </summary>
            <pre className="feed-details mono">{JSON.stringify(row.refs, null, 2)}</pre>
          </details>
        ))}
        {!rows.length && !error ? <p className="muted-text">No feed entries yet.</p> : null}
      </div>
    </section>
  );
}
