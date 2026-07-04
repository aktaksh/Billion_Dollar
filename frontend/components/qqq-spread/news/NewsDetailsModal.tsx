"use client";

import NewsEventsTable from "@/components/qqq-spread/news/NewsEventsTable";
import type { NewsQuickRefreshResponse } from "@/types/newsIntelligence";

type Props = {
  data: NewsQuickRefreshResponse;
  onClose: () => void;
};

function QueryRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="ni-query-row">
      <span className="ni-query-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function NewsDetailsModal({ data, onClose }: Props) {
  return (
    <div className="pt-modal-backdrop" role="presentation" onClick={onClose}>
      <div className="pt-modal ni-details-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="panel-header">
          <h2 className="panel-title">News Intelligence — Details</h2>
          <button type="button" className="qqq-btn" onClick={onClose}>
            Close
          </button>
        </div>

        <section className="ni-modal-section">
          <h3 className="ni-section-title">Query Summary</h3>
          <div className="ni-query-grid">
            <QueryRow label="Planned Calls" value={data.plannedCalls ?? "—"} />
            <QueryRow label="Executed Calls" value={data.executedCalls ?? "—"} />
            <QueryRow label="Skipped Calls" value={data.skippedCalls ?? "—"} />
            <QueryRow label="Total Fetched" value={data.totalFetched ?? "—"} />
            <QueryRow label="Total Saved" value={data.totalSaved ?? "—"} />
            <QueryRow label="Duplicates Removed" value={data.duplicatesRemoved ?? "—"} />
            <QueryRow label="Low Relevance Ignored" value={data.lowRelevanceIgnored ?? "—"} />
            <QueryRow label="Events Created" value={data.eventsCreated ?? data.totalSaved ?? "—"} />
          </div>
        </section>

        <section className="ni-modal-section">
          <h3 className="ni-section-title">Top Events</h3>
          <NewsEventsTable
            events={data.topEvents}
            emptyMessage="No new high-impact news found."
          />
        </section>

        {data.providerErrors.length > 0 && (
          <section className="ni-modal-section">
            <h3 className="ni-section-title">Provider Errors</h3>
            <ul className="qqq-muted-list ni-error-list">
              {data.providerErrors.map((err) => (
                <li key={err}>{err}</li>
              ))}
            </ul>
          </section>
        )}

        {data.comments.length > 0 && (
          <section className="ni-modal-section">
            <h3 className="ni-section-title">Comments</h3>
            <ul className="qqq-muted-list">
              {data.comments.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
