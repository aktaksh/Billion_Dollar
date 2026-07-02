"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { QqqSpreadAnalysis, QqqSpreadRunOut, QqqSpreadRunStatusOut } from "@/types/qqqSpreadAnalyzer";

const POLL_MS = 60_000;
const JOB_POLL_MS = 3_000;
const STALE_MINUTES = 15;

export type SpreadAnalysisApi = {
  getAnalysis: (symbol: string) => Promise<QqqSpreadAnalysis | null>;
  runAnalysis: (symbol: string, noCache?: boolean) => Promise<QqqSpreadRunOut>;
  getRunStatus: (jobId: string) => Promise<QqqSpreadRunStatusOut>;
};

export function formatSpreadTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function analysisAgeMinutes(timestamp: string): number | null {
  try {
    const ms = Date.now() - new Date(timestamp).getTime();
    if (!Number.isFinite(ms)) return null;
    return Math.max(0, Math.floor(ms / 60_000));
  } catch {
    return null;
  }
}

export function isAnalysisStale(timestamp: string, staleMinutes = STALE_MINUTES): boolean {
  const age = analysisAgeMinutes(timestamp);
  return age !== null && age >= staleMinutes;
}

export function useSpreadAnalysisPage(symbol: string, api: SpreadAnalysisApi) {
  const sym = symbol.trim().toUpperCase();
  const [data, setData] = useState<QqqSpreadAnalysis | null>(null);
  const [error, setError] = useState("");
  const [empty, setEmpty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [runBusy, setRunBusy] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState("");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const baselineTsRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (!sym) return;
    // #region agent log
    fetch("http://127.0.0.1:7577/ingest/6544d4bf-d7b7-42e2-bdeb-9c98609756e6", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "68ab8c" },
      body: JSON.stringify({
        sessionId: "68ab8c",
        hypothesisId: "A",
        location: "useSpreadAnalysisPage.ts:load:start",
        message: "load started",
        data: { sym, busyBefore: busy, runBusy },
        timestamp: Date.now(),
      }),
    }).catch(() => {});
    // #endregion
    setBusy(true);
    try {
      const result = await api.getAnalysis(sym);
      // #region agent log
      fetch("http://127.0.0.1:7577/ingest/6544d4bf-d7b7-42e2-bdeb-9c98609756e6", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "68ab8c" },
        body: JSON.stringify({
          sessionId: "68ab8c",
          hypothesisId: "A,D",
          location: "useSpreadAnalysisPage.ts:load:result",
          message: "load API returned",
          data: {
            sym,
            hasResult: Boolean(result),
            resultSymbol: result?.symbol ?? null,
            resultTimestamp: result?.timestamp ?? null,
            symbolMatch: result ? result.symbol.trim().toUpperCase() === sym : false,
            ageMin: result ? analysisAgeMinutes(result.timestamp) : null,
          },
          timestamp: Date.now(),
        }),
      }).catch(() => {});
      // #endregion
      if (!result || result.symbol.trim().toUpperCase() !== sym) {
        setData(null);
        setEmpty(true);
        setError("");
      } else {
        setData(result);
        setEmpty(false);
        setError("");
      }
      setLastFetchedAt(new Date().toISOString());
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Failed to load analysis";
      // #region agent log
      fetch("http://127.0.0.1:7577/ingest/6544d4bf-d7b7-42e2-bdeb-9c98609756e6", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "68ab8c" },
        body: JSON.stringify({
          sessionId: "68ab8c",
          hypothesisId: "C",
          location: "useSpreadAnalysisPage.ts:load:error",
          message: "load failed",
          data: { sym, errMsg },
          timestamp: Date.now(),
        }),
      }).catch(() => {});
      // #endregion
      setError(errMsg);
    } finally {
      setBusy(false);
      // #region agent log
      fetch("http://127.0.0.1:7577/ingest/6544d4bf-d7b7-42e2-bdeb-9c98609756e6", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "68ab8c" },
        body: JSON.stringify({
          sessionId: "68ab8c",
          hypothesisId: "B",
          location: "useSpreadAnalysisPage.ts:load:finally",
          message: "load finished",
          data: { sym },
          timestamp: Date.now(),
        }),
      }).catch(() => {});
      // #endregion
    }
  }, [api, sym, busy, runBusy]);

  const pollJob = useCallback(
    async (jobId: string) => {
      try {
        const status = await api.getRunStatus(jobId);
        if (status.status === "failed") {
          setRunBusy(false);
          setRunError(status.error ?? "Analysis job failed");
          setActiveJobId(null);
          return;
        }
        if (status.status === "done") {
          await load();
          setRunBusy(false);
          setRunError(null);
          setActiveJobId(null);
          return;
        }
        const latest = await api.getAnalysis(sym);
        if (
          latest &&
          latest.symbol.trim().toUpperCase() === sym &&
          (!baselineTsRef.current || latest.timestamp !== baselineTsRef.current)
        ) {
          setData(latest);
          setEmpty(false);
          setRunBusy(false);
          setRunError(null);
          setActiveJobId(null);
          setLastFetchedAt(new Date().toISOString());
        }
      } catch (err) {
        setRunError(err instanceof Error ? err.message : "Failed to poll job status");
      }
    },
    [api, load, sym],
  );

  const handleRun = useCallback(async () => {
    if (!sym) return;
    setRunBusy(true);
    setRunError(null);
    baselineTsRef.current = data?.symbol === sym ? data.timestamp : null;
    try {
      const out = await api.runAnalysis(sym, false);
      if (!out.job_id) {
        setRunBusy(false);
        setRunError(out.message || "Analysis did not return a job id");
        return;
      }
      setActiveJobId(out.job_id);
      if (out.status === "done") {
        await load();
        setRunBusy(false);
        setActiveJobId(null);
      }
    } catch (err) {
      setRunBusy(false);
      setActiveJobId(null);
      setRunError(err instanceof Error ? err.message : "Failed to start analysis");
    }
  }, [api, data, load, sym]);

  useEffect(() => {
    setData(null);
    setEmpty(false);
    setError("");
    setRunError(null);
    void load();
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [load, sym]);

  useEffect(() => {
    if (!runBusy || !activeJobId) return undefined;
    void pollJob(activeJobId);
    const timer = setInterval(() => void pollJob(activeJobId), JOB_POLL_MS);
    return () => clearInterval(timer);
  }, [activeJobId, pollJob, runBusy]);

  const lastUpdatedLabel = data
    ? formatSpreadTimestamp(data.timestamp)
    : lastFetchedAt
      ? formatSpreadTimestamp(lastFetchedAt)
      : "never";

  const dataIsStale = data ? isAnalysisStale(data.timestamp) : false;
  const dataAgeMin = data ? analysisAgeMinutes(data.timestamp) : null;

  return {
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
  };
}
