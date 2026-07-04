from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class IbkrGatewayConfig:
    base_url: str
    timeout_seconds: float = 15.0
    verify_tls: bool = False


class IbkrGatewayClient:
    """HTTP client for IBKR Client Portal Gateway REST API."""

    def __init__(self, config: IbkrGatewayConfig) -> None:
        self._config = config

    @property
    def base_url(self) -> str:
        return self._config.base_url.rstrip("/")

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict | None = None,
    ) -> dict[str, Any] | list[Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        with httpx.Client(timeout=self._config.timeout_seconds, verify=self._config.verify_tls) as client:
            response = client.request(method, url, params=params, json=json_body)
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, json_body: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        return self._request("POST", endpoint, json_body=json_body or {})

    def auth_status(self) -> dict[str, Any]:
        raw = self.get("/iserver/auth/status")
        return raw if isinstance(raw, dict) else {}

    def tickle(self) -> dict[str, Any]:
        raw = self.post("/iserver/auth/tickle")
        return raw if isinstance(raw, dict) else {}

    def list_accounts(self) -> list[dict[str, Any]]:
        raw = self.get("/portfolio/accounts")
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
        if isinstance(raw, dict):
            accounts = raw.get("accounts") or raw.get("accountIds") or []
            if isinstance(accounts, list):
                return [{"accountId": a} if isinstance(a, str) else a for a in accounts]
        return []

    def list_positions(self, account_id: str, page_id: int = 0) -> list[dict[str, Any]]:
        raw = self.get(f"/portfolio/{account_id}/positions/{page_id}")
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
        return []

    def list_all_positions(self, account_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 0
        while page < 20:
            batch = self.list_positions(account_id, page)
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return rows

    def market_snapshot(self, conids: list[int]) -> list[dict[str, Any]]:
        if not conids:
            return []
        params = {"conids": ",".join(str(c) for c in conids), "fields": "31,84,86,85,88,7635,7633,7638,7639,7644,7283,7284,7285,7286,7287,7288,7289,7290,7291,7292,7293,7294,7295,7296,7308,7309,7310,7311"}
        raw = self.get("/iserver/marketdata/snapshot", params)
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
        return []

    def contract_info(self, conid: int) -> dict[str, Any]:
        raw = self.get(f"/iserver/contract/{conid}/info")
        return raw if isinstance(raw, dict) else {}

    def is_available(self) -> tuple[bool, str]:
        try:
            status = self.auth_status()
            if status.get("authenticated"):
                return True, "Gateway authenticated"
            if status.get("connected"):
                return False, "Gateway connected but not authenticated — log in via CP Gateway UI"
            return False, "Gateway not connected"
        except Exception as exc:
            return False, f"Gateway unavailable: {exc}"
