from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PKG_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PKG_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ib_host: str = "127.0.0.1"
    ib_port: int = 4001
    ib_client_id: int = 12
    ib_read_only: bool = True
    ib_market_data_type: int = 1

    bar_timeframe: Literal["2h", "4h"] = "2h"

    min_dte: int = 7
    max_dte: int = 60
    max_option_spread_pct: float = 0.15
    min_open_interest: int = 500
    min_volume: int = 100

    # DTE bucket configuration for multi-expiry search
    dte_buckets: list[tuple[int, int]] = [(15, 21), (22, 35), (36, 45), (46, 60)]
    dte_bucket_aggressive: tuple[int, int] = (7, 14)
    aggressive_mode: bool = False
    max_expiries_per_bucket: int = 2
    expiry_event_risk_penalty: int = 20

    buy_call_delta_min: float = 0.35
    buy_call_delta_max: float = 0.45
    sell_call_delta_min: float = 0.20
    sell_call_delta_max: float = 0.30
    buy_put_delta_min: float = -0.45
    buy_put_delta_max: float = -0.35
    sell_put_delta_min: float = -0.30
    sell_put_delta_max: float = -0.20

    db_path: Path = Field(default=_PKG_ROOT / "data" / "qqq_analyzer.duckdb")
    latest_analysis_dir: Path = Field(default=_PKG_ROOT / "data")

    def latest_analysis_path(self, symbol: str) -> Path:
        sym = symbol.strip().upper()
        return self.latest_analysis_dir / f"latest_analysis_{sym}.json"

    historical_pacing_seconds: float = 1.0
    quote_batch_size: int = 40
    quote_tick_wait_seconds: float = 2.0

    # Option scan scope (matches Billion Dollar options_chain planner)
    max_expiries: int = 8
    strikes_below: int = 8
    strikes_above: int = 12
    strike_interval: float = 5.0
    strike_pct_range: float = 0.10
    max_contracts_per_scan: int = 500
    allow_exceed_max_contracts: bool = False

    gap_min_pct: float = 0.003
    swing_lookback: int = 5

    @property
    def ib_bar_size(self) -> str:
        return "2 hours" if self.bar_timeframe == "2h" else "4 hours"


def get_settings() -> Settings:
    return Settings()
