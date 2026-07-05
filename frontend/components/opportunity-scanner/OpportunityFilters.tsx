import type { OpportunityFiltersState, OpportunityScanRow } from "@/types/opportunityScanner";

type Props = {
  filters: OpportunityFiltersState;
  sectors: string[];
  onChange: (next: OpportunityFiltersState) => void;
};

export default function OpportunityFilters({ filters, sectors, onChange }: Props) {
  function patch(partial: Partial<OpportunityFiltersState>) {
    onChange({ ...filters, ...partial });
  }

  return (
    <section className="panel">
      <h2 className="panel-title">Filters</h2>
      <div className="os-filters">
        <label>
          Direction
          <select
            value={filters.direction}
            onChange={(e) => patch({ direction: e.target.value as OpportunityFiltersState["direction"] })}
          >
            <option value="All">All</option>
            <option value="Bullish">Bullish</option>
            <option value="Bearish">Bearish</option>
            <option value="Neutral">Neutral</option>
            <option value="Mixed">Mixed</option>
          </select>
        </label>
        <label>
          Min Opportunity
          <input
            type="number"
            min={0}
            max={100}
            value={filters.minOpportunity}
            onChange={(e) => patch({ minOpportunity: Number(e.target.value) })}
          />
        </label>
        <label>
          Max Risk
          <input
            type="number"
            min={0}
            max={100}
            value={filters.maxRisk}
            onChange={(e) => patch({ maxRisk: Number(e.target.value) })}
          />
        </label>
        <label>
          Sector
          <select value={filters.sector} onChange={(e) => patch({ sector: e.target.value })}>
            <option value="All">All</option>
            {sectors.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Max Priority
          <input
            type="number"
            min={1}
            max={99}
            value={filters.maxPriority}
            onChange={(e) => patch({ maxPriority: Number(e.target.value) })}
          />
        </label>
        <label>
          Has News
          <select
            value={filters.hasNews === null ? "any" : filters.hasNews ? "yes" : "no"}
            onChange={(e) => {
              const v = e.target.value;
              patch({ hasNews: v === "any" ? null : v === "yes" });
            }}
          >
            <option value="any">Any</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
        <label>
          Has Options
          <select
            value={filters.hasOptions === null ? "any" : filters.hasOptions ? "yes" : "no"}
            onChange={(e) => {
              const v = e.target.value;
              patch({ hasOptions: v === "any" ? null : v === "yes" });
            }}
          >
            <option value="any">Any</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
        <label style={{ flexDirection: "row", alignItems: "center", gap: "0.35rem" }}>
          <input
            type="checkbox"
            checked={filters.hideStale}
            onChange={(e) => patch({ hideStale: e.target.checked })}
          />
          Hide stale (no snapshot)
        </label>
      </div>
    </section>
  );
}

export function applyOpportunityFilters(
  rows: OpportunityScanRow[],
  filters: OpportunityFiltersState,
): OpportunityScanRow[] {
  return rows.filter((row) => {
    if (filters.direction !== "All" && row.direction_candidate !== filters.direction) return false;
    if (row.opportunity_score < filters.minOpportunity) return false;
    if (row.risk_score > filters.maxRisk) return false;
    if (filters.sector !== "All" && row.sector && row.sector !== filters.sector) return false;
    if ((row.priority ?? 99) > filters.maxPriority) return false;
    if (filters.hasNews === true && !row.has_news_data) return false;
    if (filters.hasNews === false && row.has_news_data) return false;
    if (filters.hasOptions === true && !row.has_options_data) return false;
    if (filters.hasOptions === false && row.has_options_data) return false;
    if (filters.hideStale && !row.has_analyzer_snapshot) return false;
    return true;
  });
}
