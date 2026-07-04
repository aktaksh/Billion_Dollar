"""Refresh mode planning for news API calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class RefreshPlan:
    mode: str
    window_hours: int
    symbols: list[str]
    planned_calls: int
    skipped_calls: int = 0
    skip_reasons: list[str] = field(default_factory=list)
    include_sec: bool = True
    include_market_sweep: bool = False

    @property
    def from_date(self) -> datetime:
        return datetime.now(UTC) - timedelta(hours=self.window_hours)

    @property
    def to_date(self) -> datetime:
        return datetime.now(UTC)


class NewsQueryPlanner:
    def plan(self, mode: str, enabled_symbols: list[str]) -> RefreshPlan:
        mode = mode.strip().lower()
        syms = [s.upper() for s in enabled_symbols if s]
        if mode == "quick":
            top = sorted(set(syms), key=lambda s: syms.index(s) if s in syms else 99)[:3]
            if "QQQ" not in top:
                top = list(dict.fromkeys([*top, "QQQ"]))[:4]
            planned = 2 + min(3, len(top)) + 1  # market + company each + av
            skip = 0
            reasons: list[str] = []
            if not syms:
                reasons.append("No watchlist symbols are enabled.")
            return RefreshPlan(
                mode="quick",
                window_hours=24,
                symbols=top or ["QQQ"],
                planned_calls=planned,
                skipped_calls=skip,
                skip_reasons=reasons,
                include_sec=False,
                include_market_sweep=False,
            )
        if mode == "deep":
            planned = 2 + len(syms) + 3 + len([s for s in syms if s not in ("QQQ", "SPY")])
            return RefreshPlan(
                mode="deep",
                window_hours=24 * 7,
                symbols=syms or ["QQQ"],
                planned_calls=planned,
                skipped_calls=0,
                skip_reasons=[],
                include_sec=True,
                include_market_sweep=True,
            )
        # standard
        planned = 2 + len(syms) + 3
        return RefreshPlan(
            mode="standard",
            window_hours=24 * 7,
            symbols=syms or ["QQQ"],
            planned_calls=planned,
            skipped_calls=0,
            skip_reasons=[],
            include_sec=True,
            include_market_sweep=False,
        )
