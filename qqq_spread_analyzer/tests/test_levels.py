import pandas as pd

from src.levels import compute_levels


def test_swing_and_gap_levels() -> None:
    idx = pd.date_range("2024-06-01", periods=30, freq="B", tz="UTC")
    close = [100.0] * 30
    close[10] = 105.0
    close[20] = 98.0
    df = pd.DataFrame(
        {
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": 1_000_000,
        },
        index=idx,
    )
    df.iloc[15, df.columns.get_loc("open")] = 110.0  # gap up
    levels = compute_levels(df, gap_min_pct=0.03)
    assert levels.gap_levels or levels.swing_highs or levels.swing_lows
