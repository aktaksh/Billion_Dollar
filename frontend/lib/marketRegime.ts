import type { QqqConfidence, QqqIndicatorSnapshot, QqqSpreadAnalysis } from "@/types/qqqSpreadAnalyzer";

export type RegimeLabel =
  | "Strong Bull"
  | "Bull Pullback"
  | "Bull Trend with Momentum Warning"
  | "Sideways"
  | "Bear Pullback"
  | "Bear Trend";

export type StrategyFilter = "Bull Call Spread" | "Bear Put Spread" | "WAIT";

export type RiskLevel = "Low" | "Medium" | "High";

export interface CompactRow {
  label: string;
  value: string;
}

export interface MarketRegimeScores {
  trend: number;
  momentum: number;
  volatility: number;
  intradayTiming: number;
  final: number;
}

export interface MarketRegimeResult {
  label: RegimeLabel;
  regimeScoreMin: number;
  regimeScoreMax: number;
  confidence: QqqConfidence;
  preferredStrategy: string;
  avoid: string;
  riskLevel: RiskLevel;
  strategyFilter: StrategyFilter;
  scores: MarketRegimeScores;
  whyBullets: string[];
  badgeClass: string;
  compactDaily: CompactRow[];
  compactIntraday: CompactRow[];
  trendBullCount: number;
  trendBearCount: number;
}

function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(digits);
}

function macdBullish(ind: QqqIndicatorSnapshot): boolean {
  return ind.macd_line != null && ind.macd_signal != null && ind.macd_line > ind.macd_signal;
}

function countTrendChecks(daily: QqqIndicatorSnapshot): { bull: number; bear: number } {
  let bull = 0;
  let bear = 0;
  if (daily.ema20 != null && daily.close > daily.ema20) bull += 1;
  else if (daily.ema20 != null && daily.close < daily.ema20) bear += 1;
  if (daily.ema20 != null && daily.ema50 != null && daily.ema20 > daily.ema50) bull += 1;
  else if (daily.ema20 != null && daily.ema50 != null && daily.ema20 < daily.ema50) bear += 1;
  if (daily.ema50 != null && daily.sma200 != null && daily.ema50 > daily.sma200) bull += 1;
  else if (daily.ema50 != null && daily.sma200 != null && daily.ema50 < daily.sma200) bear += 1;
  if (daily.rsi14 != null && daily.rsi14 > 50) bull += 1;
  else if (daily.rsi14 != null && daily.rsi14 < 50) bear += 1;
  return { bull, bear };
}

function computeTrendScore(bull: number, bear: number): number {
  if (bull >= bear) return bull * 10;
  return -bear * 10;
}

function computeMomentumScore(daily: QqqIndicatorSnapshot, intraday: QqqIndicatorSnapshot): number {
  let score = 0;
  if (macdBullish(daily)) score += 15;
  else if (daily.macd_line != null && daily.macd_signal != null) score -= 15;
  if (daily.macd_expanding) score += 5;
  if (daily.macd_weakening) score -= 5;
  if (macdBullish(intraday)) score += 5;
  else if (intraday.macd_line != null && intraday.macd_signal != null) score -= 5;
  return Math.max(-25, Math.min(25, score));
}

function computeVolatilityScore(daily: QqqIndicatorSnapshot): { score: number; riskLevel: RiskLevel } {
  const { bb_upper, bb_lower, bb_mid, atr14, close } = daily;
  if (bb_upper == null || bb_lower == null || !bb_mid || bb_mid <= 0) {
    return { score: 8, riskLevel: "Medium" };
  }
  const bbWidth = (bb_upper - bb_lower) / bb_mid;
  let riskLevel: RiskLevel = "Medium";
  let score = 8;
  if (bbWidth < 0.04) {
    riskLevel = "Low";
    score = 5;
  } else if (bbWidth > 0.08) {
    riskLevel = "High";
    score = 14;
  }
  if (atr14 != null && close > 0 && atr14 / close > 0.025) {
    riskLevel = "High";
    score = Math.max(score, 12);
  }
  return { score, riskLevel };
}

function computeIntradayTimingScore(data: QqqSpreadAnalysis, intraday: QqqIndicatorSnapshot): number {
  let score = (data.score.intraday_timing_bull ?? 0) * 5;
  if (intraday.ema21 != null && intraday.close < intraday.ema21) {
    score = Math.max(0, score - 8);
  }
  return Math.max(0, Math.min(20, score));
}

function isTrendBullish(bull: number): boolean {
  return bull >= 3;
}

function isTrendBearish(bear: number): boolean {
  return bear >= 3;
}

function supportBreakConfirmed(data: QqqSpreadAnalysis, daily: QqqIndicatorSnapshot): boolean {
  if (data.score.daily_checks.reject_res_or_break_support) return true;
  const supports = data.support_levels.map((s) => s.price).filter((p) => p > 0);
  if (supports.length === 0) return false;
  const nearest = supports.reduce((best, p) => (Math.abs(p - daily.close) < Math.abs(best - daily.close) ? p : best));
  return daily.close < nearest;
}

