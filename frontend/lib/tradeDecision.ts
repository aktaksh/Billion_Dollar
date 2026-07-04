import { computeMarketRegime, type MarketRegimeResult } from "@/lib/marketRegime";
import type { PaperTradeAnalytics } from "@/types/paperTrading";
import type {
  ChecklistItem,
  FinalDecision,
  RecommendedStrategyDetail,
  ScoreBreakdownRow,
  StrategyComparisonRow,
  StrategyStatus,
  TradeDecisionResult,
  TradeDecisionWeights,
} from "@/types/tradeDecision";
import type { QqqSpreadAnalysis, QqqSpreadCandidate } from "@/types/qqqSpreadAnalyzer";

export const DECISION_VERSION = "1.0.0";

export const DEFAULT_WEIGHTS: TradeDecisionWeights = {
  trend: 30,
  momentum: 20,
  marketRegime: 15,
  volatility: 10,
  liquidity: 10,
  riskReward: 5,
  macro: 5,
  news: 5,
  paperStatistics: 5,
};

const STRATEGIES: FinalDecision[] = [
  "Bull Call Spread",
  "Bear Put Spread",
  "Bull Put Spread",
  "Bear Call Spread",
  "Iron Condor",
  "WAIT",
];

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

function normalizeSigned(value: number, min: number, max: number): number {
  if (max <= min) return 50;
  return clamp(((value - min) / (max - min)) * 100, 0, 100);
}

function trendSubScore(data: QqqSpreadAnalysis): number {
  const checks = data.score.daily_checks;
  const keys = ["close_gt_ema20", "ema20_gt_ema50", "ema50_gt_sma200", "rsi_gt_50"];
  const available = keys.filter((k) => k in checks);
  if (available.length === 0) {
    const bull = data.bullish_score ?? 0;
    const bear = data.bearish_score ?? 0;
    const total = bull + bear || 1;
    return clamp((bull / total) * 100, 0, 100);
  }
  const passed = available.filter((k) => checks[k]).length;
  return (passed / available.length) * 100;
}

function momentumSubScore(data: QqqSpreadAnalysis): number {
  const daily = data.daily_indicators;
  const intraday = data.intraday_indicators;
  let score = 50;
  if (daily.macd_line != null && daily.macd_signal != null) {
    score += daily.macd_line > daily.macd_signal ? 25 : -25;
  }
  if (intraday.macd_line != null && intraday.macd_signal != null) {
    score += intraday.macd_line > intraday.macd_signal ? 15 : -15;
  }
  if (daily.macd_expanding) score += 5;
  if (daily.macd_weakening) score -= 5;
  return clamp(score, 0, 100);
}

function regimeSubScore(regime: MarketRegimeResult): number {
  return normalizeSigned(regime.scores.final, -60, 60);
}

function volatilitySubScore(regime: MarketRegimeResult, data: QqqSpreadAnalysis): number {
  const daily = data.daily_indicators;
  let score = 70;
  if (regime.riskLevel === "High") score = 30;
  else if (regime.riskLevel === "Medium") score = 55;
  if (daily.macd_expanding || daily.atr14 && daily.close && daily.atr14 / daily.close > 0.025) {
    score -= 15;
  }
  const bbU = daily.bb_upper;
  const bbL = daily.bb_lower;
  const bbM = daily.bb_mid;
  if (bbU && bbL && bbM && bbM > 0) {
    const w = (bbU - bbL) / bbM;
    if (w > 0.08) score -= 20;
    else if (w < 0.04) score += 10;
  }
  return clamp(score, 0, 100);
}

function liquiditySubScore(data: QqqSpreadAnalysis): number {
  const accepted = data.spread_candidates.filter((c) => c.status === "Accepted");
  if (accepted.length === 0) return 20;
  const best = Math.max(...accepted.map((c) => c.liquidity_score));
  return clamp(best, 0, 100);
}

function riskRewardSubScore(data: QqqSpreadAnalysis): number {
  const accepted = data.spread_candidates.filter((c) => c.status === "Accepted");
  if (accepted.length === 0) return 40;
  const best = accepted.reduce((a, b) => (a.reward_risk > b.reward_risk ? a : b));
  if (best.reward_risk >= 2) return 90;
  if (best.reward_risk >= 1.5) return 75;
  if (best.reward_risk >= 1) return 60;
  return 40;
}

function macroSubScore(): number | null {
  return null;
}

