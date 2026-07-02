from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from ib_insync import IB, Stock, util

from src.config import Settings, get_settings
from src.storage import Storage

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _bars_to_df(bars: list) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame()
    df = util.df(bars)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.rename(columns={"date": "ts"})
    return df.set_index("ts").sort_index()


def _chunk_plan(bar_size: str, duration: str) -> tuple[str, int]:
    """IB may truncate long intraday requests — walk back in 30D chunks for 90D series."""
    if bar_size in ("2 hours", "4 hours") and duration.strip().upper() == "90 D":
        return "30 D", 3
    return duration, 1


def fetch_historical_bars(
    ib: IB,
    symbol: str,
    *,
    bar_size: str,
    duration: str,
    use_rth: bool = True,
    pacing_seconds: float = 1.0,
    max_chunks: int = 1,
) -> pd.DataFrame:
    """Fetch bars. Default single IB request (1Y daily / 90D intraday fits one call)."""
    contract = Stock(symbol.upper(), "SMART", "USD")
    ib.qualifyContracts(contract)
    end = ""
    chunks: list[pd.DataFrame] = []
    seen_oldest: datetime | None = None

    for chunk_idx in range(max_chunks):
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=use_rth,
            formatDate=2,
            timeout=120,
        )
        if not bars:
            break
        chunk = _bars_to_df(bars)
        if chunk.empty:
            break
        oldest = chunk.index.min()
        if seen_oldest is not None and oldest >= seen_oldest:
            break
        seen_oldest = oldest
        chunks.insert(0, chunk)
        if chunk_idx + 1 >= max_chunks:
            break
        if bar_size == "1 day" or len(bars) < 50:
            break
        end = oldest.to_pydatetime().replace(tzinfo=timezone.utc)
        ib.sleep(pacing_seconds)

    if not chunks:
        return pd.DataFrame()
    out = pd.concat(chunks)
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()


def fetch_underlying_price(ib: IB, symbol: str) -> float:
    contract = Stock(symbol.upper(), "SMART", "USD")
    ib.qualifyContracts(contract)
    tickers = ib.reqTickers(contract)
    ib.sleep(1)
    if not tickers:
        return 0.0
    t = tickers[0]
    for val in (t.last, t.close, t.marketPrice()):
        try:
            price = float(val)
            if price > 0:
                return price
        except (TypeError, ValueError):
            continue
    if t.bid and t.ask and t.bid > 0 and t.ask > 0:
        return (float(t.bid) + float(t.ask)) / 2
    return 0.0


def load_or_fetch_bars(
    ib: IB,
    storage: Storage,
    symbol: str,
    *,
    timeframe: str,
    bar_size: str,
    duration: str,
    use_cache: bool = True,
    settings: Settings | None = None,
    progress=None,
    cache_status: dict[str, bool] | None = None,
) -> pd.DataFrame:
    settings = settings or get_settings()
    sym = symbol.upper()
    if use_cache:
        cached = storage.load_bars(sym, timeframe)
        if cached is not None and len(cached) > 20:
            if cache_status is not None:
                cache_status[timeframe] = True
            if progress:
                progress(f"Using cached {timeframe} bars ({len(cached)} rows)")
            return cached
    if cache_status is not None:
        cache_status[timeframe] = False
    chunk_duration, max_chunks = _chunk_plan(bar_size, duration)
    if progress:
        progress(f"Fetching {timeframe} bars from IB ({bar_size}, {duration}, up to {max_chunks} chunk(s))…")
    df = fetch_historical_bars(
        ib,
        sym,
        bar_size=bar_size,
        duration=chunk_duration,
        pacing_seconds=settings.historical_pacing_seconds,
        max_chunks=max_chunks,
    )
    if not df.empty:
        storage.save_bars(sym, timeframe, df)
    if progress:
        progress(f"Got {len(df)} {timeframe} bars")
    return df