function computeStrategyFilter(
  data: QqqSpreadAnalysis,
  daily: QqqIndicatorSnapshot,
  intraday: QqqIndicatorSnapshot,
  trendBull: number,
): StrategyFilter {
  const dailyMacdBull = macdBullish(daily);
  const intraMacdBull = macdBullish(intraday);

  const bullAllowed =
    trendBull >= 3 &&
    (daily.rsi14 ?? 0) > 50 &&
    intraday.ema21 != null &&
    intraday.close > intraday.ema21 &&
    intraMacdBull;

  const bearAllowed =
    daily.ema20 != null &&
    daily.close < daily.ema20 &&
    (daily.rsi14 ?? 100) < 50 &&
    !dailyMacdBull &&
    supportBreakConfirmed(data, daily);

  if (bullAllowed) return "Bull Call Spread";
  if (bearAllowed) return "Bear Put Spread";
  return "WAIT";
}

function classifyRegime(
  trendBull: number,
  trendBear: number,
  daily: QqqIndicatorSnapshot,
  intraday: QqqIndicatorSnapshot,
  finalScore: number,
  itBull: number,
): RegimeLabel {
  const dailyMacdBull = macdBullish(daily);
  const intraMacdBull = macdBullish(intraday);

  if (isTrendBullish(trendBull)) {
    if (dailyMacdBull && finalScore >= 50) return "Strong Bull";
    if (!dailyMacdBull) {
      return intraMacdBull ? "Bull Trend with Momentum Warning" : "Bull Pullback";
    }
    if (finalScore >= 35) return "Strong Bull";
    return "Bull Pullback";
  }
  if (isTrendBearish(trendBear)) {
    if (!dailyMacdBull && finalScore <= -40) return "Bear Trend";
    if (itBull >= 2) return "Bear Pullback";
    return "Bear Trend";
  }
  return "Sideways";
}

function badgeClassForLabel(label: RegimeLabel): string {
  switch (label) {
    case "Strong Bull":
      return "regime-strong-bull";
    case "Bull Pullback":
    case "Bull Trend with Momentum Warning":
      return "regime-bull-pullback";
    case "Sideways":
      return "regime-sideways";
    case "Bear Pullback":
      return "regime-bear-pullback";
    case "Bear Trend":
      return "regime-bear-trend";
    default:
      return "regime-sideways";
  }
}

function downgradeConfidence(conf: QqqConfidence): QqqConfidence {
  if (conf === "High") return "Medium";
  if (conf === "Medium") return "Low";
  return "Low";
}

function capConfidence(conf: QqqConfidence, max: QqqConfidence): QqqConfidence {
  const order: QqqConfidence[] = ["Low", "Medium", "High"];
  return order.indexOf(conf) > order.indexOf(max) ? max : conf;
}

function adjustConfidence(
  base: QqqConfidence,
  daily: QqqIndicatorSnapshot,
  intraday: QqqIndicatorSnapshot,
  trendBull: number,
  trendBear: number,
  itBull: number,
): QqqConfidence {
  let conf = base;
  const dailyMacdBull = macdBullish(daily);
  const intraMacdBull = macdBullish(intraday);

  if (isTrendBullish(trendBull) && itBull < 2) conf = capConfidence(conf, "Medium");
  if (isTrendBearish(trendBear) && itBull >= 2) conf = capConfidence(conf, "Medium");
  if (intraday.ema21 != null && intraday.close < intraday.ema21) conf = downgradeConfidence(conf);
  if (dailyMacdBull !== intraMacdBull) conf = capConfidence(conf, "Medium");
  if (dailyMacdBull !== intraMacdBull && itBull < 2) conf = capConfidence(conf, "Low");

  return conf;
}

function preferredStrategyCopy(
  filter: StrategyFilter,
  label: RegimeLabel,
): string {
  if (filter === "Bull Call Spread") return "Bull Call Spread";
  if (filter === "Bear Put Spread") return "Bear Put Spread";
  if (label === "Bull Pullback" || label === "Bull Trend with Momentum Warning") {
    return "Wait for Bull Call confirmation";
  }
  if (label === "Bear Pullback" || label === "Bear Trend") {
    return "Wait for Bear Put confirmation";
  }
  return "Wait — no clean setup";
}

function avoidCopy(label: RegimeLabel, filter: StrategyFilter): string {
  if (filter === "Bull Call Spread") return "Chasing extended moves without pullback";
  if (filter === "Bear Put Spread") return "Bull Call until support reclaimed";
  if (label === "Bull Pullback" || label === "Bull Trend with Momentum Warning") {
    return "Bear Put unless support breaks";
  }
  if (label === "Bear Pullback" || label === "Bear Trend") {
    return "Bull Call until trend reclaims EMA20";
  }
  return "Both directions until regime clarifies";
}

