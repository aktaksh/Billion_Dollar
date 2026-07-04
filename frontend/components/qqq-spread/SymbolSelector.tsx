"use client";

import { useEffect, useRef, useState } from "react";

const LS_SYMBOL_KEY = "billion_dollar_oss_symbol";
const LS_RECENT_KEY = "billion_dollar_oss_recent_symbols";
const MAX_RECENT = 10;

function readRecent(): string[] {
  try {
    const raw = localStorage.getItem(LS_RECENT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((s): s is string => typeof s === "string") : [];
  } catch {
    return [];
  }
}

function pushRecent(symbol: string) {
  const list = readRecent().filter((s) => s !== symbol);
  list.unshift(symbol);
  localStorage.setItem(LS_RECENT_KEY, JSON.stringify(list.slice(0, MAX_RECENT)));
}

export function readPersistedSymbol(): string | null {
  try {
    return localStorage.getItem(LS_SYMBOL_KEY)?.trim().toUpperCase() || null;
  } catch {
    return null;
  }
}

export function persistSymbol(symbol: string) {
  try {
    localStorage.setItem(LS_SYMBOL_KEY, symbol);
    pushRecent(symbol);
  } catch {}
}

type Props = {
  value: string;
  onChange: (symbol: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
};

export default function SymbolSelector({ value, onChange, onSubmit, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [recent, setRecent] = useState<string[]>([]);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setRecent(readRecent());
  }, [open]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  function handleSelect(sym: string) {
    onChange(sym);
    setOpen(false);
    persistSymbol(sym);
    setTimeout(() => onSubmit(), 0);
  }

  function handleFormSubmit(e: React.FormEvent) {
    e.preventDefault();
    setOpen(false);
    if (value.trim()) {
      persistSymbol(value.trim().toUpperCase());
      onSubmit();
    }
  }

  const filtered = recent.filter(
    (s) => s !== value && s.startsWith(value),
  );
  const showList = open && (filtered.length > 0 || recent.length > 0);
  const displayList = filtered.length > 0 ? filtered : recent.filter((s) => s !== value);

  return (
    <div className="symbol-selector-wrapper" ref={wrapperRef}>
      <form className="inline-form" onSubmit={handleFormSubmit}>
        <input
          className="feed-input symbol-selector-input"
          value={value}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          onFocus={() => setOpen(true)}
          placeholder="Symbol"
          disabled={disabled}
          autoComplete="off"
          spellCheck={false}
        />
      </form>

      {showList && displayList.length > 0 && (
        <div className="symbol-selector-dropdown">
          <div className="symbol-selector-header">Recent</div>
          {displayList.slice(0, 8).map((sym) => (
            <button
              key={sym}
              type="button"
              className="symbol-selector-item"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => handleSelect(sym)}
            >
              {sym}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
