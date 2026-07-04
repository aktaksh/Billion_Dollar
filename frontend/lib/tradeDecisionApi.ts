import type { TradeDecisionResult } from "@/types/tradeDecision";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function recordTradeDecision(
  symbol: string,
  decision: TradeDecisionResult,
  analysisTimestamp: string,
): Promise<{ id: string; saved: boolean }> {
  return fetch(`${API_BASE}/api/trade-decision/record`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      symbol,
      analysis_timestamp: analysisTimestamp,
      decision: decision.finalDecision,
      trade_score: decision.tradeScore,
      confidence: decision.confidence,
      market_regime: decision.marketRegimeLabel,
      strategy: decision.recommended.strategy,
      reason: decision.reasonParagraph,
      entry_price: null,
      entry_trigger: decision.recommended.idealEntry,
      target: decision.recommended.profitTarget,
      stop: decision.recommended.invalidation,
      risk_level: decision.riskLevel,
      probability: decision.probabilityOfSuccess,
      summary: decision.decisionSummary,
      summary_json: decision,
    }),
  }).then(async (res) => {
    if (!res.ok) {
      const msg = await res.text();
      throw new Error(msg || "Failed to record decision");
    }
    return res.json() as Promise<{ id: string; saved: boolean }>;
  });
}
