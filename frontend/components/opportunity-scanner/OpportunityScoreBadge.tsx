import type { DirectionCandidate } from "@/types/opportunityScanner";

export function directionBadgeClass(direction: DirectionCandidate | string): string {
  if (direction === "Bullish") return "os-badge os-badge-bullish";
  if (direction === "Bearish") return "os-badge os-badge-bearish";
  if (direction === "Mixed") return "os-badge os-badge-mixed";
  return "os-badge os-badge-neutral";
}

export function readinessBadgeClass(readiness: string): string {
  if (readiness === "Ready") return "os-tech-badge os-tech-fresh";
  if (readiness === "Blocked") return "os-tech-badge os-tech-stale";
  return "os-tech-badge os-tech-not-evaluated";
}

export function scoreClass(score: number, invert = false): string {
  const s = invert ? 100 - score : score;
  if (s >= 70) return "os-score-high";
  if (s >= 45) return "os-score-mid";
  return "os-score-low";
}

export default function DirectionCandidateBadge({ direction }: { direction: DirectionCandidate | string }) {
  return <span className={directionBadgeClass(direction)}>{direction}</span>;
}

export function OpportunityScoreBadge({ score }: { score: number }) {
  return <span className={`num ${scoreClass(score)}`}>{score.toFixed(0)}</span>;
}