function newsSubScore(data: QqqSpreadAnalysis): number {
  const notes = data.risk_notes ?? [];
  const macroRisk = notes.some((n) => /fed|fomc|cpi|jobs|earnings/i.test(n));
  return macroRisk ? 35 : 70;
}

function paperStatsSubScore(analytics: PaperTradeAnalytics | null | undefined, strategy: string): number | null {
  if (!analytics || analytics.strategy_breakdown.length === 0) return null;
  const match = analytics.strategy_breakdown.find((s) =>
    strategy.toLowerCase().includes(s.strategy_type.toLowerCase().split(" ")[0]),
  );
  const row = match ?? analytics.strategy_breakdown[0];
  if (!row) return null;
  return clamp(row.win_rate * 100, 0, 100);
}

function buildBreakdown(
  data: QqqSpreadAnalysis,
  regime: MarketRegimeResult,
  analytics: PaperTradeAnalytics | null | undefined,
  weights: TradeDecisionWeights,
): ScoreBreakdownRow[] {
  const components: Array<{ key: string; label: string; score: number | null; weight: number }> = [
    { key: "trend", label: "Trend", score: trendSubScore(data), weight: weights.trend },
    { key: "momentum", label: "Momentum", score: momentumSubScore(data), weight: weights.momentum },
    { key: "marketRegime", label: "Market Regime", score: regimeSubScore(regime), weight: weights.marketRegime },
    { key: "volatility", label: "Volatility", score: volatilitySubScore(regime, data), weight: weights.volatility },
    { key: "liquidity", label: "Options Liquidity", score: liquiditySubScore(data), weight: weights.liquidity },
    { key: "riskReward", label: "Risk/Reward", score: riskRewardSubScore(data), weight: weights.riskReward },
    { key: "macro", label: "Macro Events", score: macroSubScore(), weight: weights.macro },
    { key: "news", label: "News", score: newsSubScore(data), weight: weights.news },
    {
      key: "paperStatistics",
      label: "Paper Trading Statistics",
      score: paperStatsSubScore(analytics, regime.preferredStrategy),
      weight: weights.paperStatistics,
    },
  ];

  return components.map((c) => {
    const score = c.score ?? 50;
    const contribution = (score * c.weight) / 100;
    return { key: c.key, label: c.label, score: Math.round(score), weight: c.weight, contribution: Math.round(contribution * 10) / 10 };
  });
}

function tradeScoreFromBreakdown(rows: ScoreBreakdownRow[]): number {
  return Math.min(100, Math.round(rows.reduce((sum, r) => sum + r.contribution, 0)));
}

function rankStrategies(
  data: QqqSpreadAnalysis,
  regime: MarketRegimeResult,
  tradeScore: number,
): StrategyComparisonRow[] {
  const bullTrend = regime.trendBullCount >= 3;
  const bearTrend = regime.trendBearCount >= 3;
  const accepted = data.spread_candidates.filter((c) => c.status === "Accepted");

  const scores: Record<string, number> = {
    "Bull Call Spread": bullTrend ? 75 : 35,
    "Bear Put Spread": bearTrend ? 75 : 30,
    "Bull Put Spread": bullTrend ? 55 : 40,
    "Bear Call Spread": bearTrend ? 45 : 20,
    "Iron Condor": Math.abs(regime.scores.final) < 25 ? 60 : 40,
    WAIT: tradeScore < 55 ? 70 : 45,
  };

  for (const c of accepted) {
    const s = c.strategy;
    if (s.toLowerCase().includes("bull") && s.toLowerCase().includes("call")) {
      scores["Bull Call Spread"] = Math.max(scores["Bull Call Spread"], 80 + c.liquidity_score / 10);
    }
    if (s.toLowerCase().includes("bear") && s.toLowerCase().includes("put")) {
      scores["Bear Put Spread"] = Math.max(scores["Bear Put Spread"], 80 + c.liquidity_score / 10);
    }
  }

  if (regime.strategyFilter === "Bull Call Spread") scores["Bull Call Spread"] += 10;
  if (regime.strategyFilter === "Bear Put Spread") scores["Bear Put Spread"] += 10;
  if (regime.strategyFilter === "WAIT") scores.WAIT += 8;

  const sorted = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  const top = sorted[0]?.[1] ?? 0;

  return sorted.map(([strategy, score]) => {
    let status: StrategyStatus = "Neutral";
    if (score === top && strategy !== "WAIT") status = "Preferred";
    else if (score >= top - 8 && strategy !== "WAIT") status = "Alternative";
    else if (strategy === "WAIT" && tradeScore < 60) status = "Acceptable";
    else if (score < 35) status = "Avoid";

    const candidate = accepted.find((c) => c.strategy.toLowerCase().includes(strategy.split(" ")[0].toLowerCase()));
    const prob = candidate?.probability_of_profit;
    const probability = prob != null ? (prob > 1 ? `${Math.round(prob)}%` : `${Math.round(prob * 100)}%`) : "—";
    const risk = score >= 70 ? "Medium" : score >= 45 ? "Medium" : "High";

    return { strategy, score: Math.round(score), probability, risk, status };
  });
}

