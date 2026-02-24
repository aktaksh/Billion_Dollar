"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

type ThemePreference = "dark" | "light" | "system";
type EffectiveTheme = "dark" | "light";

type ThemeContextValue = {
  preference: ThemePreference;
  effectiveTheme: EffectiveTheme;
  setPreference: (theme: ThemePreference) => void;
  toggleTheme: () => void;
};

const THEME_STORAGE_KEY = "stock_tiger_theme";

const ThemeContext = createContext<ThemeContextValue | null>(null);

function systemTheme(): EffectiveTheme {
  if (typeof window === "undefined" || !window.matchMedia) {
    return "dark";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: EffectiveTheme) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", theme);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>("system");
  const [effectiveTheme, setEffectiveTheme] = useState<EffectiveTheme>("dark");

  useEffect(() => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    const pref: ThemePreference = stored === "dark" || stored === "light" || stored === "system" ? stored : "system";
    const resolved = pref === "system" ? systemTheme() : pref;
    setPreferenceState(pref);
    setEffectiveTheme(resolved);
    applyTheme(resolved);
  }, []);

  useEffect(() => {
    if (preference !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const next = media.matches ? "dark" : "light";
      setEffectiveTheme(next);
      applyTheme(next);
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [preference]);

  const setPreference = (theme: ThemePreference) => {
    const next = theme === "system" ? systemTheme() : theme;
    setPreferenceState(theme);
    setEffectiveTheme(next);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    applyTheme(next);
  };

  const toggleTheme = () => {
    const next = effectiveTheme === "dark" ? "light" : "dark";
    setPreference(next);
  };

  const value = useMemo<ThemeContextValue>(
    () => ({
      preference,
      effectiveTheme,
      setPreference,
      toggleTheme,
    }),
    [preference, effectiveTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used inside ThemeProvider");
  }
  return ctx;
}
