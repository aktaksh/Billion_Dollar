import pandas as pd
import pytest

from src.indicators import compute_daily_indicators
from src.levels import compute_levels


@pytest.fixture
def sample_daily() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=260, freq="B", tz="UTC")
    close = pd.Series(range(100, 360), index=idx, dtype=float)
    df = pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000,
        },
        index=idx,
    )
    return df


def test_daily_indicators(sample_daily: pd.DataFrame) -> None:
    snap = compute_daily_indicators(sample_daily)
    assert snap.close == 359.0
    assert snap.ema20 is not None
    assert snap.rsi14 is not None
    assert snap.ema20 > snap.ema50


def test_levels(sample_daily: pd.DataFrame) -> None:
    levels = compute_levels(sample_daily)
    assert levels.prev_week_high is None or levels.prev_week_high > 0
    assert isinstance(levels.supports, list)
