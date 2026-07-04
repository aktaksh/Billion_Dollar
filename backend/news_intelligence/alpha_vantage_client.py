"""Alpha Vantage NEWS_SENTIMENT client (limited free tier)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from news_intelligence.news_config import (
    ALPHA_VANTAGE_BASE_URL,
    ALPHA_VANTAGE_MAX_TICKERS,
    HTTP_TIMEOUT_SECONDS,
    NewsConfig,
)

logger = logging.getLogger(__name__)


class AlphaVantageError(Exception):
    pass


class AlphaVantageRateLimitError(AlphaVantageError):
    pass


class AlphaVantageClient:
    def __init__(self, config: NewsConfig) -> None:
        if not config.alpha_vantage_api_key:
            raise AlphaVantageError("ALPHA_VANTAGE_API_KEY not configured")
        self._key = config.alpha_vantage_api_key
        self._client = httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)

    def close(self) -> None:
        self._client.close()

    def fetch_news_sentiment(
        self,
        tickers: list[str],
        topics: str | None = None,
    ) -> list[dict[str, Any]]:
        if not tickers:
            return []
        if len(tickers) > ALPHA_VANTAGE_MAX_TICKERS:
            tickers = tickers[:ALPHA_VANTAGE_MAX_TICKERS]

        params: dict[str, str] = {
            "function": "NEWS_SENTIMENT",
            "tickers": ",".join(t.strip().upper() for t in tickers),
            "apikey": self._key,
        }
        if topics:
            params["topics"] = topics

        resp = self._client.get(ALPHA_VANTAGE_BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        if "Note" in data or "Information" in data:
            msg = data.get("Note") or data.get("Information") or "Rate limit"
            raise AlphaVantageRateLimitError(str(msg))

        feed = data.get("feed") or []
        if not isinstance(feed, list):
            return []
        return feed
