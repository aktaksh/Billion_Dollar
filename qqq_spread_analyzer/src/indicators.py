from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class IndicatorSnapshot:
    close: float
    ema20: float | None = None
    ema50: float | None = None
    sma200: float | None = None
    rsi14: float | None = None
    macd_line: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    macd_hist_prev: float | None = None
    atr14: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None
    bb_mid: float | None = None
    ema9: float | None = None
    ema21: float | None = None

    @property
    def macd_expanding(self) -> bool:
        if self.macd_hist is None or self.macd_hist_prev is None:
            return False
        return self.macd_hist > self.macd_hist_prev

    @property
    def macd_weakening(self) -> bool:
        if self.macd_hist is None or self.macd_hist_prev is None:
            return False
        return self.macd_hist < self.macd_hist_prev


def _last(series: pd.Series | None) -> float | None:
    if series is None or series.empty:
        return None
    val = series.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(avg_loss > 0, 100.0)
    return rsi


def _macd(
    series: pd.Series,
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def _bbands(series: pd.Series, length: int = 20, std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = _sma(series, length)
    rolling_std = series.rolling(length).std()
    upper = mid + std * rolling_std
    lower = mid - std * rolling_std
    return lower, mid, upper


def compute_daily_indicators(df: pd.DataFrame) -> IndicatorSnapshot:
    if df.empty:
        return IndicatorSnapshot(close=0.0)
    close = float(df["close"].iloc[-1])
    ema20 = _ema(df["close"], 20)
    ema50 = _ema(df["close"], 50)
    sma200 = _sma(df["close"], 200)
    rsi = _rsi(df["close"], 14)
    macd_line_s, macd_signal_s, macd_hist_s = _macd(df["close"])
    atr = _atr(df["high"], df["low"], df["close"], 14)
    bb_lower, bb_mid, bb_upper = _bbands(df["close"], 20, 2)

    macd_hist_prev = None
    if len(macd_hist_s) >= 2 and not pd.isna(macd_hist_s.iloc[-2]):
        macd_hist_prev = float(macd_hist_s.iloc[-2])

    return IndicatorSnapshot(
        close=close,
        ema20=_last(ema20),
        ema50=_last(ema50),
        sma200=_last(sma200),
        rsi14=_last(rsi),
        macd_line=_last(macd_line_s),
        macd_signal=_last(macd_signal_s),
        macd_hist=_last(macd_hist_s),
        macd_hist_prev=macd_hist_prev,
        atr14=_last(atr),
        bb_upper=_last(bb_upper),
        bb_lower=_last(bb_lower),
        bb_mid=_last(bb_mid),
    )


def compute_intraday_indicators(df: pd.DataFrame) -> IndicatorSnapshot:
    if df.empty:
        return IndicatorSnapshot(close=0.0)
    close = float(df["close"].iloc[-1])
    ema9 = _ema(df["close"], 9)
    ema21 = _ema(df["close"], 21)
    rsi = _rsi(df["close"], 14)
    macd_line_s, macd_signal_s, macd_hist_s = _macd(df["close"])

    macd_hist_prev = None
    if len(macd_hist_s) >= 2 and not pd.isna(macd_hist_s.iloc[-2]):
        macd_hist_prev = float(macd_hist_s.iloc[-2])

    return IndicatorSnapshot(
        close=close,
        ema9=_last(ema9),
        ema21=_last(ema21),
        rsi14=_last(rsi),
        macd_line=_last(macd_line_s),
        macd_signal=_last(macd_signal_s),
        macd_hist=_last(macd_hist_s),
        macd_hist_prev=macd_hist_prev,
    )
