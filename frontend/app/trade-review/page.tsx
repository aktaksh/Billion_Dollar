import { getTradeReviewQueue } from "@/lib/api";

export default async function TradeReviewPage() {
  const items = await getTradeReviewQueue();

  return (
    <main className="grid">
      <section className="card">
        <h2 className="title-red" style={{ marginTop: 0 }}>
          Trade Review Queue
        </h2>
        <p style={{ marginTop: 0 }}>
          High-priority items: overrides, delayed quote usage, and approved negative-edge cases.
        </p>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Severity</th>
              <th>Issue</th>
              <th>Aggregate</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr key={`${item.aggregate_id}-${idx}`}>
                <td>{new Date(item.occurred_at).toLocaleString()}</td>
                <td>
                  <span
                    className={`badge ${
                      item.severity === "high"
                        ? "badge-red"
                        : item.severity === "medium"
                          ? "badge-blue"
                          : "badge-green"
                    }`}
                  >
                    {item.severity}
                  </span>
                </td>
                <td>{item.issue_type}</td>
                <td>{item.aggregate_id}</td>
                <td>{item.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}


