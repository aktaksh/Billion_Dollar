from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class OptionsChainConfig(BaseModel):
    enabled: bool = True
    symbols: list[str] = Field(default_factory=lambda: ["QQQ"])
    default_symbol: str = "QQQ"
    min_dte: int = 14
    max_dte: int = 35
    strike_pct_range: float = 0.10
    quote_batch_size: int = 40
    quote_tick_wait_seconds: float = 3.0
    max_expiries: int = 4
    strikes_below: int = 8
    strikes_above: int = 12
    strike_interval: float = 5.0
    max_contracts_per_scan: int = 200
    allow_exceed_max_contracts: bool = False
    batch_delay_seconds: int = 5
    refresh_seconds: int = 120
    runtime_max_age_seconds: int = 900
    metadata_refresh_minutes: int = 20
    max_spread_pct: float = 0.08
    min_open_interest: int = 500
    min_volume: int = 100
    allow_stale_runtime_dev: bool = False

    def is_scanner_symbol(self, symbol: str) -> bool:
        if not self.enabled:
            return False
        target = symbol.strip().upper()
        return target in {s.strip().upper() for s in self.symbols if s.strip()}


class AppConfig(BaseModel):
    app_name: str = "Billion Dollar API"
    app_version: str = "0.3.0"
    default_trading_mode: str = "paper"
    database_url: str = "sqlite:///./billion_dollar.db"
    broker_backend: str = "tws"
    tws_host: str = "127.0.0.1"
    tws_port: int = 7496
    tws_client_id: int = 1
    tws_read_only: bool = True
    tws_connect_timeout_seconds: float = 10.0
    tws_market_data_type: int = 1
    tws_connection_interval_seconds: int = 60
    auto_ingestion_on_startup: bool = True
    default_runtime_tickers: list[str] = ["QQQ", "SPY", "IWM", "DIA", "XLK", "SMH"]
    reconcile_worker_interval_seconds: int = 60
    reconcile_mismatch_halt_seconds: int = 600
    allow_mock_option_chain: bool = True
    execution_mode: str = "paper_only"
    options_chain: OptionsChainConfig = Field(default_factory=OptionsChainConfig)


_APP_CONFIG_KEYS = frozenset(AppConfig.model_fields.keys())
_OPTIONS_CHAIN_KEY = "options_chain"


def _config_yaml_path() -> Path:
    config_path = os.environ.get("BILLION_DOLLAR_CONFIG")
    if config_path:
        return Path(config_path)
    return Path(__file__).resolve().parent.parent / "config.yaml"


def _load_yaml_config() -> dict:
    path = _config_yaml_path()
    if not path.is_file():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def _apply_env_overrides(values: dict) -> dict:
    merged = dict(values)
    if port := os.environ.get("TWS_PORT"):
        merged["tws_port"] = int(port)
    if backend := os.environ.get("BROKER_BACKEND"):
        merged["broker_backend"] = backend
    if host := os.environ.get("TWS_HOST"):
        merged["tws_host"] = host
    if client_id := os.environ.get("TWS_CLIENT_ID"):
        merged["tws_client_id"] = int(client_id)
    return merged


def _build_settings() -> AppConfig:
    raw = _load_yaml_config()
    yaml_options = raw.get(_OPTIONS_CHAIN_KEY)
    options_chain = (
        OptionsChainConfig(**yaml_options) if isinstance(yaml_options, dict) else OptionsChainConfig()
    )
    app_overrides = {
        key: raw[key]
        for key in _APP_CONFIG_KEYS
        if key in raw and key != _OPTIONS_CHAIN_KEY
    }
    app_overrides = _apply_env_overrides(app_overrides)
    return AppConfig(options_chain=options_chain, **app_overrides)


settings = _build_settings()
