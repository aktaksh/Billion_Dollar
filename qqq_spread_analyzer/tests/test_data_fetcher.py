from src.data_fetcher import _chunk_plan


def test_chunk_plan_intraday_90d() -> None:
    duration, chunks = _chunk_plan("2 hours", "90 D")
    assert duration == "30 D"
    assert chunks == 3


def test_chunk_plan_daily_single() -> None:
    duration, chunks = _chunk_plan("1 day", "1 Y")
    assert duration == "1 Y"
    assert chunks == 1
