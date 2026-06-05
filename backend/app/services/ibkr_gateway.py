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

    @property
    def base_url(self) -> str:
        return self._config.base_url.rstrip("/")

    def _request(self, method: str, endpoint: str, params: dict[str, Any] | None = None, json_body: dict | None = None):
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        with httpx.Client(timeout=self._config.timeout_seconds, verify=self._config.verify_tls) as client:
            response = client.request(method, url, params=params, json=json_body)
            response.raise_for_status()
            return response.json()

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, json_body: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        return self._request("POST", endpoint, json_body=json_body or {})

