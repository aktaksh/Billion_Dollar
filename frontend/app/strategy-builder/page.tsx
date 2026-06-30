"use client";

import { useEffect, useMemo, useState } from "react";

import { getDevFlags, getRuntimeMode, runPaperTrade, runReplay, runStrategyRuntime, saveDecision } from "@/lib/api";
import type { PaperTradeRunOut, ReplayRunOut, RuntimeModeOut, StrategyCandidateOut, StrategyRuntimeOut, TradeDecision } from "@/types";

function renderLegs(candidate: StrategyCandidateOut) {
  return candidate.legs.map((leg) => `${leg.action} ${leg.option_type.toUpperCase()} ${leg.strike}`).join(" | ");
}

function riskClass(status: StrategyCandidateOut["risk_status"]) {
  if (status === "allow") return "sb-status sb-status-allow";
  if (status === "override_required") return "sb-status sb-status-override";
  if (status === "watch_only") return "sb-status sb-status-watch";
  return "sb-status sb-status-reject";
}

function isActionableCandidate(status: StrategyCandidateOut["risk_status"]) {
  return status === "allow" || status === "override_required";
}

function strikeDistancePct(strike: number, underlying: number | undefined) {
  if (!underlying || underlying <= 0) return null;
  return ((strike - underlying) / underlying) * 100;
}

function spreadWidth(candidate: StrategyCandidateOut) {
  const buy = candidate.legs.find((leg) => leg.action === "BUY");
  const sell = candidate.legs.find((leg) => leg.action === "SELL");
  if (!buy || !sell) return null;
  return Math.abs(Number(sell.strike) - Number(buy.strike));
}

function runtimeBlockMessage(reason: string | null | undefined): string {
  if (!reason) return "Runtime blocked — new entries disabled";
  if (reason === "option_chain_quality_failed_mock_data") {
    return "Blocked: cached mock option chain. Connect broker, refresh QQQ Options Chain, then rerun.";
  }
  if (reason === "option_chain_quality_failed_far_strikes") {
    return "Blocked: option strikes are far from current underlying";
  }
  if (reason === "option_chain_quality_failed_stale") {
    return "Blocked: scanner snapshot is stale";
  }
  if (reason === "option_chain_quality_failed_non_broker") {
    return "Blocked: option chain is not broker-backed";
  }
  if (reason === "option_chain_quality_failed_scanner_status") {
    return "Blocked: scanner data is not fresh or partially usable";
  }
  if (reason === "option_chain_quality_failed_no_quotes") {
    return "Blocked: no usable bid/ask quotes in option chain";
  }
  if (reason === "option_chain_quality_failed_no_underlying") {
    return "Blocked: underlying price is missing";
  }
  if (reason === "option_chain_quality_failed_seeded_fixture_in_production") {
    return "Blocked: testing fixture loaded in production mode — switch to Production in Settings and refresh QQQ chain";
  }
  if (reason === "option_chain_quality_failed_malformed") {
    return "Blocked: option chain data is malformed";
  }
  return reason.replaceAll("_", " ");
}

