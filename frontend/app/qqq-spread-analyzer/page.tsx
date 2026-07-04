"use client";

import { useMemo } from "react";

import BacktestPanel from "@/components/qqq-spread/BacktestPanel";
import DailyIndicatorsPanel from "@/components/qqq-spread/DailyIndicatorsPanel";
import DiagnosticsPanel from "@/components/qqq-spread/DiagnosticsPanel";
import ExpiryRankingPanel from "@/components/qqq-spread/ExpiryRankingPanel";
import IntradayPanel from "@/components/qqq-spread/IntradayPanel";
import KeyLevelsPanel from "@/components/qqq-spread/KeyLevelsPanel";
import MarketRegimeSummary from "@/components/qqq-spread/MarketRegimeSummary";
import NewsIntelligenceCard from "@/components/qqq-spread/news/NewsIntelligenceCard";
import TradeDecisionEngine from "@/components/qqq-spread/TradeDecisionEngine";
import OptionChainPanel from "@/components/qqq-spread/OptionChainPanel";
import RiskNotesPanel from "@/components/qqq-spread/RiskNotesPanel";
import SpreadCandidatesTable from "@/components/qqq-spread/SpreadCandidatesTable";
import SummaryBar from "@/components/qqq-spread/SummaryBar";
import { useSpreadAnalysisPage } from "@/hooks/useSpreadAnalysisPage";
import { computeMarketRegime } from "@/lib/marketRegime";
import { pickSuggestedSpread } from "@/lib/tradeDecision";
import { getQqqSpreadAnalysis, getQqqSpreadRunStatus, runQqqSpreadAnalysis } from "@/lib/api";
import "@/styles/qqq-spread-analyzer.css";

const SYMBOL = "QQQ";

export default function QqqSpreadAnalyzerPage() {
  const api = useMemo(
    () => ({
      getAnalysis: getQqqSpreadAnalysis,
      runAnalysis: runQqqSpreadAnalysis,
      getRunStatus: getQqqSpreadRunStatus,
    }),
    [],
  );

  const {
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
  } = useSpreadAnalysisPage(SYMBOL, api);

  const regime = useMemo(() => (data ? computeMarketRegime(data) : null), [data]);

  const displayedSpread = useMemo(() => {
    if (!data) return null;
    const filter = regime?.strategyFilter;
    const decision =
      filter === "Bull Call Spread" || filter === "Bear Put Spread" ? filter : "WAIT";
    return pickSuggestedSpread(data, decision);
  }, [data, regime]);

  return (
    <div className="container page-stack qqq-page">
      <div className="panel-header">
        <h1 className="panel-title">QQQ Spread Analyzer</h1>
        <p className="muted-text">
          Research only. No live order placement. Refresh reloads the saved snapshot; Run analysis fetches new IB data.
        </p>
      </div>

      {error && <div className="banner banner-danger">{error}</div>}
      {runError && <div className="banner banner-danger">{runError}</div>}

      {runBusy && !data && (
        <section className="panel">
          <p className="qqq-empty">Running analysis… this usually takes 1–2 minutes.</p>
        </section>
      )}

      {empty && !data && !error && !runBusy && (
        <section className="panel">
          <p className="qqq-empty">No analysis snapshot yet. Run the CLI or click Run analysis to generate one.</p>
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
          <TradeDecisionEngine data={data} onRefresh={() => void load()} busy={busy || runBusy} />
        </>
      )}

      <NewsIntelligenceCard symbol={SYMBOL} />

      {data && (
        <>
          <MarketRegimeSummary data={data} />
          <div className="qqq-grid-2">
            <DailyIndicatorsPanel data={data} />
            <IntradayPanel data={data} />
          </div>
          <KeyLevelsPanel
            supportLevels={data.support_levels}
            resistanceLevels={data.resistance_levels}
            optionExpiry={displayedSpread?.expiry}
          />
          <ExpiryRankingPanel expirySearch={(data as unknown as Record<string, unknown>).expiry_search as Parameters<typeof ExpiryRankingPanel>[0]["expirySearch"]} />
          <SpreadCandidatesTable data={data} strategyFilter={regime?.strategyFilter} />
          <RiskNotesPanel data={data} />
          <BacktestPanel data={data} />
          <OptionChainPanel data={data} />
          <DiagnosticsPanel diagnostics={data.diagnostics} runError={runError} />
        </>
      )}
    </div>
  );
}
