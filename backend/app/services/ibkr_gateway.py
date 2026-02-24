from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class IbkrGatewayConfig:
    base_url: str
    timeout_seconds: float
    verify_tls: bool


class IbkrGatewayClient:
    def __init__(self, config: IbkrGatewayConfig) -> None:
        self._config = config

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        url = f"{self._config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        with httpx.Client(timeout=self._config.timeout_seconds, verify=self._config.verify_tls) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()

