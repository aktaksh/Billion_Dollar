"use client";

import { useState, useRef, useEffect } from "react";
import { generateAiReport, downloadAiReportUrl } from "@/lib/aiReportApi";

export default function AiReportButton() {
  const [loading, setLoading] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [done, setDone] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    }
    if (showMenu) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showMenu]);

  async function handleGenerate() {
    setLoading(true);
    setDone(false);
    try {
      await generateAiReport();
      setDone(true);
      setShowMenu(true);
    } catch (err) {
      console.error(err);
      alert("Failed to generate AI Report. Check backend logs.");
    } finally {
      setLoading(false);
    }
  }

  function triggerDownload(format: "json" | "md") {
    const url = downloadAiReportUrl(format);
    const a = document.createElement("a");
    a.href = url;
    a.download = `billion_dollar_ai_report_latest.${format}`;
    a.click();
    setShowMenu(false);
  }

  return (
    <div className="ai-report-wrapper" ref={menuRef}>
      <button
        className="ai-report-btn"
        onClick={handleGenerate}
        disabled={loading}
        title="Generate consolidated AI report"
      >
        {loading ? (
          <span className="ai-report-spinner" />
        ) : (
          <span className="ai-report-icon">📋</span>
        )}
        <span className="ai-report-label">AI Report</span>
      </button>

      {showMenu && done && (
        <div className="ai-report-menu">
          <button onClick={() => triggerDownload("json")}>Download JSON</button>
          <button onClick={() => triggerDownload("md")}>Download Markdown</button>
        </div>
      )}
    </div>
  );
}
