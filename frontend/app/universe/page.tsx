"use client";

import { FormEvent, useEffect, useState } from "react";

import {
  activateUniverse,
  getUniverseActive,
  getUniverseVersions,
  uploadUniverse,
} from "@/lib/api";
import type { ActiveUniverse, UniverseUploadResponse, UniverseVersionRow } from "@/types";

export default function UniversePage() {
  const [active, setActive] = useState<ActiveUniverse | null>(null);
  const [versions, setVersions] = useState<UniverseVersionRow[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [selectedUniverseId, setSelectedUniverseId] = useState("");
  const [uploadResult, setUploadResult] = useState<UniverseUploadResponse | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refresh = async () => {
    setError("");
    try {
      const [activeUniverse, allVersions] = await Promise.all([
        getUniverseActive().catch(() => null),
        getUniverseVersions(),
      ]);
      setActive(activeUniverse);
      setVersions(allVersions);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load universe data");
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const onUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setMessage("");
    const form = event.currentTarget;
    const input = form.elements.namedItem("file") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) {
      setError("Pick a universe JSON file first.");
      return;
    }
    try {
      const result = await uploadUniverse(file);
      setUploadResult(result);
      setSelectedVersionId(result.universe_version_id);
      setSelectedUniverseId(result.universe_id);
      setMessage(`Upload ${result.upload_status.toUpperCase()}: ${result.universe_version_id}`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    }
  };

  const onActivate = async () => {
    setError("");
    setMessage("");
    if (!selectedVersionId || !selectedUniverseId) {
      setError("Select or upload a universe version before activation.");
      return;
    }
    try {
      await activateUniverse(selectedVersionId, selectedUniverseId, "human_trader");
      setMessage(`Activated universe version ${selectedVersionId}`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Activation failed");
    }
  };

  return (
    <main className="grid" style={{ gap: 16 }}>
      <section className="card">
        <h2 className="title-blue" style={{ marginTop: 0 }}>
          Universe
        </h2>
        <p style={{ marginTop: 0 }}>
          Upload a ticker universe JSON, validate via IBKR secdef, then activate the version for monitoring cycles.
        </p>
        <form onSubmit={onUpload} className="grid" style={{ gap: 10 }}>
          <input name="file" type="file" accept="application/json" />
          <button type="submit">Upload Universe JSON</button>
        </form>
        {message ? <p className="text-green">{message}</p> : null}
        {error ? <p className="text-red">{error}</p> : null}
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Active Universe</h3>
        {active ? (
          <div className="grid grid-3">
            <div className="card">
              <div className="subtle">Universe ID</div>
              <div className="mono text-white">{active.universe_id}</div>
            </div>
            <div className="card">
              <div className="subtle">Version</div>
              <div className="mono text-white">{active.universe_version_id}</div>
            </div>
            <div className="card">
              <div className="subtle">Tickers</div>
              <div className="mono text-white">{active.tickers.length}</div>
            </div>
          </div>
        ) : (
          <p>No active universe.</p>
        )}
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Uploaded Versions</h3>
        {versions.length === 0 ? (
          <p>No uploaded versions yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Select</th>
                <th>Universe</th>
                <th>Version</th>
                <th>Status</th>
                <th>Tickers</th>
                <th>Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.universe_version_id}>
                  <td>
                    <input
                      type="radio"
                      name="version"
                      checked={selectedVersionId === v.universe_version_id}
                      onChange={() => {
                        setSelectedVersionId(v.universe_version_id);
                        setSelectedUniverseId(v.universe_id);
                      }}
                    />
                  </td>
                  <td>{v.universe_id}</td>
                  <td className="mono">{v.universe_version_id}</td>
                  <td>
                    <span className={`badge ${v.upload_status === "validated" ? "badge-green" : "badge-red"}`}>
                      {v.upload_status}
                    </span>
                  </td>
                  <td>{v.tickers_requested.length}</td>
                  <td>{new Date(v.uploaded_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div style={{ marginTop: 12 }}>
          <button onClick={onActivate} type="button">
            Activate Selected Version
          </button>
        </div>
      </section>

      {uploadResult ? (
        <section className="card">
          <h3 style={{ marginTop: 0 }}>Last Upload Validation</h3>
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Status</th>
                <th>Conid</th>
              </tr>
            </thead>
            <tbody>
              {uploadResult.validation_results.map((row) => (
                <tr key={`${uploadResult.universe_version_id}-${row.ticker}`}>
                  <td>{row.ticker}</td>
                  <td>
                    <span
                      className={`badge ${
                        row.status === "validated"
                          ? "badge-green"
                          : row.status === "ambiguous"
                            ? "badge-blue"
                            : "badge-red"
                      }`}
                    >
                      {row.status}
                    </span>
                  </td>
                  <td className="mono">{row.ibkr_conid ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </main>
  );
}
