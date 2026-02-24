"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";

import { getExplainFeed } from "@/lib/api";
import type { ExplainFeedItem } from "@/types";

type FeedScope = "global" | "ticker";

function tickerFromPathname(pathname: string): string | null {
  const parts = pathname.split("/").filter(Boolean);
  const idx = parts.indexOf("tickers");
  if (idx >= 0 && parts[idx + 1]) {
    return parts[idx + 1].toUpperCase();
  }
  return null;
}

function formatTs(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString();
}

export default function ExplainFeed() {
  const pathname = usePathname();
  const inferredTicker = useMemo(() => tickerFromPathname(pathname), [pathname]);
  const [scope, setScope] = useState<FeedScope>(inferredTicker ? "ticker" : "global");
  const [ticker, setTicker] = useState(inferredTicker ?? "");
  const [items, setItems] = useState<ExplainFeedItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>("");

  useEffect(() => {
    if (inferredTicker) {
      setTicker(inferredTicker);
    }
  }, [inferredTicker]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const rows = await getExplainFeed({
          ticker: scope === "ticker" && ticker.trim() ? ticker.trim().toUpperCase() : undefined,
          limit: 50,
          minutes: 180,
        });
        if (!cancelled) {
          setItems(rows);
          setError(null);
          setLastUpdated(new Date().toLocaleTimeString());
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load explain feed");
        }
      }
    };

    load();
    const handle = setInterval(load, 8000);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [scope, ticker]);

  const copyFeed = async () => {
    const text = items
      .map((item) => `${formatTs(item.ts)} [${item.severity.toUpperCase()}] ${item.step}`)
      .join("\n");
    if (!text) return;
    await navigator.clipboard.writeText(text);
  };

  return (
    <aside className="explain-feed">
      <div className="explain-feed-header">
        <h3 className="explain-feed-title">Explain Feed</h3>
        <button type="button" className="explain-feed-copy" onClick={copyFeed}>
          Copy
        </button>
      </div>
      <div className="explain-feed-controls">
        <label>
          <input type="radio" name="feedScope" checked={scope === "global"} onChange={() => setScope("global")} />
          Global
        </label>
        <label>
          <input type="radio" name="feedScope" checked={scope === "ticker"} onChange={() => setScope("ticker")} />
          Ticker
        </label>
        <input
          className="explain-feed-input"
          placeholder="Ticker (e.g. QQQ)"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          disabled={scope === "global"}
        />
      </div>
      <p className="subtle" style={{ margin: "8px 0 10px 0" }}>
        {lastUpdated ? `Updated ${lastUpdated}` : "Loading..."}
      </p>
      {error ? <p className="text-red">{error}</p> : null}
      <div className="explain-feed-list">
        {items.map((item) => (
          <details key={item.event_id} className={`explain-item explain-${item.severity}`}>
            <summary>
              <span className="explain-ts">{formatTs(item.ts)}</span>
              <span className="explain-step">{item.step}</span>
            </summary>
            <pre className="explain-details">{JSON.stringify(item.refs, null, 2)}</pre>
          </details>
        ))}
        {!items.length && !error ? <p className="subtle">No explain events yet.</p> : null}
      </div>
    </aside>
  );
}
