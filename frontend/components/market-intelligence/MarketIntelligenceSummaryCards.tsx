import type { MicSummary } from "@/types/marketIntelligence";

import NewsStatusBadge from "@/components/qqq-spread/news/NewsStatusBadge";

type Props = { summary: MicSummary };

export default function MarketIntelligenceSummaryCards({ summary }: Props) {
  const cards = [
    { label: "Overall News Sentiment", value: <NewsStatusBadge label={summary.overall_sentiment} /> },
    { label: "News Score", value: summary.news_score_0_to_100 },
    { label: "Critical Events", value: summary.critical_events_count },
    { label: "High Impact Events", value: summary.high_impact_events_count },
    { label: "Upcoming Earnings", value: summary.upcoming_earnings_count },
    { label: "API Health", value: <NewsStatusBadge label={summary.api_health} kind="provider" /> },
  ];

  return (
    <section className="mic-section">
      <h2 className="mic-section-title">Summary</h2>
      <div className="mic-cards-grid">
        {cards.map((c) => (
          <article key={c.label} className="mic-card">
            <div className="mic-card-label">{c.label}</div>
            <div className="mic-card-value">{c.value}</div>
          </article>
        ))}
      </div>
    </section>
  );
}