function pickFinalDecision(comparison: StrategyComparisonRow[], tradeScore: number): FinalDecision {
  const top = comparison[0];
  if (!top) return "WAIT";
  if (tradeScore < 50) return "WAIT";
  if (top.strategy === "WAIT" && tradeScore < 65) return "WAIT";
  const name = top.strategy as FinalDecision;
  return STRATEGIES.includes(name) ? name : "WAIT";
}

function buildChecklist(data: QqqSpreadAnalysis, regime: MarketRegimeResult): ChecklistItem[] {
  const daily = data.daily_indicators;
  const intraday = data.intraday_indicators;
  const dc = data.score.daily_checks;
  const ic = data.score.intraday_checks;
  const nearestRes = data.resistance_levels[0]?.price;
  const nearestSup = data.support_levels[0]?.price;
  const close = daily.close;

  const items: ChecklistItem[] = [
    { label: "Above EMA20", passed: !!dc.close_gt_ema20, available: "close_gt_ema20" in dc },
    { label: "EMA20 above EMA50", passed: !!dc.ema20_gt_ema50, available: "ema20_gt_ema50" in dc },
    { label: "EMA50 above SMA200", passed: !!dc.ema50_gt_sma200, available: "ema50_gt_sma200" in dc },
    { label: "RSI above 50", passed: !!dc.rsi_gt_50, available: "rsi_gt_50" in dc },
    { label: "Daily MACD bullish", passed: !!dc.macd_gt_signal, available: "macd_gt_signal" in dc },
    {
      label: "Intraday MACD improving",
      passed: intraday.macd_line != null && intraday.macd_signal != null && intraday.macd_line > intraday.macd_signal,
      available: intraday.macd_line != null,
    },
    {
      label: "Support holding",
      passed: nearestSup ? close >= nearestSup : !!dc.above_week_high_or_support,
      available: nearestSup != null || "above_week_high_or_support" in dc,
    },
    {
      label: "Resistance breakout",
      passed: nearestRes ? close > nearestRes : false,
      available: nearestRes != null,
    },
    {
      label: "Option liquidity acceptable",
      passed: data.spread_candidates.some((c) => c.status === "Accepted" && c.liquidity_score >= 50),
      available: data.spread_candidates.length > 0,
    },
    {
      label: "Bid/Ask spread acceptable",
      passed: data.spread_candidates.some((c) => c.status === "Accepted" && c.bid_ask_quality >= 0.5),
      available: data.spread_candidates.length > 0,
    },
    {
      label: "No major macro event today",
      passed: !(data.risk_notes ?? []).some((n) => /today|tomorrow|fed|fomc/i.test(n)),
      available: true,
    },
  ];

  if (Object.keys(ic).length > 0) {
    const intraPass = Object.values(ic).filter(Boolean).length;
    items.push({
      label: "Intraday timing aligned",
      passed: intraPass >= 2,
      available: true,
    });
  }

  void regime;
  return items;
}

function buildWhyNot(
  data: QqqSpreadAnalysis,
  regime: MarketRegimeResult,
  checklist: ChecklistItem[],
): string[] {
  const reasons: string[] = [];
  const daily = data.daily_indicators;

  if (daily.macd_line != null && daily.macd_signal != null && daily.macd_line < daily.macd_signal) {
    reasons.push("Daily MACD below signal.");
  }
  if (data.resistance_levels[0] && daily.close < data.resistance_levels[0].price) {
    reasons.push("Resistance overhead.");
  }
  if (daily.macd_expanding || (daily.atr14 && daily.close && daily.atr14 / daily.close > 0.025)) {
    reasons.push("ATR expanding.");
  }
  if (!data.spread_candidates.some((c) => c.status === "Accepted")) {
    reasons.push("Spread liquidity below threshold.");
  }
  if ((data.risk_notes ?? []).some((n) => /fed|fomc/i.test(n))) {
    reasons.push("Fed meeting or macro event noted in risk flags.");
  }
  for (const item of checklist.filter((c) => c.available && !c.passed)) {
    if (!reasons.some((r) => r.toLowerCase().includes(item.label.toLowerCase()))) {
      reasons.push(`${item.label} not confirmed.`);
    }
  }
  if (regime.strategyFilter === "WAIT") {
    reasons.push("Market regime strategy filter is WAIT.");
  }
  return reasons.slice(0, 8);
}

