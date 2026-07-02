from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import pandas as pd


@dataclass
class LevelSet:
    prev_week_high: float | None = None
    prev_week_low: float | None = None
    prev_month_high: float | None = None
    prev_month_low: float | None = None
    swing_highs: list[float] = field(default_factory=list)
    swing_lows: list[float] = field(default_factory=list)
    gap_levels: list[float] = field(default_factory=list)

    @property
    def supports(self) -> list[float]:
        levels = [self.prev_week_low, self.prev_month_low, *self.swing_lows, *self.gap_levels]
        return sorted({round(x, 2) for x in levels if x is not None})

    @property
    def resistances(self) -> list[float]:
        levels = [self.prev_week_high, self.prev_month_high, *self.swing_highs]
        return sorted({round(x, 2) for x in levels if x is not None}, reverse=True)


def _calendar_week_bounds(ts: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = ts - timedelta(days=int(ts.weekday()) + 7)
    end = start + timedelta(days=4)
    return start.normalize(), end.normalize()


def compute_levels(daily: pd.DataFrame, *, swing_lookback: int = 5, gap_min_pct: float = 0.003) -> LevelSet:
    if daily.empty or len(daily) < 10:
        return LevelSet()

    df = daily.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")

    now = df.index[-1]
    pw_start, pw_end = _calendar_week_bounds(now)
    prev_week = df[(df.index >= pw_start) & (df.index <= pw_end)]
    pm_start = (now - pd.offsets.MonthBegin(2)).normalize()
    pm_end = (now - pd.offsets.MonthBegin(1)).normalize()
    prev_month = df[(df.index >= pm_start) & (df.index < pm_end)]

    swing_highs: list[float] = []
    swing_lows: list[float] = []
    lb = max(2, swing_lookback)
    highs = df["high"].values
    lows = df["low"].values
    for i in range(lb, len(df) - lb):
        window_h = highs[i - lb : i + lb + 1]
        window_l = lows[i - lb : i + lb + 1]
        if highs[i] == window_h.max():
            swing_highs.append(float(highs[i]))
        if lows[i] == window_l.min():
            swing_lows.append(float(lows[i]))

    gap_levels: list[float] = []
    for i in range(1, len(df)):
        prev_close = float(df["close"].iloc[i - 1])
        open_px = float(df["open"].iloc[i])
        if prev_close <= 0:
            continue
        gap_pct = abs(open_px - prev_close) / prev_close
        if gap_pct >= gap_min_pct:
            gap_levels.append(open_px)

    return LevelSet(
        prev_week_high=float(prev_week["high"].max()) if not prev_week.empty else None,
        prev_week_low=float(prev_week["low"].min()) if not prev_week.empty else None,
        prev_month_high=float(prev_month["high"].max()) if not prev_month.empty else None,
        prev_month_low=float(prev_month["low"].min()) if not prev_month.empty else None,
        swing_highs=sorted(set(round(x, 2) for x in swing_highs[-8:])),
        swing_lows=sorted(set(round(x, 2) for x in swing_lows[-8:])),
        gap_levels=sorted(set(round(x, 2) for x in gap_levels[-6:])),
    )
