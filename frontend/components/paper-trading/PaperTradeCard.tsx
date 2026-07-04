type Props = {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "positive" | "negative";
};

export default function PaperTradeCard({ label, value, sub, tone = "neutral" }: Props) {
  return (
    <div className={`pt-card pt-card-${tone}`}>
      <div className="pt-card-label">{label}</div>
      <div className="pt-card-value">{value}</div>
      {sub && <div className="pt-card-sub">{sub}</div>}
    </div>
  );
}

function formatMoney(n: number): string {
  const sign = n >= 0 ? "" : "-";
  return `${sign}$${Math.abs(n).toFixed(2)}`;
}

export function summaryCards(summary: {
  open_count: number;
  closed_count: number;
  win_rate: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
  avg_return_pct: number;
}) {
  return [
    { label: "Open", value: String(summary.open_count), sub: "active paper positions" },
    { label: "Closed", value: String(summary.closed_count), sub: "completed trades" },
    { label: "Win rate", value: `${summary.win_rate.toFixed(1)}%`, sub: "closed trades" },
    {
      label: "Realized PnL",
      value: formatMoney(summary.total_realized_pnl),
      tone: summary.total_realized_pnl >= 0 ? "positive" : "negative",
    },
    {
      label: "Unrealized PnL",
      value: formatMoney(summary.total_unrealized_pnl),
      tone: summary.total_unrealized_pnl >= 0 ? "positive" : "negative",
    },
    { label: "Avg return", value: `${summary.avg_return_pct.toFixed(1)}%`, sub: "of max loss" },
  ] as const;
}
