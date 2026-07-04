import Link from "next/link";

import { formatExpiryDate } from "@/lib/expiryFormat";
import type { PaperTrade } from "@/types/paperTrading";

type Props = { trades: PaperTrade[] };

function pnlClass(n: number): string {
  if (n > 0) return "pt-pnl-pos";
  if (n < 0) return "pt-pnl-neg";
  return "";
}

function closedPnl(t: PaperTrade): number {
  return t.realized_pnl ?? t.unrealized_pnl ?? 0;
}

export default function ClosedTradesTable({ trades }: Props) {
  if (trades.length === 0) {
    return <p className="qqq-empty">No closed or expired trades yet.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="qqq-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Strategy</th>
            <th>Expiry</th>
            <th>Status</th>
            <th className="num">Realized PnL</th>
            <th className="num">Return</th>
            <th>Exit</th>
            <th>Reason</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const pnl = closedPnl(t);
            return (
              <tr key={t.id}>
                <td>{t.symbol}</td>
                <td>{t.strategy_type}</td>
                <td>{formatExpiryDate(t.expiry_date)}</td>
                <td>{t.status}</td>
                <td className={`num ${pnlClass(pnl)}`}>${pnl.toFixed(2)}</td>
                <td className="num">{(t.percent_return ?? 0).toFixed(1)}%</td>
                <td>{t.exit_date ? new Date(t.exit_date).toLocaleDateString() : "—"}</td>
                <td>{t.exit_reason ?? "—"}</td>
                <td>
                  <Link href={`/paper-trading-lab/${t.id}`} className="qqq-btn">
                    Detail
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
