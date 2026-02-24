"use client";

import { useTheme } from "@/components/ThemeProvider";

export default function ThemeToggle() {
  const { preference, effectiveTheme, toggleTheme, setPreference } = useTheme();

  return (
    <div className="theme-toggle">
      <span className="theme-toggle-label">Theme</span>
      <button
        type="button"
        className="theme-switch"
        role="switch"
        aria-checked={effectiveTheme === "dark"}
        onClick={toggleTheme}
        aria-label={`Switch theme, current ${effectiveTheme}`}
      >
        <span>{effectiveTheme === "dark" ? "Dark" : "Light"}</span>
      </button>
      <button
        type="button"
        className={`theme-system ${preference === "system" ? "is-active" : ""}`}
        onClick={() => setPreference("system")}
      >
        System
      </button>
    </div>
  );
}
