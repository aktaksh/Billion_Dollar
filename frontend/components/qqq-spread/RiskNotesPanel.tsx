import type { QqqSpreadAnalysis } from "@/types/qqqSpreadAnalyzer";

type Props = { data: QqqSpreadAnalysis };

export default function RiskNotesPanel({ data }: Props) {
  const notes = [
    "Research only — no orders placed.",
    ...(data.risk_notes ?? []),
    `Open positions (read-only): ${data.positions_count}`,
    `Open orders (read-only): ${data.open_orders_count}`,
    ...data.score.invalid_conditions,
  ];

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Risk Notes</h2>
      </div>
      <ul className="qqq-muted-list">
        {notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </section>
  );
}
