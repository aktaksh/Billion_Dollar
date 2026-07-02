import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.options_chain_planner import plan_scan_scope  # noqa: E402
from src.options_chain import _read_ticker_row, _safe_float, _safe_int  # noqa: E402
from types import SimpleNamespace
import math


def test_plan_uses_five_dollar_strikes_only() -> None:
    cfg = SimpleNamespace(
        min_dte=21,
        max_dte=45,
        max_expiries=4,
        strikes_below=8,
        strikes_above=12,
        strike_interval=5.0,
        strike_pct_range=0.10,
        max_contracts_per_scan=200,
        allow_exceed_max_contracts=False,
    )
    expiries = ["2026-04-17", "2026-05-15", "2026-06-19", "2026-07-17"]
    # Mix of $1 and $5 strikes like IB secdef returns
    strikes = [600 + i for i in range(160)] + [700, 705, 710, 715, 720, 725, 730, 735, 740]
    plan = plan_scan_scope(spot=725.0, all_expiries=expiries, all_strikes=strikes, cfg=cfg)
    assert plan.strikes
    for strike in plan.strikes:
        assert abs(strike / 5 - round(strike / 5)) < 0.01
    assert plan.strike_low >= 680
    assert plan.strike_high <= 780
    assert 617 not in plan.strikes


def test_safe_int_handles_nan_and_missing() -> None:
    assert _safe_int(float("nan")) == 0
    assert _safe_int(-1) == 0
    assert _safe_int(42) == 42
    assert _safe_float(-1.0) == 0.0
    assert _safe_float(float("nan")) == 0.0
    assert _safe_float(-0.5, allow_negative=True) == -0.5


def test_read_ticker_row_nan_volume_does_not_crash() -> None:
    ticker = SimpleNamespace(
        bid=1.0,
        ask=2.0,
        last=1.5,
        volume=float("nan"),
        openInterest=float("nan"),
        modelGreeks=None,
    )
    spec = {
        "expiry": "20260731",
        "expiry_iso": "2026-07-31",
        "strike": 700,
        "right": "C",
        "dte": 29,
    }
    row = _read_ticker_row(ticker, spec)
    assert row is not None
    assert row.volume == 0
    assert row.open_interest == 0
