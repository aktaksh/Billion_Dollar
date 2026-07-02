"use client";

import { useMemo, useState } from "react";

import type { QqqOptionQuote } from "@/types/qqqSpreadAnalyzer";

export type OptionChainViewMode = "liquid" | "all";
export type OptionChainTypeFilter = "all" | "call" | "put";

type Props = {
  liquidOptions?: QqqOptionQuote[];
  rawOptions?: QqqOptionQuote[];
  rawCountHint?: number;
  emptyMessage?: string;
  maxHeight?: string;
  showControls?: boolean;
};

function fmtNum(v: number, digits = 2): string {
  if (!Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function fmtPct(v: number): string {
  if (!Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

export default function OptionChainTable({
  liquidOptions = [],
  rawOptions = [],
  rawCountHint,
  emptyMessage = "No option quotes in this snapshot.",
  maxHeight = "420px",
  showControls = true,
}: Props) {
  const [viewMode, setViewMode] = useState<OptionChainViewMode>("liquid");
  const [typeFilter, setTypeFilter] = useState<OptionChainTypeFilter>("all");

  const sourceRows = viewMode === "liquid" ? liquidOptions : rawOptions;
  const rows = useMemo(() => {
    if (typeFilter === "all") return sourceRows;
    return sourceRows.filter((r) => r.option_type === typeFilter);
  }, [sourceRows, typeFilter]);

  const rawCount = rawOptions.length || rawCountHint || 0;

  return (
    <>
      {showControls && (
        <div className="qqq-chain-controls">
          <label className="qqq-chain-filter">
            <span>Show</span>
            <select value={viewMode} onChange={(e) => setViewMode(e.target.value as OptionChainViewMode)}>
              <option value="liquid">Liquid only</option>
              <option value="all">All raw quotes</option>
            </select>
          </label>
          <label className="qqq-chain-filter">
            <span>Type</span>
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as OptionChainTypeFilter)}>
              <option value="all">All</option>
              <option value="call">Calls</option>
              <option value="put">Puts</option>
            </select>
          </label>
          <span className="muted-text">
            {liquidOptions.length} liquid / {rawCount} raw · {rows.length} rows
          </span>
        </div>
      )}
      {rows.length === 0 ? (
        <p className="qqq-empty" style={{ marginTop: "0.5rem" }}>
          {emptyMessage}
        </p>
      ) : (
        <div className="table-wrap qqq-table-scroll" style={{ marginTop: "0.5rem", maxHeight }}>
          <table className="qqq-table">
            <thead>
              <tr>
                <th>Expiry</th>
                <th>DTE</th>
                <th>Type</th>
                <th className="num">Strike</th>
                <th className="num">Bid</th>
                <th className="num">Ask</th>
                <th className="num">Mid</th>
                <th className="num">Spread</th>
                <th className="num">Δ</th>
                <th className="num">IV</th>
                <th className="num">OI</th>
                <th className="num">Vol</th>
                {viewMode === "all" && <th>Liq</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.expiry}-${row.option_type}-${row.strike}`}>
                  <td>{row.expiry}</td>
                  <td>{row.dte}</td>
                  <td>{row.option_type.toUpperCase()}</td>
                  <td className="num">{fmtNum(row.strike, 1)}</td>
                  <td className="num">{fmtNum(row.bid)}</td>
                  <td className="num">{fmtNum(row.ask)}</td>
                  <td className="num">{fmtNum(row.mid)}</td>
                  <td className="num">{fmtPct(row.spread_pct)}</td>
                  <td className="num">{fmtNum(row.delta, 3)}</td>
                  <td className="num">{fmtPct(row.iv)}</td>
                  <td className="num">{row.open_interest > 0 ? row.open_interest : "—"}</td>
                  <td className="num">{row.volume > 0 ? row.volume : "—"}</td>
                  {viewMode === "all" && (
                    <td>
                      <span className={row.liquid ? "badge-yes" : "badge-no"}>{row.liquid ? "yes" : "no"}</span>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
