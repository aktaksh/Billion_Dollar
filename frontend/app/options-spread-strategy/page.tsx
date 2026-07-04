"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import BacktestPanel from "@/components/qqq-spread/BacktestPanel";
import DailyIndicatorsPanel from "@/components/qqq-spread/DailyIndicatorsPanel";
import DiagnosticsPanel from "@/components/qqq-spread/DiagnosticsPanel";
import ExpiryRankingPanel from "@/components/qqq-spread/ExpiryRankingPanel";
import IntradayPanel from "@/components/qqq-spread/IntradayPanel";
import KeyLevelsPanel from "@/components/qqq-spread/KeyLevelsPanel";
import { pickSuggestedSpread } from "@/lib/tradeDecision";
import MarketBiasPanel from "@/components/qqq-spread/MarketBiasPanel";
import OptionChainPanel from "@/components/qqq-spread/OptionChainPanel";
import RiskNotesPanel from "@/components/qqq-spread/RiskNotesPanel";
import SpreadCandidatesTable from "@/components/qqq-spread/SpreadCandidatesTable";
import SummaryBar from "@/components/qqq-spread/SummaryBar";
import SymbolSelector, { persistSymbol, readPersistedSymbol } from "@/components/qqq-spread/SymbolSelector";
import { useSpreadAnalysisPage } from "@/hooks/useSpreadAnalysisPage";
import {
  getOptionsSpreadStrategyAnalysis,
  getOptionsSpreadStrategyRunStatus,
  runOptionsSpreadStrategyAnalysis,
} from "@/lib/api";
import "@/styles/qqq-spread-analyzer.css";

function OptionsSpreadStrategyContent() {
  const searchParams = useSearchParams();
  const urlSymbol = searchParams.get("symbol")?.trim().toUpperCase();

  // Initialize with URL param or fallback "SPY" for SSR consistency.
  // localStorage is read in useEffect to avoid hydration mismatch.
  const [symbol, setSymbol] = useState(urlSymbol || "SPY");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (hydrated) return;
    setHydrated(true);
    // On first client mount, restore persisted symbol if no URL param
    if (!urlSymbol) {
      const persisted = readPersistedSymbol();
      if (persisted && persisted !== symbol) {
        setSymbol(persisted);
      }
    } else {
      persistSymbol(urlSymbol);
    }
  }, [hydrated, urlSymbol, symbol]);

  useEffect(() => {
    if (!hydrated) return;
    const fromUrl = searchParams.get("symbol")?.trim().toUpperCase();
    if (fromUrl && fromUrl !== symbol) {
      setSymbol(fromUrl);
      persistSymbol(fromUrl);
    }
  }, [searchParams, symbol, hydrated]);

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

  // Persist symbol whenever analysis loads successfully
  useEffect(() => {
    if (data && symbol) {
      persistSymbol(symbol);
    }
  }, [data, symbol]);

  const displayedSpread = useMemo(
    () => (data ? pickSuggestedSpread(data) : null),
    [data],
  );

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
            persistSymbol(symbol);
            const url = new URL(window.location.href);
            url.searchParams.set("symbol", symbol);
            window.history.replaceState({}, "", url.toString());
            void load();
          }}
        >
          <SymbolSelector
            value={symbol}
            onChange={setSymbol}
            onSubmit={() => {
              persistSymbol(symbol);
              const url = new URL(window.location.href);
              url.searchParams.set("symbol", symbol);
              window.history.replaceState({}, "", url.toString());
              void load();
            }}
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
          <KeyLevelsPanel
            supportLevels={data.support_levels}
            resistanceLevels={data.resistance_levels}
            optionExpiry={displayedSpread?.expiry}
          />
          <ExpiryRankingPanel expirySearch={(data as unknown as Record<string, unknown>).expiry_search as Parameters<typeof ExpiryRankingPanel>[0]["expirySearch"]} />
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

export default function OptionsSpreadStrategyPage() {
  return (
    <Suspense fallback={<div className="container page-stack qqq-page"><p className="qqq-empty">Loading…</p></div>}>
      <OptionsSpreadStrategyContent />
    </Suspense>
  );
}
