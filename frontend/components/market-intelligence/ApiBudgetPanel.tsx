import type { IbkrNewsStatus, MicApiBudget } from "@/types/marketIntelligence";

type Props = {
  budget: MicApiBudget;
  ibkrStatus?: IbkrNewsStatus;
};

function pct(used: number, limit: number): number {
  if (limit <= 0) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

export default function ApiBudgetPanel({ budget, ibkrStatus }: Props) {
  const providers = [
    { name: "Finnhub", used: budget.finnhub.used, limit: budget.finnhub.limit },
    { name: "Alpha Vantage", used: budget.alpha_vantage.used, limit: budget.alpha_vantage.limit },
    { name: "SEC EDGAR", used: budget.sec.used, limit: budget.sec.limit },
  ];

  return (
    <div className="mic-budget-grid">
      {providers.map((p) => (
        <article key={p.name} className="mic-card">
          <div className="mic-card-label">{p.name}</div>
          <div className="mic-card-value">{p.used} / {p.limit}</div>
          <div className="mic-budget-bar">
            <div className="mic-budget-fill" style={{ width: `${pct(p.used, p.limit)}%` }} />
          </div>
        </article>
      ))}

      {/* IBKR News Provider Status */}
      <article className="mic-card">
        <div className="mic-card-label">IBKR News</div>
        <div className="mic-card-value">
          <span className={`mic-ibkr-status ${ibkrStatus?.available ? "available" : "unavailable"}`}>
            {ibkrStatus?.available ? "Available" : "Unavailable"}
          </span>
        </div>
        {ibkrStatus?.providers_detected && ibkrStatus.providers_detected.length > 0 && (
          <div className="mic-ibkr-providers">
            {ibkrStatus.providers_detected.join(", ")}
          </div>
        )}
        {ibkrStatus?.cache_status && (
          <div className="mic-ibkr-cache">
            Cache: {ibkrStatus.cache_status.valid_entries} active
          </div>
        )}
        {ibkrStatus?.last_fetch && (
          <div className="mic-ibkr-last-fetch">
            Last: {new Date(ibkrStatus.last_fetch).toLocaleTimeString()}
          </div>
        )}
        {ibkrStatus?.errors && ibkrStatus.errors.length > 0 && (
          <div className="mic-ibkr-errors">
            {ibkrStatus.errors.length} error(s)
          </div>
        )}
      </article>

      <article className="mic-card">
        <div className="mic-card-label">Planned calls</div>
        <div className="mic-card-value">{budget.planned_calls}</div>
      </article>
      <article className="mic-card">
        <div className="mic-card-label">Skipped calls</div>
        <div className="mic-card-value">{budget.skipped_calls}</div>
      </article>
      {budget.skip_reasons.length > 0 && (
        <ul className="qqq-muted-list mic-budget-reasons">
          {budget.skip_reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
