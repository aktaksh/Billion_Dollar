from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


class AppConfig(BaseModel):
    app_name: str = "Billion Dollar API"
    app_version: str = "0.3.0"
    qqq_analyzer_data_dir: str = ""
    qqq_analyzer_poetry: str = "/opt/homebrew/bin/poetry"
    database_url: str = "sqlite:///./paper_trading.db"
    ibkr_gateway_base_url: str = "https://localhost:5000/v1/api"
    ibkr_gateway_timeout_seconds: float = 15.0
    ibkr_gateway_verify_tls: bool = False
    ibkr_default_account: str = ""
    ibkr_auto_sync_seconds: int = 0
    ibkr_broker_backend: str = "auto"
    tws_host: str = "127.0.0.1"
    tws_port: int = 4001
    tws_client_id: int = 13
    tws_read_only: bool = True
    tws_market_data_type: int = 1
    tws_connect_timeout_seconds: float = 15.0

    # IBKR News settings
    ibkr_news_enabled: bool = True
    ibkr_news_client_id: int = 23
    ibkr_news_cache_ttl_seconds: int = 1800
    ibkr_news_lookback_days: int = 10
    ibkr_news_max_headlines: int = 20
    ibkr_news_max_symbols_refresh: int = 5
    ibkr_news_request_timeout_seconds: float = 30.0
    ibkr_news_wait_seconds: float = 8.0

    # Stale data thresholds (minutes)
    technical_stale_minutes: int = 60
    news_stale_minutes: int = 30
    regime_stale_minutes: int = 60
    scanner_stale_minutes: int = 60


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
    if data_dir := os.environ.get("QQQ_ANALYZER_DATA_DIR"):
        merged["qqq_analyzer_data_dir"] = data_dir
    if poetry := os.environ.get("QQQ_ANALYZER_POETRY"):
        merged["qqq_analyzer_poetry"] = poetry
    if db_url := os.environ.get("DATABASE_URL"):
        merged["database_url"] = db_url
    if gw := os.environ.get("IBKR_GATEWAY_BASE_URL"):
        merged["ibkr_gateway_base_url"] = gw
    if backend := os.environ.get("IBKR_BROKER_BACKEND"):
        merged["ibkr_broker_backend"] = backend
    if tws_host := os.environ.get("TWS_HOST"):
        merged["tws_host"] = tws_host
    if tws_port := os.environ.get("TWS_PORT"):
        merged["tws_port"] = int(tws_port)
    if tws_client := os.environ.get("TWS_CLIENT_ID"):
        merged["tws_client_id"] = int(tws_client)
    return merged


def _build_settings() -> AppConfig:
    raw = _load_yaml_config()
    allowed = set(AppConfig.model_fields.keys())
    overrides = {key: raw[key] for key in allowed if key in raw}
    overrides = _apply_env_overrides(overrides)
    return AppConfig(**overrides)


settings = _build_settings()
