import Link from "next/link";

import { getWatchlist } from "@/lib/api";
import type { WatchlistOpportunity } from "@/types";

export default async function IdeasPage() {
  let ideas: WatchlistOpportunity[] = [];
  let errorMessage = "";

  try {
    ideas = await getWatchlist();
  } catch (error) {
    errorMessage = error instanceof Error ? error.message : "Failed to load watchlist";
  }

  return (
    <main className="grid" style={{ gap: 16 }}>
      <section className="card">
        <h2 className="title-blue" style={{ marginTop: 0 }}>
          Watchlist
        </h2>
        <p style={{ marginTop: 0 }}>
          Actionable opportunities in the active universe, with state and data-health gating.
        </p>
        {errorMessage ? (
          <p className="text-red">Unable to load watchlist: {errorMessage}</p>
        ) : ideas.length === 0 ? (
          <p>No watchlist items yet. Upload and activate a universe first.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>State</th>
                <th>Data Health</th>
                <th>Confidence</th>
                <th>Regime</th>
                <th>Post-Cost Edge</th>
                <th>Entry</th>
                <th>Invalidation</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {ideas.map((idea) => (
                <tr key={idea.ticker}>
                  <td className="text-white">
                    <Link href={`/tickers/${encodeURIComponent(idea.ticker)}`}>{idea.ticker}</Link>
                  </td>
                  <td>{idea.state}</td>
                  <td>
                    <span
                      className={`badge ${
                        idea.data_health === "OK"
                          ? "badge-green"
                          : idea.data_health === "Blocked"
                            ? "badge-red"
                            : "badge-blue"
                      }`}
                    >
                      {idea.data_health}
                    </span>
                  </td>
                  <td className={idea.confidence_total >= 70 ? "text-green" : "text-red"}>
                    {idea.confidence_total.toFixed(1)}
                  </td>
                  <td>{idea.regime_label}</td>
                  <td className={idea.post_cost_edge_usd > 0 ? "text-green" : "text-red"}>
                    ${idea.post_cost_edge_usd.toFixed(2)}
                  </td>
                  <td>{idea.entry_zone}</td>
                  <td>{idea.invalidation}</td>
                  <td>{idea.next_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}


