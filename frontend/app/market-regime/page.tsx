"use client";

import { useCallback, useEffect, useState } from "react";

import RegimeHistoryCharts from "@/components/market-regime/RegimeHistoryCharts";
import StrategyMatrixTable from "@/components/market-regime/StrategyMatrixTable";
import {
  exportMarketRegime,
  getMarketRegimeHistory,
  getMarketRegimeLatest,
  refreshAllMarketData,
  refreshMarketRegime,
  saveMarketRegimeSnapshot,
} from "@/lib/marketRegimeApi";
import type { MarketRegimeDashboard } from "@/types/marketRegimeDashboard";
import "@/styles/market-regime.css";

function scoreColorClass(score: number): string {
  if (score >= 60) return "mr-score-green";
  if (score >= 20) return "mr-score-light-green";
  if (score >= -19) return "mr-score-yellow";
  if (score >= -59) return "mr-score-orange";
  return "mr-score-red";
}

function regimeBadgeClass(name: string): string {
  if (name.includes("Strong Bull")) return "mr-badge-bull";
  if (name.includes("Bull")) return "mr-badge-neutral";
  if (name.includes("Bear")) return "mr-badge-bear";
  if (name.includes("Volatility")) return "mr-badge-neutral";
  return "mr-badge-neutral";
}

function progressColor(value: number): string {
  if (value >= 30) return "#27ae60";
  if (value >= 0) return "#6ab04c";
  if (value >= -30) return "#f1c40f";
  if (value >= -60) return "#e67e22";
  return "#c0392b";
}

function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(digits);
}

function trendBadgeClass(label: string): string {
  if (label === "Bullish") return "mr-badge-bull";
  if (label === "Bearish") return "mr-badge-bear";
  if (label === "Unavailable") return "mr-badge-na";
  return "mr-badge-neutral";
}

