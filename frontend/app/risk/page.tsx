import { getRiskStatus } from "@/lib/api";

export default async function RiskPage() {
  const risk = await getRiskStatus();

  return (
    <main className="grid">
      <section className="card">
        <h2 className="title-red" style={{ marginTop: 0 }}>
          Risk Cockpit
        </h2>
        <div className="grid grid-3">
          <div className="card">
            <div>Trading Mode</div>
            <div className="mono text-blue">{risk.trading_mode}</div>
          </div>
          <div className="card">
            <div>Drawdown</div>
            <div className={`mono ${risk.drawdown_pct <= -8 ? "text-red" : "text-green"}`}>
              {risk.drawdown_pct.toFixed(2)}%
            </div>
          </div>
          <div className="card">
            <div>Worst-Case Stress</div>
            <div className={`mono ${risk.worst_case_stress_loss_nav_pct <= -1.5 ? "text-red" : "text-green"}`}>
              {risk.worst_case_stress_loss_nav_pct.toFixed(2)}%
            </div>
          </div>
        </div>
        <p style={{ marginTop: 12 }}>
          New entries:{" "}
          <strong className={risk.can_open_new_entries ? "text-green" : "text-red"}>
            {risk.can_open_new_entries ? "ALLOWED" : "BLOCKED"}
          </strong>
        </p>
        <p style={{ marginBottom: 0 }}>
          Active halts: {risk.active_halts.length ? risk.active_halts.join(", ") : "none"}
        </p>
      </section>
    </main>
  );
}


