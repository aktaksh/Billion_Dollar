"use client";

import { useState } from "react";

type Props = {
  left: React.ReactNode;
  main: React.ReactNode;
  right: React.ReactNode;
  banners?: React.ReactNode;
};

export default function AppShell({ left, main, right, banners }: Props) {
  const [rightCollapsed, setRightCollapsed] = useState(false);

  return (
    <div className="app-shell">
      <nav className="subnav panel">
        <span className="muted-text">Watchlist workspace</span>
        <button type="button" className="ghost-button" onClick={() => setRightCollapsed((prev) => !prev)}>
          {rightCollapsed ? "Show Explain Feed" : "Hide Explain Feed"}
        </button>
      </nav>
      {banners ? <div className="shell-banners">{banners}</div> : null}
      <div className={`shell-grid ${rightCollapsed ? "right-collapsed" : ""}`}>
        <aside className="panel shell-left">{left}</aside>
        <section className="panel shell-main">{main}</section>
        {!rightCollapsed ? <aside className="shell-right">{right}</aside> : null}
      </div>
    </div>
  );
}
