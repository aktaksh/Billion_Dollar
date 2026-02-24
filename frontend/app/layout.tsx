import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import ExplainFeed from "./components/explain-feed";
import GlobalStatus from "./components/global-status";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stock Tiger Dashboard",
  description: "Broker-style recommendation and risk dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="container">
          <header className="topbar">
            <div className="topbar-head">
              <div>
                <h1 className="brand">Stock Tiger Dashboard</h1>
                <p className="subtle" style={{ marginTop: 6 }}>
                  Broker-style recommendations with risk-aware event tracing
                </p>
              </div>
              <div className="tiger-chip" title="Replace /tiger-top.jpg with your preferred tiger image">
                <Image
                  src="/tiger-top.png"
                  alt="Tiger"
                  width={120}
                  height={80}
                  className="tiger-image"
                  unoptimized
                />
              </div>
            </div>
            <nav className="nav">
              <Link className="nav-link" href="/">
                Watchlist
              </Link>
              <Link className="nav-link" href="/universe">
                Universe
              </Link>
              <Link className="nav-link" href="/risk">
                Risk
              </Link>
              <Link className="nav-link" href="/positions">
                Positions
              </Link>
              <Link className="nav-link" href="/blotter">
                Blotter
              </Link>
              <Link className="nav-link" href="/reconcile">
                Reconcile
              </Link>
              <Link className="nav-link" href="/review">
                Review
              </Link>
            </nav>
            <GlobalStatus />
          </header>
          <div className="layout-main">
            <main>{children}</main>
            <ExplainFeed />
          </div>
        </div>
      </body>
    </html>
  );
}


