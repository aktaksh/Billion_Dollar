import type { QqqSpreadAnalysis } from "@/types/qqqSpreadAnalyzer";

type Props = { data: QqqSpreadAnalysis };

function bannerClass(data: QqqSpreadAnalysis): string {
  const hasSpreads = data.spread_candidates.length > 0;
  const mixed = data.score.invalid_conditions.length > 0;
  if (mixed) return "qqq-banner qqq-banner-mixed";
  if (!hasSpreads) return "qqq-banner qqq-banner-wait";
  if (data.bias === "Bullish") return "qqq-banner qqq-banner-bull";
  if (data.bias === "Bearish") return "qqq-banner qqq-banner-bear";
  return "qqq-banner qqq-banner-wait";
}

function bannerText(data: QqqSpreadAnalysis): string {
  const hasSpreads = data.spread_candidates.length > 0;
  const mixed = data.score.invalid_conditions.length > 0;
  if (mixed) return "No trade — mixed signal.";
  if (!hasSpreads) return "Wait — no clean spread candidate.";
  if (data.bias === "Bullish") return "Bull call spread candidates available.";
  if (data.bias === "Bearish") return "Bear put spread candidates available.";
  return "Wait — no clean spread candidate.";
}

function biasClass(bias: string): string {
  if (bias === "Bullish") return "bias-bull";
  if (bias === "Bearish") return "bias-bear";
  return "bias-neutral";
}

export default function MarketBiasPanel({ data }: Props) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Market Bias</h2>
      </div>
      <div className={bannerClass(data)}>{bannerText(data)}</div>
      <div className="qqq-grid-3" style={{ marginTop: "0.75rem" }}>
        <article className="qqq-card">
          <div className="qqq-card-label">Bias</div>
          <div className={`qqq-card-value ${biasClass(data.bias)}`}>{data.bias}</div>
        </article>
        <article className="qqq-card">
          <div className="qqq-card-label">Confidence</div>
          <div className="qqq-card-value">{data.confidence}</div>
        </article>
        <article className="qqq-card">
          <div className="qqq-card-label">Suggested action</div>
          <div className="qqq-card-value">{data.suggested_action}</div>
        </article>
      </div>
      <p style={{ marginTop: "0.75rem", fontSize: "0.9rem" }}>{data.reason_summary}</p>
    </section>
  );
}
