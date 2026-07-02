"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/qqq-spread-analyzer", label: "QQQ Spread Analyzer" },
  { href: "/options-spread-strategy", label: "Options Spread Strategy" },
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
