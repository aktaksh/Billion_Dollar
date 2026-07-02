import type { QqqLevelRow } from "@/types/qqqSpreadAnalyzer";

type Props = {
  supportLevels: QqqLevelRow[];
  resistanceLevels: QqqLevelRow[];
};

function LevelTable({ title, rows }: { title: string; rows: QqqLevelRow[] }) {
  return (
    <div>
      <h3 style={{ fontSize: "0.85rem", marginBottom: "0.5rem" }}>{title}</h3>
      {rows.length === 0 ? (
        <p className="qqq-empty">No levels</p>
      ) : (
        <div className="table-wrap">
          <table className="qqq-table">
            <thead>
              <tr>
                <th>Level</th>
                <th>Kind</th>
                <th className="num">Distance $</th>
                <th className="num">Distance %</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.kind}-${row.price}`}>
                  <td className="num">{row.price.toFixed(2)}</td>
                  <td><span className="qqq-level-kind">{row.kind.replaceAll("_", " ")}</span></td>
                  <td className="num">{row.distance_abs >= 0 ? `+${row.distance_abs.toFixed(2)}` : row.distance_abs.toFixed(2)}</td>
                  <td className="num">{row.distance_pct >= 0 ? `+${row.distance_pct.toFixed(2)}%` : `${row.distance_pct.toFixed(2)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function KeyLevelsPanel({ supportLevels, resistanceLevels }: Props) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Key Levels</h2>
      </div>
      <div className="qqq-grid-2">
        <LevelTable title="Support" rows={supportLevels} />
        <LevelTable title="Resistance" rows={resistanceLevels} />
      </div>
    </section>
  );
}