export default function StrategyBuilderPage() {
  const [universeScope, setUniverseScope] = useState<"etf" | "top_stocks" | "custom">("etf");
  const [symbol, setSymbol] = useState("QQQ");
  const [direction, setDirection] = useState<"bullish" | "bearish">("bullish");
  const [reconciliationMismatchActive, setReconciliationMismatchActive] = useState(false);
  const [maxLossUsd, setMaxLossUsd] = useState("500");
  const [minPop, setMinPop] = useState("0.4");
  const [loading, setLoading] = useState(false);
  const [replayLoading, setReplayLoading] = useState(false);
  const [paperLoading, setPaperLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [result, setResult] = useState<StrategyRuntimeOut | null>(null);
  const [replay, setReplay] = useState<ReplayRunOut | null>(null);
  const [paperResult, setPaperResult] = useState<PaperTradeRunOut | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<StrategyCandidateOut | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [savedDecision, setSavedDecision] = useState<TradeDecision | null>(null);
  const [saveLoading, setSaveLoading] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideNote, setOverrideNote] = useState("");
  const [showRejected, setShowRejected] = useState(false);
  const [devStaleRuntimeMode, setDevStaleRuntimeMode] = useState(false);
  const [runtimeMode, setRuntimeModeState] = useState<RuntimeModeOut | null>(null);

  useEffect(() => {
    void getRuntimeMode("QQQ")
      .then((mode) => {
        setRuntimeModeState(mode);
        setDevStaleRuntimeMode(Boolean(mode.allow_stale_runtime_dev));
      })
      .catch(() => {
        void getDevFlags()
          .then((flags) => setDevStaleRuntimeMode(Boolean(flags.allow_stale_runtime_dev)))
          .catch(() => setDevStaleRuntimeMode(false));
      });
  }, []);

  const openCandidate = (candidate: StrategyCandidateOut) => {
    if (!isActionableCandidate(candidate.risk_status)) return;
    setSelectedCandidate(candidate);
    setDrawerOpen(true);
  };

  const entriesBlocked = reconciliationMismatchActive || result?.runtime_allowed === false;

  const topCandidate = useMemo(
    () =>
      result?.top_recommendations?.[0]
      ?? result?.allowed_candidates?.[0]
      ?? result?.candidates.find((candidate) => candidate.risk_status === "allow")
      ?? null,
    [result],
  );
  const topThree = useMemo(
    () => (result?.runtime_allowed === false ? [] : (result?.top_recommendations ?? [])),
    [result],
  );
  const watchOnlyCandidates = useMemo(
    () => (result?.runtime_allowed === false ? [] : (result?.watch_only_candidates ?? [])),
    [result],
  );
  const visibleCandidates = useMemo(() => {
    if (!result) return [];
    const primary = [
      ...(result.allowed_candidates ?? []),
      ...(result.override_required_candidates ?? []),
      ...(result.watch_only_candidates ?? []),
    ];
    if (primary.length) {
      return showRejected ? [...primary, ...(result.rejected_candidates ?? [])] : primary;
    }
    const fallback = result.candidates.filter((candidate) => candidate.risk_status !== "reject");
    return showRejected ? result.candidates : fallback;
  }, [result, showRejected]);
  const inferredRegime = useMemo(() => {
    const regime = result?.setup_diagnostics?.regime;
    if (typeof regime === "string" && regime.length) return regime;
    if (!result?.candidates.length) return "unknown";
    if (reconciliationMismatchActive) return "risk_off";
    const allowed = result.candidates.filter((c) => c.risk_status === "allow").length;
    return allowed >= Math.ceil(result.candidates.length / 2) ? "risk_on" : "risk_off";
  }, [result, reconciliationMismatchActive]);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setErrorMessage("");
    try {
      const payload = {
        ticker: symbol.trim().toUpperCase(),
        direction,
        reconciliation_mismatch_active: reconciliationMismatchActive,
        thresholds: {
          max_loss_per_trade_usd: Number(maxLossUsd),
          min_probability_profit: Number(minPop),
        },
      } as const;
      const response = await runStrategyRuntime(payload);
      setResult(response);
      setReplay(null);
      setPaperResult(null);
      setSavedDecision(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to build strategy candidates");
    } finally {
      setLoading(false);
    }
  };

  const runReplayNow = async () => {
    setReplayLoading(true);
    setErrorMessage("");
    try {
      const replayOut = await runReplay({
        ticker: symbol.trim().toUpperCase(),
        direction,
      });
      setReplay(replayOut);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Replay failed");
    } finally {
      setReplayLoading(false);
    }
  };

  const runPaperNow = async () => {
    if (entriesBlocked) {
      setErrorMessage("New entries blocked by reconcile halt or runtime gate");
      return;
    }
    if (!savedDecision?.decision_id) {
      setErrorMessage("Save a candidate decision before running paper trade");
      return;
    }
    if (selectedCandidate?.risk_status && !isActionableCandidate(selectedCandidate.risk_status)) {
      setErrorMessage("Watch-only and rejected candidates cannot be paper traded");
      return;
    }
    setPaperLoading(true);
    setErrorMessage("");
    try {
      const paperOut = await runPaperTrade({
        mode: "decision",
        decision_id: savedDecision.decision_id,
      });
      setPaperResult(paperOut);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Paper trade simulation failed");
    } finally {
      setPaperLoading(false);
    }
  };

  const saveSelectedDecision = async (candidate: StrategyCandidateOut, rejected = false) => {
    setSaveLoading(true);
    setErrorMessage("");
    try {
      const saved = await saveDecision({
        candidate,
        symbol: symbol.trim().toUpperCase(),
        direction,
        confidence: candidate.strategy_score,
        edge: candidate.expected_value,
        market_regime: inferredRegime,
        thesis: rejected ? `Rejected ${candidate.strategy_type}` : `Strategy Builder save ${candidate.strategy_type}`,
        data_status: result?.data_status ?? "mock",
        broker_status: "disconnected",
        reconciliation_status: reconciliationMismatchActive ? "mismatch" : "ok",
        rejected,
      });
      if (!rejected) setSavedDecision(saved);
      setSelectedCandidate(candidate);
      return saved;
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to save decision");
      return null;
    } finally {
      setSaveLoading(false);
    }
  };

  return (
    <main className="container">
      <section className="card">
        <h2 className="panel-title">Strategy Builder</h2>
        <p className="muted-text">Ingestion + feature engine + strategy runtime + replay/paper-trade validation flow.</p>
        <form className="sb-form" onSubmit={onSubmit}>
          <label className="sb-field">
            Universe
            <select value={universeScope} onChange={(event) => setUniverseScope(event.target.value as "etf" | "top_stocks" | "custom")} className="feed-input">
              <option value="etf">ETF</option>
              <option value="top_stocks">Top stocks</option>
              <option value="custom">Custom</option>
            </select>
          </label>
          <label className="sb-field">
            Symbol
            <input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} className="feed-input" required />
          </label>
          <label className="sb-field">
            Direction
            <select value={direction} onChange={(event) => setDirection(event.target.value as "bullish" | "bearish")} className="feed-input">
              <option value="bullish">bullish</option>
              <option value="bearish">bearish</option>
            </select>
          </label>
          <label className="sb-field">
            Max Loss/Trade (USD)
            <input value={maxLossUsd} onChange={(event) => setMaxLossUsd(event.target.value)} className="feed-input" type="number" min="1" step="1" />
          </label>
          <label className="sb-field">
            Min POP
            <input value={minPop} onChange={(event) => setMinPop(event.target.value)} className="feed-input" type="number" min="0" max="1" step="0.01" />
          </label>
          <label className="sb-field sb-check">
            <input
              checked={reconciliationMismatchActive}
              onChange={(event) => setReconciliationMismatchActive(event.target.checked)}
              type="checkbox"
            />
            Reconciliation mismatch active
          </label>
          <div className="sb-actions">
            <button type="submit" className="primary-button" disabled={loading}>
              {loading ? "Running..." : "Run Runtime Flow"}
            </button>
            <button type="button" className="secondary-button" onClick={runReplayNow} disabled={replayLoading}>
              {replayLoading ? "Replay..." : "Run Replay"}
            </button>
            <button type="button" className="secondary-button" onClick={runPaperNow} disabled={paperLoading || entriesBlocked || !savedDecision}>
              {paperLoading ? "Paper..." : "Run Paper Trade"}
            </button>
          </div>
        </form>
        {errorMessage ? <p className="danger-text">{errorMessage}</p> : null}
        {runtimeMode?.runtime_mode === "testing" ? (
          <div className="banner banner-warning">
            Testing mode — recommendations may use fixture or stale cache, not live market data.
          </div>
        ) : null}
        {devStaleRuntimeMode && runtimeMode?.runtime_mode !== "testing" ? (
          <div className="banner banner-warning">
            Dev mode: allow_stale_runtime_dev is enabled — stale broker cache may be used for Strategy Builder.
          </div>
        ) : null}
        {entriesBlocked ? (
          <div className="banner banner-danger">
            {reconciliationMismatchActive
              ? "Reconcile halt active — new entries blocked"
              : runtimeBlockMessage(result?.runtime_block_reason)}
          </div>
        ) : null}
        {!entriesBlocked && result?.no_trade ? (
          <div className="banner banner-warning">
            NO_TRADE: setup and regime filters left no allowed debit spreads. Review watch-only candidates or wait for a confirmed setup.
          </div>
        ) : null}
        {!entriesBlocked && result?.runtime_warning ? (
          <div className="banner banner-warning">{result.runtime_warning}</div>
        ) : null}
        {!entriesBlocked && result?.chain_diagnostics?.scanner_status === "partial" ? (
          <div className="banner banner-warning">
            Partial: using broker data with limited usable contracts (
            {String(result.chain_diagnostics.usable_contracts ?? 0)} usable)
          </div>
        ) : null}
        {result?.chain_diagnostics ? (
          <div className="sb-top-grid">
            <div>
              <div className="muted-text">Chain source</div>
              <div className="mono">{String(result.chain_diagnostics.chain_source ?? "-")}</div>
            </div>
            <div>
              <div className="muted-text">Data status</div>
              <div className="mono">{String(result.chain_diagnostics.data_status ?? result.data_status ?? "-")}</div>
            </div>
            <div>
              <div className="muted-text">Scanner status</div>
              <div className="mono">{String(result.chain_diagnostics.scanner_status ?? "-")}</div>
            </div>
            <div>
              <div className="muted-text">Underlying used</div>
              <div className="mono">{Number(result.chain_diagnostics.underlying_price ?? 0).toFixed(2)}</div>
            </div>
            <div>
              <div className="muted-text">Snapshot age (s)</div>
              <div className="mono">{String(result.chain_diagnostics.snapshot_age_seconds ?? "-")}</div>
            </div>
            <div>
              <div className="muted-text">Nearest strike dist</div>
              <div className="mono">
                {result.chain_diagnostics.nearest_strike_distance_pct != null
                  ? `${(Number(result.chain_diagnostics.nearest_strike_distance_pct) * 100).toFixed(1)}%`
                  : "-"}
              </div>
            </div>
            <div>
              <div className="muted-text">Usable / rejected</div>
              <div className="mono">
                {String(result.chain_diagnostics.usable_contracts ?? 0)} /{" "}
                {String(result.chain_diagnostics.rejected_contracts ?? 0)}
              </div>
            </div>
          </div>
        ) : null}
        {savedDecision ? (
          <p className="muted-text">
            Saved decision: <span className="mono">{savedDecision.decision_id}</span>
          </p>
        ) : null}
        {result ? (
          <p className="muted-text">
            Data status: <span className="mono">{result.data_status}</span> / runtime allowed:{" "}
            <span className="mono">{result.runtime_allowed ? "yes" : "no"}</span>
          </p>
        ) : null}
        {paperResult ? (
          <div className="banner banner-warning">
            Paper trade result: signal `{paperResult.signal_id}`, PnL after costs ${paperResult.realized_pnl_after_costs_usd.toFixed(2)},
            entry {paperResult.entry_price.toFixed(2)}, exit {paperResult.exit_price.toFixed(2)}.
          </div>
        ) : null}
      </section>

      <section className="card sb-top-pick">
        <h3 className="panel-title">Market Regime & Signal Summary</h3>
        <div className="sb-top-grid">
          <div>
            <div className="muted-text">Universe</div>
            <div className="mono">{universeScope}</div>
          </div>
          <div>
            <div className="muted-text">Setup status</div>
            <div className="mono">{String(result?.setup_status ?? "-")}</div>
          </div>
          <div>
            <div className="muted-text">Regime</div>
            <div className="mono">{inferredRegime}</div>
          </div>
          <div>
            <div className="muted-text">Alpha (top)</div>
            <div className="mono">{topCandidate ? topCandidate.alpha_score.toFixed(1) : "-"}</div>
          </div>
          <div>
            <div className="muted-text">Liquidity (top)</div>
            <div className="mono">{topCandidate ? topCandidate.liquidity_score.toFixed(1) : "-"}</div>
          </div>
        </div>
      </section>

      {watchOnlyCandidates.length && result?.runtime_allowed !== false ? (
        <section className="card sb-cards">
          <h3 className="panel-title">Watch Only</h3>
          <p className="muted-text">Candidates downgraded by setup conflict, breakeven distance, or similar swing gates.</p>
          <div className="sb-card-grid">
            {watchOnlyCandidates.map((candidate) => (
              <div
                key={`watch-${candidate.strategy_type}-${candidate.expiry}-${renderLegs(candidate)}`}
                className="sb-card"
              >
                <div className="sb-card-head">
                  <span className="mono">{candidate.strategy_type}</span>
                  <span className={riskClass(candidate.risk_status)}>{candidate.risk_status}</span>
                </div>
                <div className="muted-text">DTE {candidate.dte} / Exp {candidate.expiry}</div>
                <div className="sb-card-metrics">
                  <span className="mono">Score {candidate.strategy_score.toFixed(2)}</span>
                  {candidate.breakeven_distance_pct != null ? (
                    <span className="mono">BE dist {(candidate.breakeven_distance_pct * 100).toFixed(1)}%</span>
                  ) : null}
                </div>
                <div className="muted-text">{renderLegs(candidate)}</div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {topThree.length && result?.runtime_allowed !== false ? (
        <section className="card sb-cards">
          <h3 className="panel-title">Top Recommendations</h3>
          <div className="sb-card-grid">
            {topThree.map((candidate) => (
              <button
                key={`${candidate.strategy_type}-${candidate.expiry}-${renderLegs(candidate)}`}
                type="button"
                className="sb-card"
                onClick={() => openCandidate(candidate)}
              >
                <div className="sb-card-head">
                  <span className="mono">{candidate.strategy_type}</span>
                  <span className={riskClass(candidate.risk_status)}>{candidate.risk_status}</span>
                </div>
                <div className="muted-text">DTE {candidate.dte} / Exp {candidate.expiry}</div>
                <div className="sb-card-metrics">
                  <span className="mono">Score {candidate.strategy_score.toFixed(2)}</span>
                  <span className={`mono ${candidate.expected_value >= 0 ? "success-text" : "danger-text"}`}>
                    Model EV ${candidate.expected_value.toFixed(2)}
                  </span>
                </div>
                <div className="muted-text">{renderLegs(candidate)}</div>
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {topCandidate && result?.runtime_allowed !== false ? (
        <section className="card sb-top-pick">
          <h3 className="panel-title">Top Candidate</h3>
          <div className="sb-top-grid">
            <div>
              <div className="muted-text">Strategy</div>
              <div className="mono">{topCandidate.strategy_type}</div>
            </div>
            <div>
              <div className="muted-text">Score</div>
              <div className="mono">{topCandidate.strategy_score.toFixed(2)}</div>
            </div>
            <div>
              <div className="muted-text">Risk</div>
              <div className={riskClass(topCandidate.risk_status)}>{topCandidate.risk_status}</div>
            </div>
            <div>
              <div className="muted-text">Model EV</div>
              <div className={`mono ${topCandidate.expected_value >= 0 ? "success-text" : "danger-text"}`}>
                ${topCandidate.expected_value.toFixed(2)}
              </div>
            </div>
          </div>
          <p className="muted-text">Legs: {renderLegs(topCandidate)}</p>
          <p className="muted-text">
            Feature ref: <span className="mono">{result?.feature_snapshot_ref}</span> | Options ref:{" "}
            <span className="mono">{result?.option_chain_snapshot_ref}</span>
          </p>
        </section>
      ) : null}

      {replay?.results.length ? (
        <section className="card">
          <h3 className="panel-title">Replay Results</h3>
          <div className="table-wrap">
            <table className="dense-table">
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Risk</th>
                  <th>Score</th>
                  <th>Replay Avg PnL</th>
                  <th>Scenarios</th>
                </tr>
              </thead>
              <tbody>
                {replay.results.map((item) => (
                  <tr key={`${item.strategy_type}-${item.risk_status}-${item.strategy_score}`}>
                    <td>{item.strategy_type}</td>
                    <td>{item.risk_status}</td>
                    <td className="mono">{item.strategy_score.toFixed(2)}</td>
                    <td className={`mono ${item.replay_avg_pnl >= 0 ? "success-text" : "danger-text"}`}>${item.replay_avg_pnl.toFixed(2)}</td>
                    <td className="mono">{item.scenario_pnls.map((pnl) => pnl.toFixed(0)).join(" / ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section className="card">
        <div className="sb-card-head">
          <h3 className="panel-title">Candidates</h3>
          {result?.rejected_candidates?.length ? (
            <button type="button" className="secondary-button" onClick={() => setShowRejected((value) => !value)}>
              {showRejected ? "Hide rejected" : `Show rejected (${result.rejected_candidates.length})`}
            </button>
          ) : null}
        </div>
        {!visibleCandidates.length ? (
          <p className="muted-text">Run Runtime Flow to generate ranked candidates. Save a candidate before paper trading.</p>
        ) : null}
        {visibleCandidates.length ? (
          <div className="table-wrap">
            <table className="dense-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Symbol</th>
                  <th>Direction</th>
                  <th>Strategy</th>
                  <th>DTE</th>
                  <th>Debit</th>
                  <th>Width</th>
                  <th>Strike Dist</th>
                  <th>Max Profit</th>
                  <th>Model POP</th>
                  <th>Model EV</th>
                  <th>Confidence</th>
                  <th>Edge</th>
                  <th>Risk</th>
                  <th>Rule Reasons</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {visibleCandidates.map((candidate, idx) => (
                  <tr
                    key={`${candidate.strategy_type}-${candidate.expiry}-${renderLegs(candidate)}`}
                    className={selectedCandidate === candidate ? "is-active" : ""}
                    onClick={() => {
                      setSelectedCandidate(candidate);
                      openCandidate(candidate);
                    }}
                  >
                    <td className="mono">{idx + 1}</td>
                    <td className="mono">{candidate.symbol}</td>
                    <td>{candidate.direction}</td>
                    <td>{candidate.strategy_type}</td>
                    <td className="mono">{candidate.dte}</td>
                    <td className="mono">${candidate.debit_or_credit.toFixed(2)}</td>
                    <td className="mono">{spreadWidth(candidate)?.toFixed(0) ?? "-"}</td>
                    <td className="mono">
                      {candidate.legs
                        .map((leg) => {
                          const dist = strikeDistancePct(Number(leg.strike), Number(result?.chain_diagnostics?.underlying_price));
                          return dist == null ? "-" : `${dist.toFixed(1)}%`;
                        })
                        .join(" / ")}
                    </td>
                    <td className="mono">${candidate.max_loss.toFixed(2)}</td>
                    <td className="mono">${candidate.max_profit.toFixed(2)}</td>
                    <td className="mono">{(candidate.probability_profit * 100).toFixed(1)}%</td>
                    <td className={`mono ${candidate.expected_value >= 0 ? "success-text" : "danger-text"}`}>
                      ${candidate.expected_value.toFixed(2)}
                    </td>
                    <td className="mono">{candidate.strategy_score.toFixed(1)}</td>
                    <td className="mono">${candidate.expected_value.toFixed(2)}</td>
                    <td>
                      <span className={riskClass(candidate.risk_status)}>{candidate.risk_status}</span>
                    </td>
                    <td>
                      {candidate.rule_reasons.slice(0, 2).map((reason) => (
                        <div key={`${reason.rule_id}-${reason.message}`} className="sb-reason">
                          {reason.message}
                        </div>
                      ))}
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <div className="inline-form">
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={saveLoading || !isActionableCandidate(candidate.risk_status)}
                          onClick={() => void saveSelectedDecision(candidate)}
                        >
                          Save
                        </button>
                        <button type="button" className="ghost-button" onClick={runReplayNow}>Replay</button>
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={!savedDecision || !isActionableCandidate(candidate.risk_status)}
                          onClick={runPaperNow}
                        >
                          Paper
                        </button>
                        <button type="button" className="ghost-button" onClick={() => void saveSelectedDecision(candidate, true)}>
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      {drawerOpen && selectedCandidate ? (
        <div className="drawer-backdrop" role="dialog" aria-modal="true">
          <aside className="trade-drawer panel">
            <div className="drawer-header">
              <div>
                <h3 className="panel-title">Recommendation Card</h3>
                <p className="muted-text">
                  {selectedCandidate.symbol} - {selectedCandidate.strategy_type} - {selectedCandidate.direction}
                </p>
              </div>
              <button type="button" className="ghost-button" onClick={() => setDrawerOpen(false)}>
                Close
              </button>
            </div>
            <div className="drawer-content">
              <section className="panel-sub">
                <h3>Payoff</h3>
                <ul className="dense-list">
                  <li>
                    <span>Max Profit</span>
                    <span className="mono">${selectedCandidate.max_profit.toFixed(2)}</span>
                  </li>
                  <li>
                    <span>Max Loss</span>
                    <span className="mono">${selectedCandidate.max_loss.toFixed(2)}</span>
                  </li>
                  <li>
                    <span>Breakeven</span>
                    <span className="mono">{selectedCandidate.breakeven.toFixed(2)}</span>
                  </li>
                  <li>
                    <span>Model POP</span>
                    <span className="mono">{(selectedCandidate.probability_profit * 100).toFixed(1)}%</span>
                  </li>
                </ul>
              </section>
              <section className="panel-sub">
                <h3>Risk and Rule Reasons</h3>
                <div className={riskClass(selectedCandidate.risk_status)}>{selectedCandidate.risk_status}</div>
                <div style={{ marginTop: 8 }}>
                  {selectedCandidate.rule_reasons.map((reason) => (
                    <div key={`${reason.rule_id}-${reason.message}`} className="sb-reason">
                      <span className="mono">{reason.rule_id}</span> ({reason.severity}): {reason.message}
                    </div>
                  ))}
                </div>
              </section>
              {selectedCandidate.risk_status === "override_required" ? (
                <section className="panel-sub">
                  <h3>Override Drawer</h3>
                  <p className="muted-text">Record why this setup is manually allowed despite warnings.</p>
                  <input
                    value={overrideReason}
                    onChange={(event) => setOverrideReason(event.target.value)}
                    className="feed-input"
                    placeholder="Override reason"
                  />
                  <textarea
                    value={overrideNote}
                    onChange={(event) => setOverrideNote(event.target.value)}
                    className="feed-input"
                    style={{ marginTop: 8, minHeight: 90 }}
                    placeholder="Execution guardrails and rationale"
                  />
                  <div className="sb-actions" style={{ marginTop: 8 }}>
                    <button type="button" className="primary-button" disabled={!overrideReason.trim()}>
                      Submit Override Intent
                    </button>
                    <span className="muted-text">{overrideReason.trim() ? "Ready to submit" : "Reason required"}</span>
                  </div>
                </section>
              ) : null}
              <div className="drawer-actions">
                <button type="button" className="primary-button" disabled={saveLoading} onClick={() => void saveSelectedDecision(selectedCandidate)}>
                  {saveLoading ? "Saving..." : "Save Decision"}
                </button>
                <button type="button" className="secondary-button" onClick={runReplayNow}>Run Replay</button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={!savedDecision || selectedCandidate.risk_status === "reject"}
                  onClick={runPaperNow}
                >
                  Run Paper
                </button>
                <button type="button" className="ghost-button" onClick={() => void saveSelectedDecision(selectedCandidate, true)}>
                  Reject
                </button>
              </div>
            </div>
          </aside>
        </div>
      ) : null}
    </main>
  );
}
