"use client";

import type { TradeCard } from "@/types";

type Props = {
  card: TradeCard | null;
  ticker: string | null;
  open: boolean;
  onClose: () => void;
  globalBlocked: boolean;
  tickerDataBlocked: boolean;
};

function kvRows(record: Record<string, unknown> | null | undefined) {
  if (!record) return [];
  return Object.entries(record);
}

export default function TradeCardDrawer({ card, ticker, open, onClose, globalBlocked, tickerDataBlocked }: Props) {
  if (!open) return null;
  const actionsBlocked = globalBlocked || tickerDataBlocked;
  return (
    <div className="drawer-backdrop" role="dialog" aria-modal="true">
      <aside className="trade-drawer panel">
        <div className="drawer-header">
          <div>
            <h2 className="panel-title">Trade Card {ticker ? `- ${ticker}` : ""}</h2>
            <p className="muted-text">Thesis, structure, risk and approval context</p>
          </div>
          <button type="button" className="ghost-button" onClick={onClose}>
            Close
          </button>
        </div>

        {tickerDataBlocked ? (
          <div className="banner banner-warning">Data health is BLOCKED for this ticker. Execution actions are disabled.</div>
        ) : null}

        {!card ? (
          <p className="muted-text">Select a watchlist row to open details.</p>
        ) : (
          <div className="drawer-content">
            <div className="drawer-grid">
              <div className="stat-cell">
                <span className="muted-text">State</span>
                <strong className="mono">{card.state}</strong>
              </div>
              <div className="stat-cell">
                <span className="muted-text">Confidence</span>
                <strong className="mono">{card.confidence_total.toFixed(1)}</strong>
              </div>
              <div className="stat-cell">
                <span className="muted-text">Last Price</span>
                <strong className="mono">{card.last_price ?? "-"}</strong>
              </div>
            </div>

            <section className="panel-sub">
              <h3>Thesis</h3>
              <pre className="mono feed-details">{JSON.stringify(card.thesis, null, 2)}</pre>
            </section>

            <section className="panel-sub">
              <h3>Confidence Breakdown</h3>
              <ul className="dense-list">
                {Object.entries(card.confidence_components).map(([k, v]) => (
                  <li key={k}>
                    <span>{k}</span>
                    <span className="mono">{Number(v).toFixed(1)}</span>
                  </li>
                ))}
                {Object.keys(card.confidence_components).length === 0 ? <li className="muted-text">No breakdown available.</li> : null}
              </ul>
            </section>

            <section className="panel-sub">
              <h3>Structure Summary</h3>
              <ul className="dense-list">
                {kvRows(card.structure_summary).map(([k, v]) => (
                  <li key={k}>
                    <span>{k}</span>
                    <span className="mono">{String(v)}</span>
                  </li>
                ))}
                {!card.structure_summary ? <li className="muted-text">No structure proposed yet.</li> : null}
              </ul>
            </section>

            <section className="panel-sub">
              <h3>Risk Summary</h3>
              <ul className="dense-list">
                {kvRows(card.risk_summary).map(([k, v]) => (
                  <li key={k}>
                    <span>{k}</span>
                    <span className="mono">{Array.isArray(v) ? v.join(", ") : String(v)}</span>
                  </li>
                ))}
                {!card.risk_summary ? <li className="muted-text">No risk decision yet.</li> : null}
              </ul>
            </section>

            <div className="drawer-actions">
              <button type="button" className="primary-button" disabled={actionsBlocked}>
                Build Structure
              </button>
              <button type="button" className="secondary-button" disabled={actionsBlocked}>
                Run Risk
              </button>
              <button type="button" className="secondary-button" disabled={actionsBlocked}>
                Request Approval
              </button>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
