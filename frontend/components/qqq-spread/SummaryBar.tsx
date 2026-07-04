import type { QqqSpreadAnalysis } from "@/types/qqqSpreadAnalyzer";

function biasClass(bias: string): string {
  if (bias === "Bullish") return "bias-bull";
  if (bias === "Bearish") return "bias-bear";
  return "bias-neutral";
}

type Props = {
  data: QqqSpreadAnalysis;
  lastUpdatedLabel: string;
  onRefresh: () => void;
  onRun: () => void;
  busy: boolean;
  runBusy: boolean;
  dataIsStale?: boolean;
  dataAgeMin?: number | null;
};

export default function SummaryBar({
  data,
  lastUpdatedLabel,
  onRefresh,
  onRun,
  busy,
  runBusy,
  dataIsStale = false,
  dataAgeMin = null,
}: Props) {
  return (
    <div className="qqq-summary-bar">
      <div className="qqq-summary-main">
        <strong>
          {data.symbol} @ {data.underlying_price.toFixed(2)}
        </strong>
        <span className={biasClass(data.bias)}>Bias: {data.bias}</span>
        <span>Confidence: {data.confidence}</span>
        <span>Action: {data.suggested_action}</span>
        <span>
          Bull {data.bullish_score}/10 | Bear {data.bearish_score}/10
        </span>
        <span className="muted-text">Analysis snapshot: {lastUpdatedLabel}</span>
        {dataAgeMin !== null && dataAgeMin > 0 && (
          <span className={dataIsStale ? "qqq-stale-badge" : "muted-text"}>
            {dataIsStale ? `Stale (${dataAgeMin}m old) — Run analysis for fresh IB data` : `${dataAgeMin}m old`}
          </span>
        )}
      </div>
      <div className="qqq-actions">
        <button type="button" className="qqq-btn" onClick={onRefresh} disabled={busy || runBusy}>
          Reload snapshot
        </button>
        <button type="button" className="qqq-btn qqq-btn-primary" onClick={onRun} disabled={busy || runBusy}>
          {runBusy ? "Running analysis…" : "Run analysis"}
        </button>
      </div>
    </div>
  );
}
