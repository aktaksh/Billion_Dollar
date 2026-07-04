"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import SavePaperTradeDialog from "@/components/paper-trading/SavePaperTradeDialog";
import { getPaperTradeAnalytics } from "@/lib/paperTradeApi";
import { computeTradeDecision, DECISION_VERSION } from "@/lib/tradeDecision";
import { recordTradeDecision } from "@/lib/tradeDecisionApi";
import { computeMarketRegime } from "@/lib/marketRegime";
import type { PaperTradeAnalytics } from "@/types/paperTrading";
import type { TradeDecisionResult } from "@/types/tradeDecision";
import type { QqqSpreadAnalysis } from "@/types/qqqSpreadAnalyzer";

type Props = {
  data: QqqSpreadAnalysis;
  onRefresh?: () => void;
  busy?: boolean;
};

function scoreGaugeClass(score: number): string {
  if (score >= 71) return "tde-gauge-green";
  if (score >= 41) return "tde-gauge-yellow";
  return "tde-gauge-red";
}

function decisionIconClass(decision: string): string {
  if (decision === "WAIT") return "tde-decision-wait";
  if (decision.includes("Bear")) return "tde-decision-bear";
  if (decision.includes("Bull")) return "tde-decision-bull";
  return "tde-decision-neutral";
}

function confidencePct(conf: string): number {
  if (conf === "High") return 85;
  if (conf === "Medium") return 55;
  return 30;
}

function statusClass(status: string): string {
  if (status === "Preferred") return "tde-status-preferred";
  if (status === "Avoid") return "tde-status-avoid";
  if (status === "Alternative") return "tde-status-alt";
  return "tde-status-neutral";
}

