import { computeMarketRegime, formatRegimeScoreRange } from "@/lib/marketRegime";
import type { QqqSpreadAnalysis } from "@/types/qqqSpreadAnalyzer";

type Props = { data: QqqSpreadAnalysis };

function CompactColumn({ title, rows }: { title: string; rows: { label: string; value: string }[] }) {
  return (
    <div className="qqq-regime-compact-col">
      <h3 className="qqq-regime-compact-title">{title}</h3>
      <table className="qqq-table qqq-regime-compact-table">
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th>{row.label}</th>
              <td className="num">{row.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function MarketRegimeSummary({ data }: Props) {
  const regime = computeMarketRegime(data);
  const tf = data.diagnostics.intraday_timeframe ?? "2H";

  return (
    <section className="panel qqq-regime-panel">
      <div className="panel-header">
        <h2 className="panel-title">Market Regime Summary</h2>
      </div>

      <div className="qqq-regime-cards">
        <article className="qqq-card">
          <div className="qqq-card-label">Market Regime</div>
          <div className={`qqq-regime-badge ${regime.badgeClass}`}>{regime.label}</div>
        </article>
        <article className="qqq-card">
          <div className="qqq-card-label">Regime Score</div>
          <div className="qqq-card-value">{formatRegimeScoreRange(regime.regimeScoreMin, regime.regimeScoreMax)}</div>
        </article>
        <article className="qqq-card">
          <div className="qqq-card-label">Confidence</div>
          <div className="qqq-card-value">{regime.confidence}</div>
        </article>
        <article className="qqq-card">
          <div className="qqq-card-label">Preferred Strategy</div>
          <div className="qqq-card-value qqq-regime-strategy">{regime.preferredStrategy}</div>
        </article>
        <article className="qqq-card">
          <div className="qqq-card-label">Risk Level</div>
          <div className="qqq-card-value">{regime.riskLevel}</div>
        </article>
      </div>

      <div className="qqq-regime-meta">
        <p>
          <strong>Avoid:</strong> {regime.avoid}
        </p>
        <span className={`qqq-regime-filter qqq-regime-filter-${regime.strategyFilter === "WAIT" ? "wait" : regime.strategyFilter === "Bull Call Spread" ? "bull" : "bear"}`}>
          Strategy filter: {regime.strategyFilter}
        </span>
      </div>

      <div className="qqq-regime-compact-grid">
        <CompactColumn title="Daily" rows={regime.compactDaily} />
        <CompactColumn title={`Intraday (${tf})`} rows={regime.compactIntraday} />
      </div>

      <div className="qqq-regime-scores">
        <div className="qqq-regime-score-chip">
          <span className="qqq-regime-score-label">Trend</span>
          <strong>{regime.scores.trend >= 0 ? "+" : ""}{regime.scores.trend}</strong>
        </div>
        <div className="qqq-regime-score-chip">
          <span className="qqq-regime-score-label">Momentum</span>
          <strong>{regime.scores.momentum >= 0 ? "+" : ""}{regime.scores.momentum}</strong>
        </div>
        <div className="qqq-regime-score-chip">
          <span className="qqq-regime-score-label">Volatility</span>
          <strong>{regime.scores.volatility}</strong>
        </div>
        <div className="qqq-regime-score-chip">
          <span className="qqq-regime-score-label">Intraday Timing</span>
          <strong>{regime.scores.intradayTiming}</strong>
        </div>
        <div className="qqq-regime-score-chip qqq-regime-score-final">
          <span className="qqq-regime-score-label">Final Regime</span>
          <strong>{regime.scores.final >= 0 ? "+" : ""}{regime.scores.final}</strong>
        </div>
      </div>

      <div className="qqq-regime-why">
        <h3 className="qqq-regime-why-title">Why this regime?</h3>
        <ul className="qqq-muted-list">
          {regime.whyBullets.map((bullet) => (
            <li key={bullet}>{bullet}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export { computeMarketRegime };
export type { MarketRegimeResult, StrategyFilter } from "@/lib/marketRegime";
