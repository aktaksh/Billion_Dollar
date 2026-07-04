"""IBKR News Client — fetches historical headlines via ib_insync TWS API."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_ib_news_lock = threading.Lock()

TICKER_PROVIDERS = ("DJ-N", "BRFUPDN")
MARKET_PROVIDERS = ("BRFG", "DJ-RT", "DJNL")
ALL_PROVIDERS = TICKER_PROVIDERS + MARKET_PROVIDERS

DEFAULT_LOOKBACK_DAYS = 10
DEFAULT_MAX_HEADLINES = 20
CACHE_TTL_SECONDS = 1800  # 30 minutes


@dataclass
class IbkrHeadline:
    timestamp: str
    provider_code: str
    article_id: str
    headline: str


@dataclass
class IbkrNewsResult:
    symbol: str
    con_id: int | None
    headlines: list[IbkrHeadline] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)
    error: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class _CacheEntry:
    result: IbkrNewsResult
    expires_at: float


class IbkrNewsClient:
    """Connects to IB Gateway/TWS via ib_insync for historical news."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        cache_ttl: int = CACHE_TTL_SECONDS,
    ) -> None:
        self._host = host or settings.tws_host
        self._port = port or settings.tws_port
        self._client_id = client_id or (settings.tws_client_id + 10)
        self._cache_ttl = cache_ttl
        self._ib: Any = None
        self._available_providers: list[str] = []
        self._con_id_cache: dict[str, int] = {}
        self._news_cache: dict[str, _CacheEntry] = {}
        self._connected = False

    def _ensure_ib(self) -> Any:
        from ib_insync import IB, util

        if self._ib is None:
            util.startLoop()
            self._ib = IB()
        return self._ib

    def connect(self) -> bool:
        with _ib_news_lock:
            if self._connected and self._ib and self._ib.isConnected():
                return True
            try:
                ib = self._ensure_ib()
                ib.connect(
                    self._host,
                    self._port,
                    clientId=self._client_id,
                    readonly=True,
                    timeout=10,
                )
                self._connected = True
                logger.info("IBKR News client connected on %s:%s", self._host, self._port)
                return True
            except Exception as exc:
                logger.warning("IBKR News connection failed: %s", exc)
                self._connected = False
                return False

    def disconnect(self) -> None:
        with _ib_news_lock:
            if self._ib and self._ib.isConnected():
                try:
                    self._ib.disconnect()
                except Exception:
                    pass
            self._connected = False

    def is_available(self) -> tuple[bool, str]:
        try:
            if self.connect():
                return True, f"IBKR News connected on {self._host}:{self._port}"
            return False, f"IBKR News unavailable on {self._host}:{self._port}"
        except Exception as exc:
            return False, f"IBKR News unavailable: {exc}"

    def fetch_providers(self) -> list[str]:
        if not self.connect():
            return []
        with _ib_news_lock:
            try:
                providers = self._ib.reqNewsProviders()
                self._ib.sleep(1)
                self._available_providers = [p.code for p in providers] if providers else []
                logger.info("IBKR News providers: %s", self._available_providers)
                return self._available_providers
            except Exception as exc:
                logger.warning("Failed to fetch news providers: %s", exc)
                return []

    @property
    def available_providers(self) -> list[str]:
        if not self._available_providers:
            self.fetch_providers()
        return self._available_providers

    def _resolve_con_id(self, symbol: str) -> int | None:
        sym = symbol.strip().upper()
        if sym in self._con_id_cache:
            return self._con_id_cache[sym]

        if not self.connect():
            return None

        from ib_insync import Stock

        with _ib_news_lock:
            try:
                contract = Stock(sym, "SMART", "USD")
                details = self._ib.reqContractDetails(contract)
                self._ib.sleep(1)
                if details:
                    con_id = details[0].contract.conId
                    self._con_id_cache[sym] = con_id
                    return con_id
                logger.warning("No contract details for %s", sym)
                return None
            except Exception as exc:
                logger.warning("Contract lookup failed for %s: %s", sym, exc)
                return None

    def _get_cached(self, symbol: str) -> IbkrNewsResult | None:
        key = symbol.upper()
        entry = self._news_cache.get(key)
        if entry and time.time() < entry.expires_at:
            return entry.result
        if entry:
            del self._news_cache[key]
        return None

    def _set_cache(self, result: IbkrNewsResult) -> None:
        key = result.symbol.upper()
        self._news_cache[key] = _CacheEntry(
            result=result,
            expires_at=time.time() + self._cache_ttl,
        )

    def fetch_historical_news(
        self,
        symbol: str,
        *,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        max_headlines: int = DEFAULT_MAX_HEADLINES,
        provider_codes: list[str] | None = None,
    ) -> IbkrNewsResult:
        sym = symbol.strip().upper()

        cached = self._get_cached(sym)
        if cached:
            logger.debug("IBKR News cache hit for %s", sym)
            return cached

        if not self.connect():
            return IbkrNewsResult(symbol=sym, con_id=None, error="IBKR unavailable")

        con_id = self._resolve_con_id(sym)
        if not con_id:
            return IbkrNewsResult(symbol=sym, con_id=None, error=f"Cannot resolve conId for {sym}")

        available = self.available_providers
        if not available:
            return IbkrNewsResult(symbol=sym, con_id=con_id, error="No news providers available")

        codes = provider_codes or list(TICKER_PROVIDERS)
        valid_codes = [c for c in codes if c in available]
        if not valid_codes:
            valid_codes = [c for c in ALL_PROVIDERS if c in available][:3]
        if not valid_codes:
            return IbkrNewsResult(
                symbol=sym, con_id=con_id, error="No matching news providers available"
            )

        providers_str = "+".join(valid_codes)
        end_dt = datetime.now(UTC)
        start_dt = end_dt - timedelta(days=lookback_days)

        with _ib_news_lock:
            try:
                headlines_raw = self._ib.reqHistoricalNews(
                    con_id,
                    providers_str,
                    start_dt.strftime("%Y%m%d %H:%M:%S"),
                    end_dt.strftime("%Y%m%d %H:%M:%S"),
                    max_headlines,
                )
                self._ib.sleep(2)
            except Exception as exc:
                return IbkrNewsResult(
                    symbol=sym, con_id=con_id, error=f"reqHistoricalNews failed: {exc}"
                )

        headlines: list[IbkrHeadline] = []
        if headlines_raw:
            for h in headlines_raw:
                headlines.append(IbkrHeadline(
                    timestamp=str(getattr(h, "time", "") or ""),
                    provider_code=str(getattr(h, "providerCode", "") or ""),
                    article_id=str(getattr(h, "articleId", "") or ""),
                    headline=str(getattr(h, "headline", "") or ""),
                ))

        result = IbkrNewsResult(
            symbol=sym,
            con_id=con_id,
            headlines=headlines,
            providers_used=valid_codes,
        )
        self._set_cache(result)
        logger.info("IBKR News: fetched %d headlines for %s", len(headlines), sym)
        return result

    def fetch_for_symbols(
        self,
        symbols: list[str],
        *,
        max_symbols: int = 5,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        max_headlines: int = DEFAULT_MAX_HEADLINES,
    ) -> list[IbkrNewsResult]:
        results: list[IbkrNewsResult] = []
        for sym in symbols[:max_symbols]:
            result = self.fetch_historical_news(
                sym,
                lookback_days=lookback_days,
                max_headlines=max_headlines,
            )
            results.append(result)
            time.sleep(0.5)
        return results

    def clear_cache(self) -> None:
        self._news_cache.clear()

    @property
    def cache_stats(self) -> dict[str, Any]:
        now = time.time()
        valid = sum(1 for e in self._news_cache.values() if now < e.expires_at)
        return {
            "total_entries": len(self._news_cache),
            "valid_entries": valid,
            "expired_entries": len(self._news_cache) - valid,
        }
