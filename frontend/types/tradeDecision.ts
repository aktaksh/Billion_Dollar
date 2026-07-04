import type { QqqConfidence, QqqSpreadCandidate } from "@/types/qqqSpreadAnalyzer";

export type FinalDecision =
  | "Bull Call Spread"
  | "Bear Put Spread"
  | "Bull Put Spread"
  | "Bear Call Spread"
  | "Iron Condor"
  | "WAIT";

export type DecisionRiskLevel = "Low" | "Medium" | "High" | "Extreme";

export type StrategyStatus = "Preferred" | "Alternative" | "Acceptable" | "Neutral" | "Avoid";

export interface TradeDecisionWeights {
  trend: number;
  momentum: number;
  marketRegime: number;
  volatility: number;
  liquidity: number;
  riskReward: number;
  macro: number;
  news: number;
  paperStatistics: number;
}

export interface ScoreBreakdownRow {
  key: string;
  label: string;
  score: number;
  weight: number;
  contribution: number;
}

export interface ChecklistItem {
  label: string;
  passed: boolean;
  available: boolean;
}

export interface StrategyComparisonRow {
  strategy: string;
  score: number;
  probability: string;
  risk: string;
  status: StrategyStatus;
}

export interface RecommendedStrategyDetail {
  strategy: string;
  reason: string;
  idealEntry: string;
  profitTarget: string;
  invalidation: string;
  expectedHoldingDays: string;
  idealDte: string;
  preferredDelta: string;
  riskNotes: string;
}

export interface TradeDecisionResult {
  version: string;
  evaluatedAt: string;
  finalDecision: FinalDecision;
  tradeScore: number;
  confidence: QqqConfidence;
  riskLevel: DecisionRiskLevel;
  expectedRiskReward: string;
  probabilityOfSuccess: number | null;
  decisionSummary: string;
  reasonParagraph: string;
  breakdown: ScoreBreakdownRow[];
  checklist: ChecklistItem[];
  recommended: RecommendedStrategyDetail;
  strategyComparison: StrategyComparisonRow[];
  whyNot: string[];
  suggestedSpread: QqqSpreadCandidate | null;
  noCandidateReasons: string[];
  marketRegimeLabel: string;
}