export default function MarketRegimePage() {
  const [data, setData] = useState<MarketRegimeDashboard | null>(null);
  const [history, setHistory] = useState<Awaited<ReturnType<typeof getMarketRegimeHistory>>>([]);
  const [historyDays, setHistoryDays] = useState(30);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  const loadHistory = useCallback(async (days: number) => {
    try {
      const rows = await getMarketRegimeHistory(days);
      setHistory(rows);
    } catch {
      setHistory([]);
    }
  }, []);

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const [dash] = await Promise.all([getMarketRegimeLatest(), loadHistory(historyDays)]);
      setData(dash);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load market regime");
    } finally {
      setBusy(false);
    }
  }, [historyDays, loadHistory]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleRefresh() {
    setBusy(true);
    setError("");
    try {
      const dash = await refreshMarketRegime();
      setData(dash);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleRefreshAll() {
    setBusy(true);
    setError("");
    try {
      const dash = await refreshAllMarketData();
      setData(dash);
      await loadHistory(historyDays);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh all failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleSave() {
    setBusy(true);
    try {
      const res = await saveMarketRegimeSnapshot();
      setToast(`Snapshot saved for ${res.snapshot_date}`);
      await loadHistory(historyDays);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleExport() {
    try {
      const json = await exportMarketRegime();
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `market-regime-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    }
  }

  const lastUpdated = data?.timestamp ? new Date(data.timestamp).toLocaleString() : "—";
  const scores = data?.score_breakdown;
  const scoreItems = scores
    ? [
        { label: "Trend", value: scores.trend_score, weight: "30%" },
        { label: "Momentum", value: scores.momentum_score, weight: "20%" },
        { label: "Volatility", value: scores.volatility_score, weight: "20%" },
        { label: "Breadth", value: scores.breadth_score, weight: "15%" },
        { label: "Macro", value: scores.macro_score, weight: "10%" },
        { label: "News/Catalysts", value: scores.news_catalyst_score, weight: "5%" },
      ]
    : [];

  return (
    <div className="container page-stack mr-page">
      <section className="panel">
        <div className="mr-header">
          <div>
            <h1 className="panel-title">Market Regime</h1>
            <p className="muted-text">Broad market health, risk environment, and preferred options strategy filter.</p>
            <div className="mr-meta">
              <span>Last Updated: {lastUpdated}</span>
              {data && (
                <>
                  <span>IBKR: {data.data_source.ibkr}</span>
                  <span>Analyzer: {data.data_source.analyzer}</span>
                  <span>Macro: {data.data_source.macro}</span>
                </>
              )}
            </div>
          </div>
          <div className="mr-header-actions">
            <button type="button" className="qqq-btn" onClick={() => void handleRefresh()} disabled={busy}>
              Refresh Regime
            </button>
            <button type="button" className="qqq-btn" onClick={() => void handleRefreshAll()} disabled={busy}>
              Refresh All Market Data
            </button>
            <button type="button" className="qqq-btn qqq-btn-primary" onClick={() => void handleSave()} disabled={busy}>
              Save Snapshot
            </button>
            <button type="button" className="qqq-btn" onClick={() => void handleExport()} disabled={busy}>
              Export
            </button>
          </div>
        </div>
      </section>

      {error && <div className="banner banner-danger">{error}</div>}
      {toast && <div className="banner banner-success">{toast}</div>}

      {!data && !error && (
        <section className="panel">
          <p className="qqq-empty">{busy ? "Loading market regime…" : "No regime data yet."}</p>
        </section>
      )}

      {data && (
        <>
          {/* ROW 1: Summary cards */}
          <section className="panel">
            <div className="mr-cards-5">
              <article className="mr-card">
                <div className="mr-card-label">Overall Market Regime</div>
                <div className={`mr-regime-badge ${regimeBadgeClass(data.summary.regime_name)}`}>
                  {data.summary.regime_name}
                </div>
              </article>
              <article className="mr-card">
                <div className="mr-card-label">Regime Score</div>
                <div className={`mr-card-value ${scoreColorClass(data.summary.regime_score)}`}>
                  {data.summary.regime_score >= 0 ? "+" : ""}
                  {data.summary.regime_score}
                </div>
              </article>
              <article className="mr-card">
                <div className="mr-card-label">Confidence</div>
                <div className="mr-card-value">{data.summary.confidence}</div>
              </article>
              <article className="mr-card">
                <div className="mr-card-label">Risk Level</div>
                <div className="mr-card-value">{data.summary.risk_level}</div>
              </article>
              <article className="mr-card">
                <div className="mr-card-label">Preferred Strategy</div>
                <div className="mr-card-value">{data.summary.preferred_strategy}</div>
              </article>
            </div>
          </section>

          {/* ROW 2: Broader market snapshot */}
          <section className="panel">
            <h2 className="panel-title">Broader Market Snapshot</h2>
            <div className="mr-instrument-grid">
              {data.instruments.map((inst) => (
                <div key={inst.symbol} className="mr-instrument-card">
                  <div className="mr-instrument-symbol">{inst.symbol}</div>
                  <div className="mr-instrument-price">
                    {inst.available ? fmt(inst.price) : <span className="mr-unavailable">Data unavailable</span>}
                  </div>
                  {inst.daily_pct != null && (
                    <div className={inst.daily_pct >= 0 ? "mr-score-green" : "mr-score-red"}>
                      {inst.daily_pct >= 0 ? "+" : ""}
                      {inst.daily_pct}%
                    </div>
                  )}
                  <div className="mr-badge-row">
                    <span className={`mr-mini-badge ${trendBadgeClass(inst.trend_badge)}`}>{inst.trend_badge}</span>
                    <span className="mr-mini-badge">{inst.risk_badge}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* ROW 3: Score breakdown */}
          <section className="panel">
            <h2 className="panel-title">Score Breakdown</h2>
            <div className="mr-score-bars">
              {scoreItems.map((item) => (
                <div key={item.label} className="mr-score-row">
                  <span>
                    {item.label} <span className="muted-text">({item.weight})</span>
                  </span>
                  <div className="mr-progress-track">
                    <div
                      className="mr-progress-fill"
                      style={{
                        width: `${Math.min(100, Math.abs(item.value))}%`,
                        background: progressColor(item.value),
                      }}
                    />
                  </div>
                  <strong className={scoreColorClass(item.value)}>
                    {item.value >= 0 ? "+" : ""}
                    {item.value}
                  </strong>
                </div>
              ))}
              <div className="mr-score-row">
                <span>
                  <strong>Final Score</strong>
                </span>
                <div className="mr-progress-track">
                  <div
                    className="mr-progress-fill"
                    style={{
                      width: `${Math.min(100, Math.abs(data.summary.regime_score))}%`,
                      background: progressColor(data.summary.regime_score),
                    }}
                  />
                </div>
                <strong className={scoreColorClass(data.summary.regime_score)}>
                  {data.summary.regime_score >= 0 ? "+" : ""}
                  {data.summary.regime_score}
                </strong>
              </div>
            </div>
          </section>

          {/* ROW 4: Multi-timeframe */}
          <section className="panel">
            <h2 className="panel-title">Multi-Timeframe Trend</h2>
            <div className="mr-tf-grid">
              {data.multi_timeframe.map((tf) => (
                <div key={tf.timeframe} className="mr-tf-card">
                  <div className="mr-tf-title">{tf.timeframe}</div>
                  {!tf.available ? (
                    <p className="mr-unavailable">{tf.note ?? "Data unavailable"}</p>
                  ) : (
                    <table className="qqq-table mr-table-compact">
                      <tbody>
                        <tr><th>Close</th><td className="num">{fmt(tf.close)}</td></tr>
                        <tr><th>EMA20</th><td className="num">{fmt(tf.ema20)}</td></tr>
                        <tr><th>EMA50</th><td className="num">{fmt(tf.ema50)}</td></tr>
                        <tr><th>SMA200</th><td className="num">{fmt(tf.sma200)}</td></tr>
                        <tr><th>RSI14</th><td className="num">{fmt(tf.rsi14)}</td></tr>
                        <tr><th>MACD</th><td className="num">{fmt(tf.macd_line, 3)} / {fmt(tf.macd_signal, 3)}</td></tr>
                        <tr><th>Hist</th><td className="num">{fmt(tf.macd_hist, 3)}</td></tr>
                        <tr><th>ATR14</th><td className="num">{fmt(tf.atr14)}</td></tr>
                        <tr><th>Trend</th><td>{tf.trend_label}</td></tr>
                        <tr><th>Signal</th><td>{tf.signal_label}</td></tr>
                      </tbody>
                    </table>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* ROW 5: Market breadth */}
          <section className="panel">
            <h2 className="panel-title">Market Breadth</h2>
            <div className="mr-heatmap">
              {data.breadth.heatmap.map((cell) => (
                <div
                  key={cell.symbol}
                  className={`mr-heatmap-cell mr-heatmap-${cell.state}`}
                >
                  {cell.symbol}
                  <br />
                  {cell.state === "bull" ? "Above EMA20" : cell.state === "bear" ? "Below EMA20" : "N/A"}
                </div>
              ))}
            </div>
            <div className="table-wrap">
              <table className="qqq-table mr-table-compact">
                <tbody>
                  <tr><th>QQQ above EMA20?</th><td>{String(data.breadth.qqq_above_ema20 ?? "N/A")}</td></tr>
                  <tr><th>SPY above EMA20?</th><td>{String(data.breadth.spy_above_ema20 ?? "N/A")}</td></tr>
                  <tr><th>IWM above EMA20?</th><td>{String(data.breadth.iwm_above_ema20 ?? "N/A")}</td></tr>
                  <tr><th>DIA above EMA20?</th><td>{String(data.breadth.dia_above_ema20 ?? "N/A")}</td></tr>
                  <tr><th>SMH/SOXX confirming?</th><td>{String(data.breadth.smh_soxx_confirming)}</td></tr>
                  <tr><th>Major indexes bullish</th><td>{data.breadth.bullish_count}</td></tr>
                  <tr><th>Major indexes bearish</th><td>{data.breadth.bearish_count}</td></tr>
                  <tr><th>Breadth score</th><td className={scoreColorClass(data.breadth.breadth_score)}>{data.breadth.breadth_score}</td></tr>
                </tbody>
              </table>
            </div>
          </section>

          {/* ROW 6: Volatility */}
          <section className="panel">
            <h2 className="panel-title">Volatility and Risk</h2>
            <div className="qqq-grid-2">
              <table className="qqq-table mr-table-compact">
                <tbody>
                  <tr><th>VIX level</th><td>{fmt(data.volatility.vix_level)}</td></tr>
                  <tr><th>VIX daily change</th><td>{data.volatility.vix_daily_change_pct != null ? `${data.volatility.vix_daily_change_pct}%` : "—"}</td></tr>
                  <tr><th>ATR trend</th><td>{data.volatility.atr_trend}</td></tr>
                  <tr><th>Bollinger width</th><td>{data.volatility.bollinger_width_pct != null ? `${data.volatility.bollinger_width_pct}%` : "—"}</td></tr>
                  <tr><th>IV Rank</th><td>{data.volatility.iv_rank ?? "—"}</td></tr>
                  <tr><th>IV Percentile</th><td>{data.volatility.iv_percentile ?? "—"}</td></tr>
                  <tr><th>Volatility regime</th><td><strong>{data.volatility.volatility_regime}</strong></td></tr>
                </tbody>
              </table>
            </div>
          </section>

          {/* ROW 7: Macro */}
          <section className="panel">
            <h2 className="panel-title">Macro Panel</h2>
            <div className="mr-instrument-grid">
              {[
                { label: "10Y Treasury Yield", value: data.macro.ten_year_yield },
                { label: "2Y Treasury Yield", value: data.macro.two_year_yield },
                { label: "Yield Curve (10Y−2Y)", value: data.macro.yield_curve_10y_minus_2y },
                { label: "DXY", value: data.macro.dxy },
                { label: "Fed Funds Rate", value: data.macro.fed_funds_rate },
                { label: "Next CPI", value: data.macro.next_cpi_date },
                { label: "Next FOMC", value: data.macro.next_fomc_date },
                { label: "Next Jobs Report", value: data.macro.next_jobs_report_date },
              ].map((item) => (
                <div key={item.label} className="mr-instrument-card">
                  <div className="mr-card-label">{item.label}</div>
                  <div className="mr-instrument-price">
                    {item.value != null ? String(item.value) : <span className="mr-unavailable">Data unavailable</span>}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* ROW 8: Strategy matrix */}
          <section className="panel">
            <h2 className="panel-title">Strategy Matrix</h2>
            <StrategyMatrixTable rows={data.strategy_matrix} highlightRegime={data.summary.regime_name} />
          </section>

          {/* ROW 9: Catalyst watch */}
          <section className="panel">
            <h2 className="panel-title">Catalyst Watch</h2>
            <div className="table-wrap">
              <table className="qqq-table mr-table-compact">
                <thead>
                  <tr>
                    <th>Event</th>
                    <th>Date</th>
                    <th>Time</th>
                    <th>Expected impact</th>
                    <th>Risk level</th>
                    <th>Countdown</th>
                  </tr>
                </thead>
                <tbody>
                  {data.catalysts.map((c) => (
                    <tr key={`${c.event}-${c.date}`}>
                      <td>{c.event}</td>
                      <td>{c.date}</td>
                      <td>{c.time}</td>
                      <td>{c.expected_impact}</td>
                      <td>{c.risk_level}</td>
                      <td>{c.countdown_days}d</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* ROW 10: Regime history */}
          <RegimeHistoryCharts
            history={history}
            days={historyDays}
            onDaysChange={(d) => {
              setHistoryDays(d);
              void loadHistory(d);
            }}
          />

          {/* ROW 11: AI summary */}
          <section className="panel mr-ai-panel">
            <h2 className="panel-title">AI Summary</h2>
            <p>{data.ai_summary.narrative.replace(/\*\*/g, "")}</p>
            <p><strong>Why it changed:</strong> {data.ai_summary.why_changed}</p>
            <div className="qqq-grid-2">
              <div>
                <strong>Confirms</strong>
                <ul>{data.ai_summary.confirms.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
              <div>
                <strong>Contradicts</strong>
                <ul>{data.ai_summary.contradicts.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
            </div>
            <p><strong>Preferred:</strong> {data.ai_summary.preferred_strategies.join(", ")}</p>
            <p><strong>Avoid:</strong> {data.ai_summary.avoid_strategies.join(", ")}</p>
            <p><strong>Watch:</strong> {data.ai_summary.key_levels_events.join(", ")}</p>
          </section>
        </>
      )}
    </div>
  );
}