function buildWhyBullets(
  data: QqqSpreadAnalysis,
  daily: QqqIndicatorSnapshot,
  intraday: QqqIndicatorSnapshot,
  trendBull: number,
  filter: StrategyFilter,
): string[] {
  const bullets: string[] = [];
  const tf = data.diagnostics.intraday_timeframe ?? "2H";

  if (daily.ema20 != null && daily.close > daily.ema20) bullets.push("Price above Daily EMA20");
  else if (daily.ema20 != null && daily.close < daily.ema20) bullets.push("Price below Daily EMA20");

  if (daily.ema20 != null && daily.ema50 != null && daily.sma200 != null) {
    if (daily.ema20 > daily.ema50 && daily.ema50 > daily.sma200) {
      bullets.push("EMA structure is bullish");
    } else if (daily.ema20 < daily.ema50 && daily.ema50 < daily.sma200) {
      bullets.push("EMA structure is bearish");
    } else {
      bullets.push("EMA structure is mixed");
    }
  }

  if (daily.rsi14 != null) {
    bullets.push(daily.rsi14 > 50 ? "RSI above 50" : "RSI below 50");
  }

  if (daily.macd_line != null && daily.macd_signal != null) {
    if (daily.macd_line < daily.macd_signal) {
      bullets.push("Daily MACD is below signal, showing momentum warning");
    } else {
      bullets.push("Daily MACD is above signal, momentum supportive");
    }
  }

  if (macdBullish(intraday) && (intraday.rsi14 ?? 0) > 50) {
    bullets.push(`${tf} MACD is bullish, showing possible short-term recovery`);
  } else if (!macdBullish(intraday) && intraday.macd_line != null) {
    bullets.push(`${tf} MACD is bearish, intraday timing weak`);
  }

  if (intraday.ema21 != null && intraday.close < intraday.ema21) {
    bullets.push(`Price below ${tf} EMA21 — entry confidence reduced`);
  }

  if (trendBull >= 3 && (data.score.intraday_timing_bull ?? 0) < 2) {
    bullets.push("Daily and intraday timing disagree");
  }

  if (filter === "WAIT") {
    bullets.push("Entry still requires confirmation");
  }

  return bullets;
}

function buildCompactRows(ind: QqqIndicatorSnapshot, mode: "daily" | "intraday"): CompactRow[] {
  if (mode === "daily") {
    return [
      { label: "Close", value: fmt(ind.close) },
      { label: "EMA20", value: fmt(ind.ema20) },
      { label: "EMA50", value: fmt(ind.ema50) },
      { label: "SMA200", value: fmt(ind.sma200) },
      { label: "RSI14", value: fmt(ind.rsi14) },
      { label: "MACD", value: `${fmt(ind.macd_line, 3)} / ${fmt(ind.macd_signal, 3)}` },
    ];
  }
  return [
    { label: "Close", value: fmt(ind.close) },
    { label: "EMA9", value: fmt(ind.ema9) },
    { label: "EMA21", value: fmt(ind.ema21) },
    { label: "RSI14", value: fmt(ind.rsi14) },
    { label: "MACD", value: `${fmt(ind.macd_line, 3)} / ${fmt(ind.macd_signal, 3)}` },
  ];
}

export function computeMarketRegime(data: QqqSpreadAnalysis): MarketRegimeResult {
  const daily = data.daily_indicators;
  const intraday = data.intraday_indicators;
  const { bull: trendBull, bear: trendBear } = countTrendChecks(daily);

  const trend = computeTrendScore(trendBull, trendBear);
  const momentum = computeMomentumScore(daily, intraday);
  const { score: volatility, riskLevel: volRisk } = computeVolatilityScore(daily);
  const intradayTiming = computeIntradayTimingScore(data, intraday);
  const final = trend + momentum + intradayTiming;

  const regimeScoreMin = Math.max(-100, Math.min(100, final - 5));
  const regimeScoreMax = Math.max(-100, Math.min(100, final + 5));

  const label = classifyRegime(trendBull, trendBear, daily, intraday, final, data.score.intraday_timing_bull ?? 0);
  const strategyFilter = computeStrategyFilter(data, daily, intraday, trendBull);
  const confidence = adjustConfidence(
    data.confidence,
    daily,
    intraday,
    trendBull,
    trendBear,
    data.score.intraday_timing_bull ?? 0,
  );

  let riskLevel = volRisk;
  if (confidence === "Low") riskLevel = "High";
  else if (confidence === "High" && volRisk === "Low") riskLevel = "Low";

  return {
    label,
    regimeScoreMin,
    regimeScoreMax,
    confidence,
    preferredStrategy: preferredStrategyCopy(strategyFilter, label),
    avoid: avoidCopy(label, strategyFilter),
    riskLevel,
    strategyFilter,
    scores: { trend, momentum, volatility, intradayTiming, final },
    whyBullets: buildWhyBullets(data, daily, intraday, trendBull, strategyFilter),
    badgeClass: badgeClassForLabel(label),
    compactDaily: buildCompactRows(daily, "daily"),
    compactIntraday: buildCompactRows(intraday, "intraday"),
    trendBullCount: trendBull,
    trendBearCount: trendBear,
  };
}

export function formatRegimeScoreRange(min: number, max: number): string {
  const sign = min >= 0 ? "+" : "";
  if (min === max) return `${sign}${min}`;
  return `${sign}${min} to ${max >= 0 ? "+" : ""}${max}`;
}
