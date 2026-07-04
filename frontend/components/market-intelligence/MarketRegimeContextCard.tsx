import Link from "next/link";

import type { MicRegimeContext } from "@/types/marketIntelligence";

type Props = { context: MicRegimeContext };

export default function MarketRegimeContextCard({ context }: Props) {
  if (!context.available) {
    return (
      <section className="mic-section mic-regime-context">
        <h2 className="mic-section-title">Market Regime Context</h2>
        <p className="muted-text">{context.message ?? "Market Regime data unavailable. Run analysis or open Market Regime tab."}</p>
        <Link href="/market-regime" className="qqq-btn">Open Market Regime</Link>
      </section>
    );
  }

  const cards = [
    { label: "Current Regime", value: context.current_regime ?? "—" },
    { label: "Regime Score", value: context.regime_score?.toFixed(1) ?? "—" },
    { label: "Risk Level", value: context.risk_level ?? "—" },
    { label: "Preferred Strategy", value: context.preferred_strategy ?? "—" },
    {
      label: "Next Major Catalyst",
      value: context.next_major_catalyst
        ? `${context.next_major_catalyst}${context.next_catalyst_countdown_days != null ? ` (${context.next_catalyst_countdown_days}d)` : ""}`
        : "—",
    },
    { label: "Volatility Regime", value: context.volatility_regime ?? "—" },
  ];

  return (
    <section className="mic-section mic-regime-context">
      <div className="mic-section-head">
        <h2 className="mic-section-title">Market Regime Context</h2>
        <Link href="/market-regime" className="mic-link">Full dashboard →</Link>
      </div>
      <p className="muted-text mic-regime-note">Read-only context from Market Regime service — not recalculated here.</p>
      <div className="mic-cards-grid mic-cards-6">
        {cards.map((c) => (
          <article key={c.label} className="mic-card mic-card-compact">
            <div className="mic-card-label">{c.label}</div>
            <div className="mic-card-value mic-card-value-sm">{c.value}</div>
          </article>
        ))}
      </div>
    </section>
  );
}
