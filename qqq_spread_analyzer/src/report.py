from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.indicators import IndicatorSnapshot
from src.levels import LevelSet
from src.scoring import ScoreResult
from src.spread_builder import SpreadCandidate


@dataclass
class AnalysisReport:
    timestamp: datetime
    symbol: str
    underlying_price: float
    score: ScoreResult
    daily: IndicatorSnapshot
    intraday: IndicatorSnapshot
    levels: LevelSet
    spreads: list[SpreadCandidate]
    positions_count: int = 0
    open_orders_count: int = 0
    risk_notes: list[str] | None = None


def _indicator_table(title: str, snap: IndicatorSnapshot, extra: dict[str, bool] | None = None) -> Table:
    t = Table(title=title, show_header=True)
    t.add_column("Metric")
    t.add_column("Value")
    rows = [
        ("Close", f"{snap.close:.2f}"),
        ("EMA20", f"{snap.ema20:.2f}" if snap.ema20 else "-"),
        ("EMA50", f"{snap.ema50:.2f}" if snap.ema50 else "-"),
        ("SMA200", f"{snap.sma200:.2f}" if snap.sma200 else "-"),
        ("EMA9", f"{snap.ema9:.2f}" if snap.ema9 else "-"),
        ("EMA21", f"{snap.ema21:.2f}" if snap.ema21 else "-"),
        ("RSI14", f"{snap.rsi14:.2f}" if snap.rsi14 else "-"),
        ("MACD", f"{snap.macd_line:.3f} / {snap.macd_signal:.3f}" if snap.macd_line else "-"),
        ("MACD hist", f"{snap.macd_hist:.3f}" if snap.macd_hist else "-"),
        ("ATR14", f"{snap.atr14:.2f}" if snap.atr14 else "-"),
    ]
    for name, val in rows:
        t.add_row(name, val)
    if extra:
        for k, v in extra.items():
            t.add_row(k, "yes" if v else "no")
    return t


def print_report(report: AnalysisReport, console: Console | None = None) -> None:
    console = console or Console()
    action_label = {
        "bull_call_spread": "Bull call spread",
        "bear_put_spread": "Bear put spread",
        "no_trade": "No trade / wait",
    }[report.score.action]

    header = (
        f"[bold]{report.symbol}[/bold] @ {report.underlying_price:.2f}\n"
        f"Bias: [cyan]{report.score.bias}[/cyan] | Confidence: {report.score.confidence}\n"
        f"Bullish score: {report.score.bullish_score}/10 | Bearish score: {report.score.bearish_score}/10\n"
        f"Suggested action: [green]{action_label}[/green]"
    )
    console.print(Panel(header, title=f"QQQ Spread Analysis — {report.timestamp.isoformat()}", expand=False))

    console.print(_indicator_table("Daily indicators", report.daily, report.score.daily_checks))
    console.print(_indicator_table("Intraday timing", report.intraday, report.score.intraday_checks))

    lvl = Table(title="Key levels")
    lvl.add_column("Support")
    lvl.add_column("Resistance")
    supports = report.levels.supports[:8] or ["-"]
    resistances = report.levels.resistances[:8] or ["-"]
    for i in range(max(len(supports), len(resistances))):
        s = supports[i] if i < len(supports) else ""
        r = resistances[i] if i < len(resistances) else ""
        lvl.add_row(str(s), str(r))
    console.print(lvl)

    if report.spreads:
        st = Table(title="Candidate spreads (max loss shown first)")
        for col in (
            "Type",
            "Expiry",
            "DTE",
            "Buy",
            "Sell",
            "Debit",
            "Max loss",
            "Max profit",
            "BE",
            "R/R",
            "Liq",
        ):
            st.add_column(col)
        for sp in report.spreads:
            st.add_row(
                sp.spread_type.replace("_", " "),
                sp.expiry,
                str(sp.dte),
                f"{sp.buy_strike:.0f} (δ{sp.buy_delta:.2f})",
                f"{sp.sell_strike:.0f} (δ{sp.sell_delta:.2f})",
                f"${sp.net_debit:.2f}",
                f"[red]${sp.max_loss:.0f}[/red]",
                f"${sp.max_profit:.0f}",
                f"{sp.breakeven:.2f}",
                f"{sp.reward_risk:.2f}",
                f"{sp.liquidity_score:.0f}",
            )
        console.print(st)
    else:
        console.print("[yellow]No spread candidates passed filters.[/yellow]")

    notes = report.risk_notes or []
    notes.extend(
        [
            "Research only — no orders placed.",
            f"Open positions (read-only): {report.positions_count}",
            f"Open orders (read-only): {report.open_orders_count}",
        ]
    )
    if report.score.invalid_conditions:
        notes.extend(report.score.invalid_conditions)
    console.print(Panel("\n".join(f"• {n}" for n in notes), title="Risk notes", expand=False))
