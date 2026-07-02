from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.indicators import compute_daily_indicators
from src.levels import compute_levels
from src.scoring import Action, score_setup

ExitRule = Literal[
    "hold_full",
    "profit_50",
    "profit_70",
    "stop_debit",
    "ema20_break",
    "macd_flip",
    "dte_7",
]


@dataclass
class BacktestMetrics:
    signals: int = 0
    bull_signals: int = 0
    bear_signals: int = 0
    no_trade: int = 0
    wins: int = 0
    losses: int = 0
    false_signals: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float = 0.0
    avg_days_in_trade: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0


def _underlying_pnl_proxy(
    action: Action,
    entry_close: float,
    current_close: float,
    *,
    proxy_debit: float,
    proxy_max_profit: float,
) -> float:
    if action == "bull_call_spread":
        move = current_close - entry_close
    else:
        move = entry_close - current_close
    return min(proxy_max_profit, max(-proxy_debit, move))


def _macd_against(action: Action, snap) -> bool:
    if snap.macd_line is None or snap.macd_signal is None:
        return False
    if action == "bull_call_spread":
        return snap.macd_line < snap.macd_signal
    return snap.macd_line > snap.macd_signal


def _ema20_against(action: Action, snap) -> bool:
    if snap.ema20 is None:
        return False
    if action == "bull_call_spread":
        return snap.close < snap.ema20
    return snap.close > snap.ema20


def _should_exit(
    action: Action,
    snap,
    pnl: float,
    *,
    days_held: int,
    hold_days: int,
    proxy_debit: float,
    proxy_max_profit: float,
    exit_profit_pct: float,
    exit_rules: set[ExitRule],
) -> tuple[bool, str]:
    if "profit_70" in exit_rules and pnl >= proxy_max_profit * 0.70:
        return True, "70% max profit"
    if "profit_50" in exit_rules and pnl >= proxy_max_profit * exit_profit_pct:
        return True, "50% max profit"
    if "stop_debit" in exit_rules and pnl <= -proxy_debit:
        return True, "100% debit loss"
    if "ema20_break" in exit_rules and _ema20_against(action, snap):
        return True, "EMA20 break"
    if "macd_flip" in exit_rules and _macd_against(action, snap):
        return True, "MACD flip"
    if "dte_7" in exit_rules and days_held >= max(1, hold_days - 7):
        return True, "7 DTE exit"
    if days_held >= hold_days:
        return True, "max hold"
    return False, ""


def run_bar_backtest(
    daily: pd.DataFrame,
    *,
    hold_days: int = 21,
    proxy_debit: float = 2.0,
    proxy_max_profit: float = 3.0,
    exit_profit_pct: float = 0.5,
    exit_rules: set[ExitRule] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> BacktestMetrics:
    """
    Bar-only proxy backtest: uses signal direction vs forward underlying move.
    Full option P&L requires forward-stored option snapshots (mode snapshot).
    """
    if len(daily) < 220:
        return BacktestMetrics()

    rules: set[ExitRule] = exit_rules or {
        "profit_50",
        "stop_debit",
        "ema20_break",
        "macd_flip",
        "dte_7",
    }

    df = daily.copy()
    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df.index <= pd.Timestamp(end, tz="UTC")]
    if len(df) < 220:
        return BacktestMetrics()

    metrics = BacktestMetrics()
    pnl_series: list[float] = []
    hold_lengths: list[int] = []

    for i in range(200, len(df) - 2):
        window = df.iloc[: i + 1]
        snap = compute_daily_indicators(window)
        levels = compute_levels(window)
        result = score_setup(snap, snap, levels)
        metrics.signals += 1
        if result.action == "no_trade":
            metrics.no_trade += 1
            continue
        if result.action == "bull_call_spread":
            metrics.bull_signals += 1
        else:
            metrics.bear_signals += 1

        entry_close = float(df["close"].iloc[i])
        pnl = 0.0
        exit_day = i
        for offset in range(1, hold_days + 1):
            j = i + offset
            if j >= len(df):
                break
            bar_window = df.iloc[: j + 1]
            bar_snap = compute_daily_indicators(bar_window)
            pnl = _underlying_pnl_proxy(
                result.action,
                entry_close,
                float(df["close"].iloc[j]),
                proxy_debit=proxy_debit,
                proxy_max_profit=proxy_max_profit,
            )
            exit_day = j
            should_exit, _reason = _should_exit(
                result.action,
                bar_snap,
                pnl,
                days_held=offset,
                hold_days=hold_days,
                proxy_debit=proxy_debit,
                proxy_max_profit=proxy_max_profit,
                exit_profit_pct=exit_profit_pct,
                exit_rules=rules,
            )
            if should_exit:
                break

        pnl_series.append(pnl)
        hold_lengths.append(exit_day - i)
        if pnl > 0:
            metrics.wins += 1
        elif pnl < 0:
            metrics.losses += 1
            if result.confidence == "High":
                metrics.false_signals += 1

    if not pnl_series:
        return metrics

    wins = [p for p in pnl_series if p > 0]
    losses = [p for p in pnl_series if p < 0]
    metrics.win_rate = metrics.wins / len(pnl_series)
    metrics.avg_win = sum(wins) / len(wins) if wins else 0
    metrics.avg_loss = sum(losses) / len(losses) if losses else 0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    metrics.profit_factor = gross_win / gross_loss if gross_loss > 0 else gross_win
    metrics.avg_days_in_trade = sum(hold_lengths) / len(hold_lengths)
    metrics.best_trade = max(pnl_series)
    metrics.worst_trade = min(pnl_series)

    equity = pd.Series(pnl_series).cumsum()
    peak = equity.cummax()
    dd = equity - peak
    metrics.max_drawdown = float(dd.min()) if len(dd) else 0
    rets = pd.Series(pnl_series)
    metrics.sharpe = float(rets.mean() / rets.std() * (252**0.5)) if rets.std() > 0 else 0
    return metrics
