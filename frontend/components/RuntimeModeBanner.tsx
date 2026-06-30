"use client";

import { useCallback, useEffect, useState } from "react";

import { getRuntimeMode } from "@/lib/api";
import type { RuntimeModeOut } from "@/types";

export default function RuntimeModeBanner() {
  const [flags, setFlags] = useState<RuntimeModeOut | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await getRuntimeMode("QQQ");
      setFlags(data);
    } catch {
      setFlags(null);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 30_000);
    return () => clearInterval(timer);
  }, [load]);

  if (!flags) return null;

  if (flags.runtime_mode === "testing") {
    return (
      <div className="container">
        <div className="banner banner-warning">
          TESTING MODE — fixture or stale broker cache allowed. Strategy Builder may use non-live data.
        </div>
      </div>
    );
  }

  if (!flags.is_production_valid_chain) {
    if (flags.chain_origin === "seeded_fixture") {
      return (
        <div className="container">
          <div className="banner banner-danger">
            Production mode: testing fixture still loaded — connect broker and refresh QQQ Options Chain for live data.
          </div>
        </div>
      );
    }
    return null;
  }

  if (flags.scanner_status === "fresh") {
    return (
      <div className="container">
        <div className="banner banner-success">
          Production mode — live broker chain data ({flags.chain_origin}).
        </div>
      </div>
    );
  }

  return null;
}
