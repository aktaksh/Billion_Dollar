import Link from "next/link";

import { dteFromExpiry, formatExpiryDate } from "@/lib/expiryFormat";
import type { PaperTrade } from "@/types/paperTrading";

type Props = {
  trades: PaperTrade[];
  onClose: (trade: PaperTrade) => void;
};

function pnlClass(n: number): string {
  if (n > 0) return "pt-pnl-pos";
  if (n < 0) return "pt-pnl-neg";
  return "";
}

function progressPct(trade: PaperTrade): number {
  if (trade.progress_pct != null) return Math.max(0, Math.min(100, trade.progress_pct));
  const pnl = trade.unrealized_pnl ?? 0;
  const maxProfit = trade.max_profit || 1;
  return Math.max(0, Math.min(100, (pnl / maxProfit) * 100));
}

function avgCostPerContract(trade: PaperTrade): number {
  if (trade.average_cost != null) return trade.average_cost;
  return trade.entry_debit ?? trade.entry_credit ?? 0;
}

export default function OpenTradesTable({ trades, onClose }: Props) {
  if (trades.length === 0) {
    return <p className="qqq-empty">No open paper trades.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="qqq-table pt-wide-table">
        <thead>
          <tr>
            <th>Underlying</th>
            <th>Strategy</th>
            <th>Expiry</th>
            <th className="num">Long</th>
            <th className="num">Short</th>
            <th className="num">Qty</th>
            <th className="num">Avg cost</th>
            <th className="num">Spread value</th>
            <th className="num">PnL</th>
            <th className="num">Today PnL</th>
            <th className="num">Mkt value</th>
            <th className="num">DTE</th>
            <th>Progress</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const pnl = t.unrealized_pnl ?? 0;
            const pct = progressPct(t);
            const dte = t.days_to_entry_dte ?? dteFromExpiry(t.expiry_date);
            return (
              <tr key={t.id}>
                <td>{t.symbol}</td>
                <td>{t.strategy_type}</td>
                <td>{formatExpiryDate(t.expiry_date)}</td>
                <td className="num">{t.long_strike.toFixed(0)}</td>
                <td className="num">{t.short_strike.toFixed(0)}</td>
                <td className="num">{t.quantity}</td>
                <td className="num">${avgCostPerContract(t).toFixed(2)}</td>
                <td className="num">${(t.current_spread_value ?? 0).toFixed(2)}</td>
                <td className={`num ${pnlClass(pnl)}`}>${pnl.toFixed(2)}</td>
                <td className={`num ${pnlClass(t.today_pnl ?? 0)}`}>${(t.today_pnl ?? 0).toFixed(2)}</td>
                <td className="num">${(t.market_value ?? t.current_spread_value ?? 0).toFixed(2)}</td>
                <td className="num">{dte}</td>
                <td>
                  <div className="pt-progress" title={`${pct.toFixed(0)}% toward max profit`}>
                    <div className="pt-progress-bar" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="muted-text">{pct.toFixed(0)}%</span>
                </td>
                <td>
                  {t.status}
                  {t.source === "ibkr" && <span className="pt-ibkr-badge">IBKR</span>}
                </td>
                <td className="pt-row-actions">
                  <Link href={`/paper-trading-lab/${t.id}`} className="qqq-btn">
                    Detail
                  </Link>
                  <button type="button" className="qqq-btn" onClick={() => onClose(t)}>
                    Close
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
