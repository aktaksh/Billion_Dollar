import pandas as pd

from src.backtest import run_bar_backtest


def _sample_daily(rows: int = 260) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=rows, freq="B", tz="UTC")
    close = pd.Series(range(100, 100 + rows), index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000,
        },
        index=idx,
    )


def test_backtest_runs_on_uptrend() -> None:
    metrics = run_bar_backtest(_sample_daily())
    assert metrics.signals > 0
    assert metrics.bull_signals + metrics.bear_signals + metrics.no_trade == metrics.signals


def test_backtest_date_filter() -> None:
    df = _sample_daily()
    metrics = run_bar_backtest(df, start="2024-06-01", end="2024-09-01")
    assert metrics.signals >= 0
