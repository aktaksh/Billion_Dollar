"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { HistoryPoint } from "@/types/marketRegimeDashboard";

type Props = {
  history: HistoryPoint[];
  days: number;
  onDaysChange: (d: number) => void;
};

const CONF_MAP: Record<string, number> = { Low: 1, Medium: 2, High: 3 };
const RISK_MAP: Record<string, number> = { Low: 1, Medium: 2, High: 3, Extreme: 4 };

export default function RegimeHistoryCharts({ history, days, onDaysChange }: Props) {
  const chartData = [...history]
    .reverse()
    .map((h) => ({
      date: h.timestamp.slice(0, 10),
      score: h.regime_score,
      confidence: CONF_MAP[h.confidence] ?? 2,
      risk: RISK_MAP[h.risk_level] ?? 2,
    }));

  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Regime History</h2>
        <div className="mr-filter-row">
          {[7, 30, 90, 365].map((d) => (
            <button
              key={d}
              type="button"
              className={`qqq-btn mr-filter-btn ${days === d ? "is-active" : ""}`}
              onClick={() => onDaysChange(d)}
            >
              {d === 365 ? "1Y" : `${d}D`}
            </button>
          ))}
        </div>
      </div>
      {chartData.length === 0 ? (
        <p className="mr-unavailable">No saved snapshots yet. Click Save Snapshot to record daily regime.</p>
      ) : (
        <div className="mr-chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="var(--muted)" />
              <YAxis yAxisId="score" tick={{ fontSize: 11 }} stroke="var(--muted)" domain={[-100, 100]} />
              <YAxis yAxisId="level" orientation="right" hide domain={[0, 4]} />
              <Tooltip contentStyle={{ background: "var(--panel)", border: "1px solid var(--border)" }} />
              <Legend />
              <Line yAxisId="score" type="monotone" dataKey="score" name="Regime Score" stroke="#27ae60" dot={false} />
              <Line yAxisId="level" type="monotone" dataKey="confidence" name="Confidence" stroke="#3498db" dot={false} />
              <Line yAxisId="level" type="monotone" dataKey="risk" name="Risk Level" stroke="#e67e22" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