function bestCandidate(data: QqqSpreadAnalysis, decision: FinalDecision): QqqSpreadCandidate | null {
  const accepted = data.spread_candidates.filter((c) => c.status === "Accepted");
  if (accepted.length === 0) return null;
  const keyword = decision === "WAIT" ? "" : decision.split(" ")[0].toLowerCase();
  const matching = keyword
    ? accepted.filter((c) => c.strategy.toLowerCase().includes(keyword))
    : accepted;
  const pool = matching.length > 0 ? matching : accepted;
  return pool.reduce((a, b) => (a.liquidity_score > b.liquidity_score ? a : b));
}

/** Top spread candidate shown alongside key levels (best liquidity, strategy-aware). */
export function pickSuggestedSpread(
  data: QqqSpreadAnalysis,
  decision: FinalDecision = "WAIT",
): QqqSpreadCandidate | null {
  const accepted = data.spread_candidates.filter((c) => c.status === "Accepted");
  if (accepted.length > 0) {
    return bestCandidate(data, decision);
  }
  return data.spread_candidates[0] ?? null;
}

function noCandidateReasons(data: QqqSpreadAnalysis): string[] {
  const reasons: string[] = [];
  const hints = data.diagnostics.qualification_failures ?? [];
  for (const f of hints) {
    reasons.push(`${f.failed_count} contracts failed for ${f.expiry}: ${f.reason_hint}`);
  }
  if ((data.diagnostics.liquid_quotes ?? 0) === 0 && (data.diagnostics.raw_quotes ?? 0) > 0) {
    reasons.push("Bid/Ask spread may have exceeded threshold");
  }
  if (data.score.invalid_conditions.length) {
    reasons.push(...data.score.invalid_conditions);
  }
  if (reasons.length === 0 && data.spread_candidates.length === 0) {
    reasons.push("No spread candidates returned by analyzer");
  }
  if (reasons.length === 0) {
    reasons.push("Delta outside target range or open interest below minimum");
  }
  return reasons;
}

function buildRecommended(
  data: QqqSpreadAnalysis,
  regime: MarketRegimeResult,
  decision: FinalDecision,
  candidate: QqqSpreadCandidate | null,
): RecommendedStrategyDetail {
  const res = data.resistance_levels[0]?.price;
  const sup = data.support_levels[0]?.price;
  const close = data.underlying_price;

  const strategy = decision === "WAIT" ? regime.preferredStrategy : decision;
  const entryTrigger = res && decision.includes("Bull")
    ? `Only after daily close above ${res.toFixed(0)}`
    : sup && decision.includes("Bear")
      ? `On rejection below ${sup.toFixed(0)} or break confirmation`
      : `Confirm bias at ${close.toFixed(2)}`;

  return {
    strategy,
    reason: regime.whyBullets.slice(0, 2).join(" ") || data.reason_summary,
    idealEntry: candidate ? `Debit ${candidate.net_debit.toFixed(2)} at current levels` : entryTrigger,
    profitTarget: res ? `${res.toFixed(0)}` : candidate ? `${(candidate.breakeven + candidate.max_profit / 100).toFixed(0)}` : "—",
    invalidation: sup ? `Below ${sup.toFixed(0)}` : candidate ? `Max loss ${candidate.max_loss.toFixed(0)}` : "—",
    expectedHoldingDays: candidate ? `${Math.min(candidate.dte, 21)}–${candidate.dte}` : "14–30",
    idealDte: candidate ? `${candidate.dte}` : "21–45",
    preferredDelta: candidate
      ? `Buy Δ ${Math.abs(candidate.combined_delta + 0.15).toFixed(2)} / Sell Δ ${Math.abs(candidate.combined_delta).toFixed(2)}`
      : "Buy 0.40 / Sell 0.25",
    riskNotes: data.risk_notes.slice(0, 2).join(" ") || "Research only — no live execution.",
  };
}

