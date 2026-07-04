"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import TradeDetailsDialog from "@/components/paper-trading/TradeDetailsDialog";
import { getPaperTrade } from "@/lib/paperTradeApi";
import type { PaperTradeDetail } from "@/types/paperTrading";
import "@/styles/paper-trading.css";

export default function PaperTradeDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [trade, setTrade] = useState<PaperTradeDetail | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setTrade(await getPaperTrade(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load trade");
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="container page-stack pt-page">
      <div className="panel-header">
        <Link href="/paper-trading-lab" className="qqq-btn">
          ← Back to lab
        </Link>
      </div>
      {error && <div className="banner banner-danger">{error}</div>}
      {!trade && !error && <p className="qqq-empty">Loading trade…</p>}
      {trade && <TradeDetailsDialog trade={trade} onUpdated={setTrade} />}
    </div>
  );
}
