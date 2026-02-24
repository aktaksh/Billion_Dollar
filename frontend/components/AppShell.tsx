"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

type Props = {
  left: React.ReactNode;
  main: React.ReactNode;
  right: React.ReactNode;
  banners?: React.ReactNode;
};

const NAV_ITEMS = [
  { href: "/", label: "Watchlist" },
  { href: "/universe", label: "Universe" },
  { href: "/risk", label: "Risk" },
  { href: "/positions", label: "Positions" },
  { href: "/blotter", label: "Blotter" },
  { href: "/reconcile", label: "Reconcile" },
  { href: "/review", label: "Review" },
];

export default function AppShell({ left, main, right, banners }: Props) {
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const pathname = usePathname();

  return (
    <div className="app-shell">
      <nav className="subnav panel">
        <div className="subnav-links">
          {NAV_ITEMS.map((item) => (
            <Link key={item.href} href={item.href} className={`subnav-link ${pathname === item.href ? "is-active" : ""}`}>
              {item.label}
            </Link>
          ))}
        </div>
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
