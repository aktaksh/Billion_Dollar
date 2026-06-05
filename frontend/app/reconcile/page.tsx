import { getReconcileMismatches } from "@/lib/api";

export default async function ReconcilePage() {
  const mismatches = await getReconcileMismatches();
  const blocking = mismatches.some((m) => m.blocking);

  return (
    <main className="grid">
      {blocking ? (
        <section className="card" style={{ borderColor: "rgba(255, 92, 112, 0.6)" }}>
          <h2 className="title-red" style={{ marginTop: 0 }}>
            Reconcile Blocking: New Entries Disabled
          </h2>
          <p style={{ margin: 0 }}>One or more active mismatches are blocking trade entries until resolved.</p>
        </section>
      ) : null}
      <section className="card">
        <h2 className="title-blue" style={{ marginTop: 0 }}>
          Reconcile Mismatches
        </h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Ticker</th>
              <th>Severity</th>
              <th>Blocking</th>
              <th>Reason</th>
              <th>Age (sec)</th>
            </tr>
          </thead>
          <tbody>
            {mismatches.length === 0 ? (
              <tr>
                <td colSpan={6}>No mismatches detected. App state matches TWS broker state.</td>
              </tr>
            ) : (
              mismatches.map((row) => (
                <tr key={row.mismatch_id}>
                  <td className="mono">{row.mismatch_id}</td>
                  <td>{row.ticker ?? "-"}</td>
                  <td>
                    <span
                      className={`badge ${
                        row.severity === "high"
                          ? "badge-red"
                          : row.severity === "medium"
                            ? "badge-blue"
                            : "badge-green"
                      }`}
                    >
                      {row.severity}
                    </span>
                  </td>
                  <td>{row.blocking ? "yes" : "no"}</td>
                  <td>{row.reason}</td>
                  <td>{row.mismatch_age_seconds}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}
