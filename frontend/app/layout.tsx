import type { Metadata } from "next";
import Image from "next/image";

import GlobalTabs from "@/components/GlobalTabs";
import AiReportButton from "@/components/AiReportButton";
import { ThemeProvider } from "@/components/ThemeProvider";
import ThemeToggle from "@/components/ThemeToggle";
import "./globals.css";
import "../styles/theme.css";

export const metadata: Metadata = {
  title: "Billion Dollar — Options Alpha Research Platform",
  description: "Options alpha research platform — data, discipline, decisions, results",
};

const themeBootScript = `
(() => {
  try {
    const key = "billion_dollar_theme";
    let stored = localStorage.getItem(key);
    if (!stored) {
      stored = localStorage.getItem("stock_tiger_theme") || "system";
    }
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
                  <h1 className="brand">Billion Dollar</h1>
                  <p className="brand-tagline">Options alpha research platform</p>
                </div>
                <div className="header-right">
                  <AiReportButton />
                  <ThemeToggle />
                  <div className="brand-chip" title="Billion Dollar">
                    <Image src="/brand-mark.png" alt="Billion Dollar" width={180} height={108} className="brand-image" unoptimized />
                  </div>
                </div>
              </div>
              <GlobalTabs />
            </header>
          </div>
          <main>{children}</main>
        </ThemeProvider>
      </body>
    </html>
  );
}