function adjustConfidence(
  base: QqqSpreadAnalysis["confidence"],
  breakdown: ScoreBreakdownRow[],
  missingData: boolean,
): QqqSpreadAnalysis["confidence"] {
  const order = ["Low", "Medium", "High"] as const;
  let idx = order.indexOf(base);
  const unavailable = breakdown.filter((r) => r.key === "macro" || r.key === "paperStatistics");
  if (missingData) idx = Math.max(0, idx - 1);
  if (unavailable.some((r) => r.score === 50 && (r.key === "macro" || r.key === "paperStatistics"))) {
    idx = Math.max(0, idx - 1);
  }
  return order[idx];
}

function riskFromScore(tradeScore: number, regime: MarketRegimeResult): TradeDecisionResult["riskLevel"] {
  if (regime.riskLevel === "High" && tradeScore < 50) return "Extreme";
  if (regime.riskLevel === "High") return "High";
  if (tradeScore >= 70) return "Low";
  if (tradeScore >= 45) return "Medium";
  return "High";
}

function buildSummary(decision: FinalDecision, reasons: string[], regime: MarketRegimeResult): { summary: string; paragraph: string } {
  const lines = [
    regime.whyBullets[0],
    reasons[0],
    reasons[1],
    decision === "WAIT"
      ? "No high-quality spread currently satisfies liquidity and technical filters."
      : "Spread candidates and technical structure support this approach.",
    decision === "WAIT"
      ? "Wait for confirmation above resistance or breakdown below support."
      : "Review suggested spread and risk notes before paper trading.",
  ].filter(Boolean);

  return {
    summary: `Decision: ${decision}`,
    paragraph: lines.join("\n\n"),
  };
}

export function computeTradeDecision(
  data: QqqSpreadAnalysis,
  options?: {
    regime?: MarketRegimeResult;
    analytics?: PaperTradeAnalytics | null;
    weights?: TradeDecisionWeights;
  },
): TradeDecisionResult {
  const regime = options?.regime ?? computeMarketRegime(data);
  const weights = options?.weights ?? DEFAULT_WEIGHTS;
  const breakdown = buildBreakdown(data, regime, options?.analytics, weights);
  let tradeScore = tradeScoreFromBreakdown(breakdown);
  const comparison = rankStrategies(data, regime, tradeScore);

  const accepted = data.spread_candidates.filter((c) => c.status === "Accepted");
  const expirySearch = (data as unknown as Record<string, unknown>).expiry_search as Record<string, unknown> | undefined;
  const forceWait = accepted.length === 0 || (expirySearch?.force_wait === true);

  if (forceWait) {
    tradeScore = Math.min(tradeScore, 55);
  }

  let finalDecision: FinalDecision;
  if (forceWait) {
    finalDecision = "WAIT";
  } else {
    finalDecision = pickFinalDecision(comparison, tradeScore);
  }

  const checklist = buildChecklist(data, regime);
  const whyNot = buildWhyNot(data, regime, checklist);

  if (forceWait && expirySearch?.wait_reason) {
    whyNot.unshift(String(expirySearch.wait_reason));
  } else if (forceWait && accepted.length === 0) {
    whyNot.unshift("No valid spread candidates across all scanned expiries.");
  }

  const suggestedSpread = bestCandidate(data, finalDecision);
  const noCandidates = suggestedSpread ? [] : noCandidateReasons(data);
  const recommended = buildRecommended(data, regime, finalDecision, suggestedSpread);
  const { summary, paragraph } = buildSummary(finalDecision, whyNot, regime);

  const best = suggestedSpread;
  const rawProb = best?.probability_of_profit;
  const probability =
    rawProb != null ? (rawProb > 1 ? Math.round(rawProb) : Math.round(rawProb * 100)) : null;
  const rr = best ? `1 : ${best.reward_risk.toFixed(1)}` : "—";

  const macroMissing = macroSubScore() === null;
  const paperMissing = !options?.analytics?.strategy_breakdown?.length;

  return {
    version: DECISION_VERSION,
    evaluatedAt: new Date().toISOString(),
    finalDecision,
    tradeScore,
    confidence: adjustConfidence(data.confidence, breakdown, macroMissing || paperMissing),
    riskLevel: riskFromScore(tradeScore, regime),
    expectedRiskReward: rr,
    probabilityOfSuccess: probability != null ? Math.round(probability * 100) : null,
    decisionSummary: summary,
    reasonParagraph: paragraph,
    breakdown,
    checklist,
    recommended,
    strategyComparison: comparison,
    whyNot,
    suggestedSpread,
    noCandidateReasons: noCandidates,
    marketRegimeLabel: regime.label,
  };
}
