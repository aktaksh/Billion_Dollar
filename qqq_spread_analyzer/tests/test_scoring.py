from src.indicators import IndicatorSnapshot
from src.levels import LevelSet
from src.scoring import score_setup


def _bullish_daily() -> IndicatorSnapshot:
    return IndicatorSnapshot(
        close=110.0,
        ema20=105.0,
        ema50=100.0,
        sma200=95.0,
        rsi14=58.0,
        macd_line=1.2,
        macd_signal=0.8,
        macd_hist=0.5,
        macd_hist_prev=0.3,
    )


def _bullish_intraday() -> IndicatorSnapshot:
    return IndicatorSnapshot(
        close=110.0,
        ema9=109.0,
        ema21=107.0,
        rsi14=55.0,
        macd_line=0.5,
        macd_signal=0.3,
        macd_hist=0.2,
        macd_hist_prev=0.1,
    )


def test_bullish_setup() -> None:
    levels = LevelSet(prev_week_high=108.0, prev_week_low=95.0)
    result = score_setup(_bullish_daily(), _bullish_intraday(), levels)
    assert result.bullish_score >= 7
    assert result.action == "bull_call_spread"
    assert result.bias == "Bullish"


def test_no_trade_mixed() -> None:
    daily = IndicatorSnapshot(
        close=100.0,
        ema20=101.0,
        ema50=100.0,
        sma200=99.0,
        rsi14=50.0,
        macd_line=0.0,
        macd_signal=0.0,
        macd_hist=0.0,
        macd_hist_prev=0.0,
    )
    intra = IndicatorSnapshot(close=100.0, ema9=100.0, ema21=100.0, rsi14=50.0)
    result = score_setup(daily, intra, LevelSet())
    assert result.action == "no_trade"
