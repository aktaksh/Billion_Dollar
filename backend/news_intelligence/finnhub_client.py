"""Finnhub API client for market and company news."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from news_intelligence.news_config import (
    FINNHUB_BASE_URL,
    FINNHUB_MAX_RETRIES,
    HTTP_TIMEOUT_SECONDS,
    NewsConfig,
)

logger = logging.getLogger(__name__)


class FinnhubError(Exception):
    pass


class FinnhubRateLimitError(FinnhubError):
    pass


class FinnhubAuthError(FinnhubError):
    pass


class FinnhubClient:
    def __init__(self, config: NewsConfig) -> None:
        self._token = config.finnhub_api_key
        self._client = httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)

    def close(self) -> None:
        self._client.close()

    def _request(self, path: str, params: dict[str, Any]) -> Any:
        params = {**params, "token": self._token}
        url = f"{FINNHUB_BASE_URL}{path}"
        last_exc: Exception | None = None

        for attempt in range(FINNHUB_MAX_RETRIES + 1):
            try:
                resp = self._client.get(url, params=params)
                if resp.status_code == 401:
                    raise FinnhubAuthError("Invalid FINNHUB_API_KEY")
                if resp.status_code == 429:
                    raise FinnhubRateLimitError("Finnhub rate limit exceeded")
                if resp.status_code >= 500:
                    raise FinnhubError(f"Finnhub server error {resp.status_code}")
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list):
                    if isinstance(data, dict) and data.get("error"):
                        raise FinnhubError(str(data["error"]))
                    return data if data else []
                return data
            except (FinnhubAuthError, FinnhubRateLimitError):
                raise
            except Exception as exc:
                last_exc = exc
                logger.warning("Finnhub request failed (attempt %s): %s", attempt + 1, exc)

        raise FinnhubError(f"Finnhub request failed after retries: {last_exc}")

    def fetch_market_news(self, category: str = "general") -> list[dict[str, Any]]:
        data = self._request("/news", {"category": category})
        return data if isinstance(data, list) else []

    def fetch_company_news(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
    ) -> list[dict[str, Any]]:
        data = self._request(
            "/company-news",
            {"symbol": symbol.strip().upper(), "from": from_date, "to": to_date},
        )
        return data if isinstance(data, list) else []
