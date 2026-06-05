import { patchDecision, runStrategyRuntime, saveDecision } from "@/lib/api";
import type { StrategyCandidateOut, StrategyRuntimeOut, TradeDecision } from "@/types";

export async function runtimeForSymbol(
  symbol: string,
  direction: "bullish" | "bearish" = "bullish",
): Promise<StrategyRuntimeOut> {
  return runStrategyRuntime({
    ticker: symbol.trim().toUpperCase(),
    direction,
    reconciliation_mismatch_active: false,
    thresholds: { max_loss_per_trade_usd: 500, min_probability_profit: 0.4 },
  });
}

export function pickBestCandidate(candidates: StrategyCandidateOut[]): StrategyCandidateOut | null {
  const allowed = candidates.find((c) => c.risk_status === "allow");
  return allowed ?? candidates[0] ?? null;
}

export async function saveDecisionFromRuntime(
  symbol: string,
  direction: "bullish" | "bearish",
  opts?: {
    candidate?: StrategyCandidateOut;
    runtime?: StrategyRuntimeOut;
    signal_id?: string | null;
    thesis?: string;
    rejected?: boolean;
  },
): Promise<TradeDecision> {
  const runtime = opts?.runtime ?? (await runtimeForSymbol(symbol, direction));
  const candidate = opts?.candidate ?? pickBestCandidate(runtime.candidates);
  if (!candidate) {
    throw new Error("No strategy candidate available to save as decision");
  }
  return saveDecision({
    candidate,
    symbol: symbol.trim().toUpperCase(),
    direction,
    signal_id: opts?.signal_id ?? null,
    confidence: candidate.strategy_score,
    edge: candidate.expected_value,
    market_regime: runtime.data_status,
    thesis: opts?.thesis ?? `Saved from ${symbol} runtime flow`,
    data_status: runtime.data_status,
    broker_status: "disconnected",
    reconciliation_status: "ok",
    rejected: opts?.rejected ?? false,
  });
}

export async function rejectCandidateViaSave(
  symbol: string,
  direction: "bullish" | "bearish",
  candidate?: StrategyCandidateOut,
): Promise<TradeDecision> {
  return saveDecisionFromRuntime(symbol, direction, { candidate, rejected: true });
}

export async function markDecisionRejected(decisionId: string): Promise<TradeDecision> {
  return patchDecision(decisionId, { rejected: true });
}
