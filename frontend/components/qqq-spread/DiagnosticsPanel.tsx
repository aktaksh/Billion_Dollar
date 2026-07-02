import type { QqqDiagnostics } from "@/types/qqqSpreadAnalyzer";

type Props = { diagnostics: QqqDiagnostics; runError?: string | null };

export default function DiagnosticsPanel({ diagnostics, runError }: Props) {
  const failures = diagnostics.qualification_failures ?? [];

  return (
    <section className="panel qqq-diag">
      <details>
        <summary>Raw Diagnostics</summary>
        <div className="table-wrap" style={{ marginTop: "0.5rem" }}>
          <table className="qqq-table">
            <tbody>
              <tr><th>IB connected</th><td>{diagnostics.ib_connected ? "yes" : "no"}</td></tr>
              <tr><th>IB host</th><td>{diagnostics.ib_host ?? "—"}:{diagnostics.ib_port ?? "—"} (client {diagnostics.ib_client_id ?? "—"})</td></tr>
              <tr><th>Daily bars</th><td>{diagnostics.daily_bars ?? "—"} {diagnostics.cache_status?.daily ? "(cached)" : ""}</td></tr>
              <tr><th>Intraday bars</th><td>{diagnostics.intraday_bars ?? "—"} {diagnostics.cache_status?.intraday ? "(cached)" : ""}</td></tr>
              <tr><th>Contracts planned</th><td>{diagnostics.contracts_planned ?? "—"}</td></tr>
              <tr><th>Contracts qualified</th><td>{diagnostics.contracts_qualified ?? "—"}</td></tr>
              <tr><th>Raw option quotes</th><td>{diagnostics.raw_quotes ?? "—"}</td></tr>
              <tr><th>Liquid quotes</th><td>{diagnostics.liquid_quotes ?? "—"}</td></tr>
              <tr><th>IB Error 200 count</th><td>{diagnostics.ib_error_200_count ?? 0}</td></tr>
            </tbody>
          </table>
        </div>
        {failures.length > 0 && (
          <ul className="qqq-muted-list" style={{ marginTop: "0.75rem" }}>
            {failures.map((f) => (
              <li key={f.expiry}>
                {f.failed_count} contracts failed qualification for expiry {f.expiry}. {f.reason_hint}
              </li>
            ))}
          </ul>
        )}
        {runError && <p className="banner banner-danger" style={{ marginTop: "0.75rem" }}>{runError}</p>}
      </details>
    </section>
  );
}
