"""SEC EDGAR client for ticker resolution and recent filings."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from news_intelligence.news_config import (
    HTTP_TIMEOUT_SECONDS,
    SEC_ALLOWED_FORMS,
    SEC_MIN_REQUEST_INTERVAL,
    SEC_SUBMISSIONS_URL,
    SEC_TICKERS_URL,
    NewsConfig,
)

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_FILE = CACHE_DIR / "company_tickers.json"
CACHE_MAX_AGE_DAYS = 7


class SecEdgarError(Exception):
    pass


class SecEdgarClient:
    def __init__(self, config: NewsConfig) -> None:
        self._headers = {
            "User-Agent": config.sec_user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        self._client = httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, headers=self._headers)
        self._last_request_at = 0.0
        self._ticker_map: dict[str, str] | None = None

    def close(self) -> None:
        self._client.close()

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < SEC_MIN_REQUEST_INTERVAL:
            time.sleep(SEC_MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.monotonic()

    def _get(self, url: str) -> Any:
        self._rate_limit()
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp.json()

    def _load_ticker_cache(self) -> dict[str, str]:
        if CACHE_FILE.is_file():
            try:
                mtime = datetime.fromtimestamp(CACHE_FILE.stat().st_mtime, tz=UTC)
                if datetime.now(UTC) - mtime < timedelta(days=CACHE_MAX_AGE_DAYS):
                    raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                    return self._parse_ticker_json(raw)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Ticker cache read failed: %s", exc)

        raw = self._get(SEC_TICKERS_URL)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(raw), encoding="utf-8")
        return self._parse_ticker_json(raw)

    @staticmethod
    def _parse_ticker_json(raw: Any) -> dict[str, str]:
        mapping: dict[str, str] = {}
        if isinstance(raw, dict):
            for entry in raw.values():
                if isinstance(entry, dict):
                    ticker = str(entry.get("ticker", "")).upper()
                    cik = str(entry.get("cik_str", ""))
                    if ticker and cik:
                        mapping[ticker] = cik
        return mapping

    def resolve_ticker_to_cik(self, symbol: str) -> str | None:
        if self._ticker_map is None:
            self._ticker_map = self._load_ticker_cache()
        return self._ticker_map.get(symbol.strip().upper())

    @staticmethod
    def _pad_cik(cik: str) -> str:
        return str(cik).zfill(10)

    def fetch_recent_filings(self, symbol: str, max_filings: int = 20) -> list[dict[str, Any]]:
        sym = symbol.strip().upper()
        cik = self.resolve_ticker_to_cik(sym)
        if not cik:
            raise SecEdgarError(f"Could not resolve CIK for ticker {sym}")

        padded = self._pad_cik(cik)
        data = self._get(SEC_SUBMISSIONS_URL.format(cik=padded))
        recent = data.get("filings", {}).get("recent") or {}

        forms = recent.get("form") or []
        dates = recent.get("filingDate") or []
        accessions = recent.get("accessionNumber") or []
        primary_docs = recent.get("primaryDocument") or []
        descriptions = recent.get("primaryDocDescription") or []

        out: list[dict[str, Any]] = []
        for i, form in enumerate(forms):
            if form not in SEC_ALLOWED_FORMS:
                continue
            if i >= len(dates) or i >= len(accessions):
                continue
            out.append({
                "symbol": sym,
                "form_type": form,
                "filing_date": dates[i],
                "accession": accessions[i],
                "primary_document": primary_docs[i] if i < len(primary_docs) else "",
                "description": descriptions[i] if i < len(descriptions) else "",
                "cik": cik,
            })
            if len(out) >= max_filings:
                break
        return out
