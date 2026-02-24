import type { Metadata } from "next";
import Image from "next/image";

import { ThemeProvider } from "@/components/ThemeProvider";
import ThemeToggle from "@/components/ThemeToggle";
import "./globals.css";
import "../styles/theme.css";

export const metadata: Metadata = {
  title: "Stock Tiger Dashboard",
  description: "Broker-style recommendation and risk dashboard",
};

const themeBootScript = `
(() => {
  try {
    const key = "stock_tiger_theme";
    const stored = localStorage.getItem(key) || "system";
    const system = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    const resolved = stored === "system" ? system : stored;
    document.documentElement.setAttribute("data-theme", resolved);
  } catch {
    document.documentElement.setAttribute("data-theme", "dark");
  }
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
      </head>
      <body>
        <ThemeProvider>
          <div className="container">
            <header className="topbar panel">
              <div className="topbar-head">
                <div>
                  <h1 className="brand">Stock Tiger</h1>
                  <p className="muted-text">Broker-style recommendations with risk-aware event tracing</p>
                </div>
                <div className="header-right">
                  <ThemeToggle />
                  <div className="tiger-chip" title="Stock Tiger">
                    <Image src="/tiger-top.png" alt="Tiger" width={120} height={80} className="tiger-image" unoptimized />
                  </div>
                </div>
              </div>
            </header>
          </div>
          <main>{children}</main>
        </ThemeProvider>
      </body>
    </html>
  );
}


