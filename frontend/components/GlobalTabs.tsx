"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/", label: "Watchlist" },
  { href: "/universe", label: "Universe" },
  { href: "/options-chain", label: "Options Chain" },
  { href: "/risk", label: "Risk" },
  { href: "/strategy-builder", label: "Strategy Builder" },
  { href: "/decisions", label: "Decision Ledger" },
  { href: "/replay", label: "Replay" },
  { href: "/paper", label: "Paper" },
  { href: "/positions", label: "Positions" },
  { href: "/blotter", label: "Blotter" },
  { href: "/reconcile", label: "Reconcile" },
  { href: "/review", label: "Review" },
  { href: "/settings", label: "Settings" },
];

export default function GlobalTabs() {
  const pathname = usePathname();
  return (
    <nav className="global-tabs">
      {NAV_ITEMS.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={`tab-link ${pathname === item.href ? "is-active" : ""}`}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
