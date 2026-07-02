from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


class AppConfig(BaseModel):
    app_name: str = "Billion Dollar API"
    app_version: str = "0.3.0"
    qqq_analyzer_data_dir: str = ""
    qqq_analyzer_poetry: str = "/opt/homebrew/bin/poetry"


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
    return merged


def _build_settings() -> AppConfig:
    raw = _load_yaml_config()
    allowed = set(AppConfig.model_fields.keys())
    overrides = {key: raw[key] for key in allowed if key in raw}
    overrides = _apply_env_overrides(overrides)
    return AppConfig(**overrides)


settings = _build_settings()
