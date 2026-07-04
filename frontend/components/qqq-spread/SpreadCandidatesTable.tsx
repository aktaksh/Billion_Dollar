"use client";

import { useMemo, useState } from "react";

import SavePaperTradeDialog from "@/components/paper-trading/SavePaperTradeDialog";
import type { StrategyFilter } from "@/lib/marketRegime";
import type { QqqSpreadAnalysis, QqqSpreadCandidate } from "@/types/qqqSpreadAnalyzer";

type Props = {
  data: QqqSpreadAnalysis;
  strategyFilter?: StrategyFilter;
  onSaved?: (message: string) => void;
};

function filterBannerClass(filter: StrategyFilter): string {
  if (filter === "Bull Call Spread") return "qqq-regime-filter-bull";
  if (filter === "Bear Put Spread") return "qqq-regime-filter-bear";
  return "qqq-regime-filter-wait";
}

function filterBannerText(filter: StrategyFilter): string {
  if (filter === "Bull Call Spread") return "Bull Call Spread allowed";
  if (filter === "Bear Put Spread") return "Bear Put Spread allowed";
  return "WAIT — no strategy filter passed (candidates shown for research only)";
}

function rejectionHints(data: QqqSpreadAnalysis): string[] {
  const hints: string[] = [];
  if (data.risk_notes?.length) hints.push(...data.risk_notes);
  if (data.score.invalid_conditions.length) hints.push(...data.score.invalid_conditions);
  const diag = data.diagnostics;
  if ((diag.liquid_quotes ?? 0) === 0 && (diag.raw_quotes ?? 0) > 0) {
    hints.push("Wide bid/ask spread, low open interest, or low volume may have filtered all legs");
  }
  if ((diag.raw_quotes ?? 0) === 0) hints.push("No raw option quotes received");
  for (const fail of diag.qualification_failures ?? []) {
    hints.push(`${fail.failed_count} contracts failed qualification for expiry ${fail.expiry}. ${fail.reason_hint}`);
  }

  const expirySearch = (data as unknown as Record<string, unknown>).expiry_search as Record<string, unknown> | undefined;
  if (expirySearch?.no_candidate_reasons) {
    const reasons = expirySearch.no_candidate_reasons as string[];
    hints.push(...reasons.slice(0, 3));
  }

  return [...new Set(hints)];
}

type GroupedExpiry = {
  expiry: string;
  dte: number;
  candidates: QqqSpreadCandidate[];
};

function groupByExpiry(rows: QqqSpreadCandidate[]): GroupedExpiry[] {
  const map = new Map<string, QqqSpreadCandidate[]>();
  for (const row of rows) {
    const key = row.expiry;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(row);
  }
  const groups: GroupedExpiry[] = [];
  for (const [expiry, candidates] of map) {
    candidates.sort((a, b) => b.liquidity_score - a.liquidity_score);
    groups.push({ expiry, dte: candidates[0].dte, candidates });
  }
  groups.sort((a, b) => a.dte - b.dte);
  return groups;
}

export default function SpreadCandidatesTable({ data, strategyFilter = "WAIT", onSaved }: Props) {
  const rows = data.spread_candidates;
  const hints = rejectionHints(data);
  const acceptedCount = rows.filter((r) => r.status === "Accepted").length;
  const [saveCandidate, setSaveCandidate] = useState<QqqSpreadCandidate | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [toast, setToast] = useState("");

  const grouped = useMemo(() => groupByExpiry(rows), [rows]);
  const hasMultipleExpiries = grouped.length > 1;

  function handleSaved(message: string) {
    setToast(message);
    onSaved?.(message);
  }

  function formatExpiry(exp: string): string {
    return exp.includes("-") ? exp : `${exp.slice(0, 4)}-${exp.slice(4, 6)}-${exp.slice(6, 8)}`;
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Spread Candidates</h2>
        <span className="muted-text" style={{ fontSize: "0.75rem" }}>
          {rows.length} candidates across {grouped.length} {grouped.length === 1 ? "expiry" : "expiries"}
        </span>
        {acceptedCount > 0 && (
          <button type="button" className="qqq-btn qqq-btn-primary" onClick={() => setBulkOpen(true)}>
            Save all to Paper Trading ({acceptedCount})
          </button>
        )}
      </div>
      <div className={`qqq-regime-filter-banner ${filterBannerClass(strategyFilter)}`}>
        {filterBannerText(strategyFilter)}
      </div>
      {toast && <div className="banner banner-success">{toast}</div>}
      {rows.length === 0 ? (
        <>
          <p className="qqq-empty">No valid spreads found across scanned expiries.</p>
          {hints.length > 0 && (
            <ul className="qqq-muted-list">
              {hints.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <>
          {grouped.map((group) => (
            <div key={group.expiry} style={{ marginBottom: hasMultipleExpiries ? "1.25rem" : 0 }}>
              {hasMultipleExpiries && (
                <div style={{ padding: "6px 12px", fontSize: "0.8rem", fontWeight: 600, borderBottom: "1px solid var(--border)" }}>
                  {formatExpiry(group.expiry)} — {group.dte} DTE ({group.candidates.length} spreads)
                </div>
              )}
              <div className="table-wrap">
                <table className="qqq-table">
                  <thead>
                    <tr>
                      <th>Strategy</th>
                      {!hasMultipleExpiries && <th>Expiry</th>}
                      <th>DTE</th>
                      <th>Long</th>
                      <th>Short</th>
                      <th className="num">Debit</th>
                      <th className="num">Max loss</th>
                      <th className="num">Max profit</th>
                      <th className="num">BE</th>
                      <th className="num">R/R</th>
                      <th className="num">Δ</th>
                      <th className="num">Θ</th>
                      <th className="num">Liq</th>
                      <th>Status</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {group.candidates.map((row, idx) => (
                      <tr key={`${row.expiry}-${row.long_leg}-${idx}`}>
                        <td>{row.strategy}</td>
                        {!hasMultipleExpiries && <td>{formatExpiry(row.expiry)}</td>}
                        <td>{row.dte}</td>
                        <td>{row.long_leg}</td>
                        <td>{row.short_leg}</td>
                        <td className="num">{row.net_debit.toFixed(2)}</td>
                        <td className="num">{row.max_loss.toFixed(0)}</td>
                        <td className="num">{row.max_profit.toFixed(0)}</td>
                        <td className="num">{row.breakeven.toFixed(2)}</td>
                        <td className="num">{row.reward_risk.toFixed(2)}</td>
                        <td className="num">{row.combined_delta.toFixed(2)}</td>
                        <td className="num">{row.combined_theta.toFixed(2)}</td>
                        <td className="num">{row.liquidity_score.toFixed(0)}</td>
                        <td>
                          <span className="badge-yes">{row.status}</span>
                        </td>
                        <td>
                          {row.status === "Accepted" && (
                            <button type="button" className="qqq-btn" onClick={() => setSaveCandidate(row)}>
                              Save
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </>
      )}
      {saveCandidate && (
        <SavePaperTradeDialog
          analysis={data}
          candidate={saveCandidate}
          onClose={() => setSaveCandidate(null)}
          onSaved={handleSaved}
        />
      )}
      {bulkOpen && (
        <SavePaperTradeDialog
          analysis={data}
          candidate={null}
          bulk
          onClose={() => setBulkOpen(false)}
          onSaved={handleSaved}
        />
      )}
    </section>
  );
}
