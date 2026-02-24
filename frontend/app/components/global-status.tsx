"use client";

import { useEffect, useMemo, useState } from "react";

import { getReconcileMismatches, getRiskStatus } from "@/lib/api";
import type { ReconcileMismatch, RiskStatus } from "@/types";

export default function GlobalStatus() {
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [mismatches, setMismatches] = useState<ReconcileMismatch[]>([]);

  const refresh = async () => {
    try {
      const [riskRes, mismatchRes] = await Promise.all([
        getRiskStatus(),
        getReconcileMismatches(),
      ]);
      setRisk(riskRes);
      setMismatches(mismatchRes);
    } catch {
      // Keep UI resilient even if status calls fail.
    }
  };

  useEffect(() => {
    void refresh();
    const id = setInterval(() => {
      void refresh();
    }, 15_000);
    return () => clearInterval(id);
  }, []);

  const blocking = useMemo(() => mismatches.some((m) => m.blocking), [mismatches]);

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="grid grid-3">
        <div>
          <div className="subtle">Trading Mode</div>
          <div className="mono text-white">{risk?.trading_mode ?? "unknown"}</div>
        </div>
        <div>
          <div className="subtle">Global Reconcile</div>
          <div className={blocking ? "mono text-red" : "mono text-green"}>
            {blocking ? "BLOCKING" : "CLEAN"}
          </div>
        </div>
        <div>
          <div className="subtle">New Entries</div>
          <div className={risk?.can_open_new_entries ? "mono text-green" : "mono text-red"}>
            {risk?.can_open_new_entries ? "ALLOWED" : "BLOCKED"}
          </div>
        </div>
      </div>
      {blocking ? (
        <p className="text-red" style={{ marginBottom: 0 }}>
          Reconcile mismatch detected. No-new-entries mode should be enforced until cleared.
        </p>
      ) : null}
    </div>
  );
}