export default function TradeDecisionEngine({ data, onRefresh, busy = false }: Props) {
  const [analytics, setAnalytics] = useState<PaperTradeAnalytics | null>(null);
  const [expandedWhy, setExpandedWhy] = useState(true);
  const [saveOpen, setSaveOpen] = useState(false);
  const [toast, setToast] = useState("");

  const regime = useMemo(() => computeMarketRegime(data), [data]);

  const decision: TradeDecisionResult = useMemo(
    () => computeTradeDecision(data, { regime, analytics }),
    [data, regime, analytics],
  );

  const loadAnalytics = useCallback(async () => {
    try {
      const a = await getPaperTradeAnalytics();
      setAnalytics(a);
    } catch {
      setAnalytics(null);
    }
  }, []);

  useEffect(() => {
    void loadAnalytics();
  }, [loadAnalytics]);

  const evaluate = useCallback(async () => {
    try {
      await recordTradeDecision(data.symbol, decision, data.timestamp);
    } catch {
      // non-blocking audit
    }
    onRefresh?.();
  }, [data.symbol, data.timestamp, decision, onRefresh]);

  useEffect(() => {
    if (!data.timestamp) return;
    const d = computeTradeDecision(data, { regime, analytics });
    void recordTradeDecision(data.symbol, d, data.timestamp).catch(() => undefined);
  }, [data.timestamp, data.symbol, regime, analytics, data]);

  const evaluatedLabel = new Date(decision.evaluatedAt).toLocaleString();
  const confPct = confidencePct(decision.confidence);

  return (
    <section className="panel tde-panel">
      <div className="panel-header tde-header">
        <div>
          <h2 className="panel-title">Trade Decision Engine</h2>
          <p className="muted-text tde-subtitle">
            AI-powered options strategy recommendation using technicals, market regime, options data, and risk analysis.
          </p>
        </div>
        <div className="tde-header-meta">
          <span className="muted-text">Last Evaluated: {evaluatedLabel}</span>
          <span className="muted-text">v{DECISION_VERSION}</span>
          <button type="button" className="qqq-btn" onClick={() => void evaluate()} disabled={busy}>
            Refresh
          </button>
        </div>
      </div>

      {toast && <div className="banner banner-success">{toast}</div>}

      {/* ROW 1 */}
      <div className="tde-cards-6">
        <article className="tde-card tde-card-decision">
          <div className="tde-card-label">Final Decision</div>
          <div className={`tde-decision-icon ${decisionIconClass(decision.finalDecision)}`} aria-hidden>
            {decision.finalDecision === "WAIT" ? "⏸" : decision.finalDecision.includes("Bull") ? "▲" : decision.finalDecision.includes("Bear") ? "▼" : "◆"}
          </div>
          <div className={`tde-decision-text ${decisionIconClass(decision.finalDecision)}`}>{decision.finalDecision}</div>
        </article>
        <article className="tde-card">
          <div className="tde-card-label">Trade Score</div>
          <div className={`tde-gauge ${scoreGaugeClass(decision.tradeScore)}`}>
            <div className="tde-gauge-fill" style={{ width: `${decision.tradeScore}%` }} />
            <span className="tde-gauge-value">{decision.tradeScore}</span>
          </div>
        </article>
        <article className="tde-card">
          <div className="tde-card-label">Confidence</div>
          <div className="tde-confidence-ring" style={{ "--pct": confPct } as React.CSSProperties}>
            <span>{decision.confidence}</span>
          </div>
        </article>
        <article className="tde-card">
          <div className="tde-card-label">Risk Level</div>
          <div className="tde-card-value">{decision.riskLevel}</div>
        </article>
        <article className="tde-card">
          <div className="tde-card-label">Expected Risk / Reward</div>
          <div className="tde-card-value">{decision.expectedRiskReward}</div>
        </article>
        <article className="tde-card">
          <div className="tde-card-label">Probability of Success</div>
          <div className="tde-card-value">
            {decision.probabilityOfSuccess != null ? `${decision.probabilityOfSuccess}%` : "Not Calculated"}
          </div>
        </article>
      </div>

      {/* ROW 2 */}
      <div className="tde-summary-panel">
        <h3 className="tde-section-title">Decision Summary</h3>
        <p className="tde-summary-decision">{decision.decisionSummary}</p>
        <div className="tde-summary-reason">{decision.reasonParagraph.split("\n\n").map((p) => <p key={p.slice(0, 24)}>{p}</p>)}</div>
      </div>

      {/* ROW 3 */}
      <div className="tde-breakdown">
        <h3 className="tde-section-title">Decision Breakdown</h3>
        {decision.breakdown.map((row) => (
          <div key={row.key} className="tde-breakdown-row">
            <span className="tde-breakdown-label">
              {row.label} <span className="muted-text">(0–{row.weight})</span>
            </span>
            <div className="tde-progress-track">
              <div className="tde-progress-fill" style={{ width: `${row.score}%` }} />
            </div>
            <span className="tde-breakdown-score">{row.score}</span>
            <span className="tde-breakdown-contrib">+{row.contribution}</span>
          </div>
        ))}
      </div>

      {/* ROW 4 */}
      <div className="tde-checklist">
        <h3 className="tde-section-title">Decision Checklist</h3>
        <ul className="tde-checklist-grid">
          {decision.checklist.map((item) => (
            <li key={item.label} className={item.available ? (item.passed ? "tde-check-pass" : "tde-check-fail") : "tde-check-na"}>
              <span className="tde-check-icon">{!item.available ? "—" : item.passed ? "✔" : "✖"}</span>
              {item.label}
            </li>
          ))}
        </ul>
      </div>

      {/* ROW 5 */}
      <div className="tde-recommended">
        <h3 className="tde-section-title">Recommended Strategy</h3>
        <div className="tde-recommended-grid">
          <div><strong>Strategy</strong><p>{decision.recommended.strategy}</p></div>
          <div><strong>Reason</strong><p>{decision.recommended.reason}</p></div>
          <div><strong>Ideal Entry</strong><p>{decision.recommended.idealEntry}</p></div>
          <div><strong>Profit Target</strong><p>{decision.recommended.profitTarget}</p></div>
          <div><strong>Invalidation</strong><p>{decision.recommended.invalidation}</p></div>
          <div><strong>Expected Holding Days</strong><p>{decision.recommended.expectedHoldingDays}</p></div>
          <div><strong>Ideal DTE</strong><p>{decision.recommended.idealDte}</p></div>
          <div><strong>Preferred Delta</strong><p>{decision.recommended.preferredDelta}</p></div>
          <div className="tde-recommended-full"><strong>Risk Notes</strong><p>{decision.recommended.riskNotes}</p></div>
        </div>
      </div>

      {/* ROW 6 */}
      <div className="tde-comparison">
        <h3 className="tde-section-title">Strategy Comparison</h3>
        <div className="table-wrap">
          <table className="qqq-table tde-table">
            <thead>
              <tr>
                <th>Strategy</th>
                <th className="num">Score</th>
                <th>Probability</th>
                <th>Risk</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {decision.strategyComparison.map((row) => (
                <tr key={row.strategy}>
                  <td>{row.strategy}</td>
                  <td className="num">{row.score}</td>
                  <td>{row.probability}</td>
                  <td>{row.risk}</td>
                  <td><span className={`tde-status-badge ${statusClass(row.status)}`}>{row.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ROW 7 */}
      <div className="tde-why-not">
        <button type="button" className="tde-collapse-btn" onClick={() => setExpandedWhy((v) => !v)}>
          Why NOT? {expandedWhy ? "▾" : "▸"}
        </button>
        {expandedWhy && (
          <ul className="qqq-muted-list">
            {decision.whyNot.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        )}
      </div>

      {/* ROW 8 */}
      <div className="tde-suggested">
        <h3 className="tde-section-title">Suggested Spread</h3>
        {decision.suggestedSpread ? (
          <>
            <div className="table-wrap">
              <table className="qqq-table tde-table">
                <tbody>
                  <tr><th>Long Strike</th><td>{decision.suggestedSpread.buy_strike}</td></tr>
                  <tr><th>Short Strike</th><td>{decision.suggestedSpread.sell_strike}</td></tr>
                  <tr><th>Debit</th><td className="num">{decision.suggestedSpread.net_debit.toFixed(2)}</td></tr>
                  <tr><th>Max Profit</th><td className="num">{decision.suggestedSpread.max_profit.toFixed(0)}</td></tr>
                  <tr><th>Max Loss</th><td className="num">{decision.suggestedSpread.max_loss.toFixed(0)}</td></tr>
                  <tr><th>Breakeven</th><td className="num">{decision.suggestedSpread.breakeven.toFixed(2)}</td></tr>
                  <tr><th>Delta</th><td className="num">{decision.suggestedSpread.combined_delta.toFixed(2)}</td></tr>
                  <tr><th>Liquidity Score</th><td className="num">{decision.suggestedSpread.liquidity_score.toFixed(0)}</td></tr>
                </tbody>
              </table>
            </div>
            <button type="button" className="qqq-btn qqq-btn-primary" onClick={() => setSaveOpen(true)}>
              Save to Paper Trading
            </button>
          </>
        ) : (
          <div>
            <p className="muted-text">No candidates passed filters.</p>
            <ul className="qqq-muted-list">
              {decision.noCandidateReasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {saveOpen && decision.suggestedSpread && (
        <SavePaperTradeDialog
          analysis={data}
          candidate={decision.suggestedSpread}
          onClose={() => setSaveOpen(false)}
          onSaved={(msg) => setToast(msg)}
        />
      )}
    </section>
  );
}
