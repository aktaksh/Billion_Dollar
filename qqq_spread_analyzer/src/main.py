from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from rich.console import Console

# Ensure package root on path when run as script
_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from src.backtest import run_bar_backtest
from src.config import get_settings
from src.data_fetcher import fetch_underlying_price, load_or_fetch_bars
from src.export import write_latest_analysis
from src.expiry_spread_orchestrator import ExpirySpreadOrchestrator
from src.ib_client import ib_session
from src.indicators import compute_daily_indicators, compute_intraday_indicators
from src.levels import compute_levels
from src.options_chain import fetch_option_chain, filter_liquid_options
from src.report import AnalysisReport, print_report
from src.scoring import score_setup
from src.spread_builder import build_spread_candidates
from src.storage import Storage


def run_analyze(symbol: str, *, use_cache: bool = True, timeframe: str | None = None) -> int:
    settings = get_settings()
    if timeframe in ("2h", "4h"):
        settings = settings.model_copy(update={"bar_timeframe": timeframe})
    storage = Storage(settings)
    console = Console()
    cache_status: dict[str, bool] = {}
    chain_diagnostics: dict = {}

    try:
        with ib_session(settings) as ib:
            console.print(f"[dim]Connected to IB {settings.ib_host}:{settings.ib_port} clientId={settings.ib_client_id}[/dim]")

            def progress(msg: str) -> None:
                console.print(f"[cyan]{msg}[/cyan]")

            progress("Fetching underlying price…")
            underlying = fetch_underlying_price(ib, symbol)
            progress(f"Underlying: {underlying:.2f}" if underlying else "Underlying: unavailable")

            daily = load_or_fetch_bars(
                ib,
                storage,
                symbol,
                timeframe="1d",
                bar_size="1 day",
                duration="1 Y",
                use_cache=use_cache,
                settings=settings,
                progress=progress,
                cache_status=cache_status,
            )
            intraday = load_or_fetch_bars(
                ib,
                storage,
                symbol,
                timeframe=settings.bar_timeframe,
                bar_size=settings.ib_bar_size,
                duration="90 D",
                use_cache=use_cache,
                settings=settings,
                progress=progress,
                cache_status=cache_status,
            )

            progress("Computing indicators and score…")
            daily_ind = compute_daily_indicators(daily)
            intra_ind = compute_intraday_indicators(intraday)
            levels = compute_levels(
                daily,
                swing_lookback=settings.swing_lookback,
                gap_min_pct=settings.gap_min_pct,
            )
            score = score_setup(daily_ind, intra_ind, levels)

            progress("Fetching option chain (may take 1–2 min)…")
            raw_quotes = fetch_option_chain(
                ib,
                symbol,
                underlying,
                settings=settings,
                progress=progress,
                diagnostics=chain_diagnostics,
            )
            progress(f"Option quotes: {len(raw_quotes)} raw")
            liquid = filter_liquid_options(raw_quotes, settings)

            progress("Running expiry search engine…")
            orchestrator = ExpirySpreadOrchestrator(settings)
            expiry_spread_result = orchestrator.run(
                raw_quotes,
                liquid,
                underlying,
                score.action,
                confidence=score.confidence,
                volatility="Medium",
                earnings_date=None,
            )
            spreads = expiry_spread_result.final_candidates
            expiry_search_export = orchestrator.export_dict(expiry_spread_result)

            if expiry_spread_result.force_wait:
                progress(f"[yellow]Expiry search: WAIT — {expiry_spread_result.wait_reason}[/yellow]")
            else:
                progress(f"Expiry search: {len(spreads)} candidates across {expiry_spread_result.expiry_search.expiries_scanned} expiries")

            positions = ib.positions()
            orders = ib.openOrders()

            risk_notes: list[str] = []
            if not liquid and raw_quotes:
                risk_notes.append("Options fetched but none passed liquidity filters (wide spread / low OI / volume)")
            elif not raw_quotes:
                risk_notes.append("No live option quotes — market may be closed or data subscription missing")

            report = AnalysisReport(
                timestamp=datetime.now(timezone.utc),
                symbol=symbol.upper(),
                underlying_price=underlying,
                score=score,
                daily=daily_ind,
                intraday=intra_ind,
                levels=levels,
                spreads=spreads,
                positions_count=len(positions),
                open_orders_count=len(orders),
                risk_notes=risk_notes,
            )
            print_report(report, console)

            diagnostics = {
                "ib_connected": True,
                "ib_host": settings.ib_host,
                "ib_port": settings.ib_port,
                "ib_client_id": settings.ib_client_id,
                "daily_bars": len(daily),
                "intraday_bars": len(intraday),
                "intraday_timeframe": settings.bar_timeframe,
                "liquid_quotes": len(liquid),
                "spread_candidates_count": len(spreads),
                "cache_status": {
                    "daily": cache_status.get("1d", False),
                    "intraday": cache_status.get(settings.bar_timeframe, False),
                },
                **chain_diagnostics,
            }
            payload = write_latest_analysis(
                report,
                diagnostics=diagnostics,
                liquid_options=liquid,
                raw_options=raw_quotes,
                expiry_search=expiry_search_export,
                path=settings.latest_analysis_path(symbol),
            )

            storage._conn.execute(
                """
                INSERT INTO analysis_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    uuid4().hex,
                    symbol.upper(),
                    report.timestamp,
                    score.bias,
                    score.confidence,
                    score.bullish_score,
                    score.bearish_score,
                    score.action,
                    underlying,
                    json.dumps(payload),
                ],
            )
            return 0
    finally:
        storage.close()


def run_snapshot(symbol: str) -> int:
    settings = get_settings()
    storage = Storage(settings)
    try:
        with ib_session(settings) as ib:
            underlying = fetch_underlying_price(ib, symbol)
            quotes = fetch_option_chain(ib, symbol, underlying, settings=settings)
            rows = [
                {
                    "expiry": q.expiry,
                    "strike": q.strike,
                    "option_right": "C" if q.option_type == "call" else "P",
                    "bid": q.bid,
                    "ask": q.ask,
                    "last": q.last,
                    "delta": q.delta,
                    "gamma": q.gamma,
                    "theta": q.theta,
                    "vega": q.vega,
                    "iv": q.iv,
                    "volume": q.volume,
                    "open_interest": q.open_interest,
                    "dte": q.dte,
                }
                for q in quotes
            ]
            n = storage.save_option_snapshot(symbol, rows)
            Console().print(f"Saved {n} option rows for {symbol.upper()}")
            return 0
    finally:
        storage.close()


def run_backtest(symbol: str, *, start: str | None = None, end: str | None = None) -> int:
    settings = get_settings()
    storage = Storage(settings)
    console = Console()
    try:
        with ib_session(settings) as ib:
            daily = load_or_fetch_bars(
                ib,
                storage,
                symbol,
                timeframe="1d",
                bar_size="1 day",
                duration="1 Y",
                use_cache=True,
                settings=settings,
            )
        metrics = run_bar_backtest(daily, start=start, end=end)
        console.print(
            f"Backtest proxy ({symbol.upper()} daily bars)\n"
            f"  Signals: {metrics.signals} (bull {metrics.bull_signals}, bear {metrics.bear_signals}, no-trade {metrics.no_trade})\n"
            f"  Win rate: {metrics.win_rate:.1%} | PF: {metrics.profit_factor:.2f}\n"
            f"  Avg win: {metrics.avg_win:.2f} | Avg loss: {metrics.avg_loss:.2f}\n"
            f"  Best: {metrics.best_trade:.2f} | Worst: {metrics.worst_trade:.2f} | False signals: {metrics.false_signals}\n"
            f"  Max DD: {metrics.max_drawdown:.2f} | Sharpe: {metrics.sharpe:.2f} | Avg days: {metrics.avg_days_in_trade:.1f}\n"
            f"  [dim]Note: bar-proxy P&L; run 'snapshot' daily for forward option backtests[/dim]"
        )
        return 0
    finally:
        storage.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="QQQ spread analyzer — IB Gateway research CLI")
    parser.add_argument("--symbol", default="QQQ")
    parser.add_argument("--mode", choices=["analyze", "backtest", "snapshot"], default="analyze")
    parser.add_argument("--timeframe", choices=["2h", "4h"], default=None, help="Intraday bar size for analyze mode")
    parser.add_argument("--start", default=None, help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    if args.mode == "analyze":
        return run_analyze(args.symbol, use_cache=not args.no_cache, timeframe=args.timeframe)
    if args.mode == "snapshot":
        return run_snapshot(args.symbol)
    return run_backtest(args.symbol, start=args.start, end=args.end)


if __name__ == "__main__":
    raise SystemExit(main())
