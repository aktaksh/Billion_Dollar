"use client";

import { useMemo, useState } from "react";

import BacktestPanel from "@/components/qqq-spread/BacktestPanel";
import DailyIndicatorsPanel from "@/components/qqq-spread/DailyIndicatorsPanel";
import DiagnosticsPanel from "@/components/qqq-spread/DiagnosticsPanel";
import IntradayPanel from "@/components/qqq-spread/IntradayPanel";
import KeyLevelsPanel from "@/components/qqq-spread/KeyLevelsPanel";
import MarketBiasPanel from "@/components/qqq-spread/MarketBiasPanel";
import OptionChainPanel from "@/components/qqq-spread/OptionChainPanel";
import RiskNotesPanel from "@/components/qqq-spread/RiskNotesPanel";
import SpreadCandidatesTable from "@/components/qqq-spread/SpreadCandidatesTable";
import SummaryBar from "@/components/qqq-spread/SummaryBar";
import { useSpreadAnalysisPage } from "@/hooks/useSpreadAnalysisPage";
import {
  getOptionsSpreadStrategyAnalysis,
  getOptionsSpreadStrategyRunStatus,
  runOptionsSpreadStrategyAnalysis,
} from "@/lib/api";
import "@/styles/qqq-spread-analyzer.css";

export default function OptionsSpreadStrategyPage() {
  const [symbol, setSymbol] = useState("SPY");

  const api = useMemo(
    () => ({
      getAnalysis: getOptionsSpreadStrategyAnalysis,
      runAnalysis: runOptionsSpreadStrategyAnalysis,
      getRunStatus: getOptionsSpreadStrategyRunStatus,
    }),
    [],
  );

  const {
    sym,
    data,
    error,
    empty,
    busy,
    runBusy,
    runError,
    lastUpdatedLabel,
    dataIsStale,
    dataAgeMin,
    load,
    handleRun,
  } = useSpreadAnalysisPage(symbol, api);

  return (
    <div className="container page-stack qqq-page">
      <div className="panel-header">
        <h1 className="panel-title">Options Spread Strategy</h1>
        <p className="muted-text">
          Full spread analysis for any ticker. Research only — no orders. Refresh reloads the saved snapshot; Run analysis
          fetches new IB data.
        </p>
        <form
          className="inline-form"
          style={{ marginTop: "0.5rem" }}
          onSubmit={(event) => {
            event.preventDefault();
            void load();
          }}
        >
          <input
            className="feed-input"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="Symbol"
            disabled={runBusy}
          />
        </form>
      </div>

      {error && <div className="banner banner-danger">{error}</div>}
      {runError && <div className="banner banner-danger">{runError}</div>}

      {runBusy && !data && sym && (
        <section className="panel">
          <p className="qqq-empty">Running analysis for {sym}… this usually takes 1–2 minutes.</p>
        </section>
      )}

      {empty && !data && !error && sym && !runBusy && (
        <section className="panel">
          <p className="qqq-empty">No analysis for {sym} yet. Click Run analysis (~1–2 min).</p>
          <div className="qqq-actions" style={{ marginTop: "0.75rem" }}>
            <button type="button" className="qqq-btn qqq-btn-primary" onClick={() => void handleRun()} disabled={runBusy}>
              Run analysis
            </button>
          </div>
        </section>
      )}

      {data && (
        <>
          <SummaryBar
            data={data}
            lastUpdatedLabel={lastUpdatedLabel}
            onRefresh={() => void load()}
            onRun={() => void handleRun()}
            busy={busy}
            runBusy={runBusy}
            dataIsStale={dataIsStale}
            dataAgeMin={dataAgeMin}
          />
          <MarketBiasPanel data={data} />
          <div className="qqq-grid-2">
            <DailyIndicatorsPanel data={data} />
            <IntradayPanel data={data} />
          </div>
          <KeyLevelsPanel supportLevels={data.support_levels} resistanceLevels={data.resistance_levels} />
          <SpreadCandidatesTable data={data} />
          <RiskNotesPanel data={data} />
          <BacktestPanel data={data} />
          <OptionChainPanel data={data} />
          <DiagnosticsPanel diagnostics={data.diagnostics} runError={runError} />
        </>
      )}
    </div>
  );
}
