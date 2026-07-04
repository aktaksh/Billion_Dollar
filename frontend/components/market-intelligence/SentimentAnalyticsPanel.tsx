"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MicSentimentAnalytics } from "@/types/marketIntelligence";

type Props = { data: MicSentimentAnalytics };

const PIE_COLORS = ["#27ae60", "#c0392b", "#f1c40f"];

export default function SentimentAnalyticsPanel({ data }: Props) {
  const split = [
    { name: "Bullish", value: data.split.bullish },
    { name: "Bearish", value: data.split.bearish },
    { name: "Neutral", value: data.split.neutral },
  ];
  const total = split.reduce((s, x) => s + x.value, 0);

  if (total === 0 && data.trend.length === 0) {
    return (
      <p className="muted-text mic-empty">
        No sentiment data yet. Run a refresh to populate news_items before charts can render.
      </p>
    );
  }

  return (
    <div className="mic-charts-grid">
      <div className="mic-chart-box">
        <h3 className="mic-chart-title">Bull / Bear / Neutral</h3>
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie data={split} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label>
              {split.map((_, i) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="mic-chart-box">
        <h3 className="mic-chart-title">Sentiment trend (14d)</h3>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data.trend}>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="bullish" stroke="#27ae60" dot={false} />
            <Line type="monotone" dataKey="bearish" stroke="#c0392b" dot={false} />
            <Line type="monotone" dataKey="neutral" stroke="#f1c40f" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="mic-chart-box">
        <h3 className="mic-chart-title">Most positive symbols</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data.most_positive}>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey="symbol" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip />
            <Bar dataKey="avg_sentiment" fill="#27ae60" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mic-chart-box">
        <h3 className="mic-chart-title">Most negative symbols</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data.most_negative}>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis dataKey="symbol" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip />
            <Bar dataKey="avg_sentiment" fill="#c0392b" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
