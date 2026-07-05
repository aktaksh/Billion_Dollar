"""IBKR News Client — fetches historical headlines via native ibapi TWS API."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

from app.config import settings

logger = logging.getLogger(__name__)

_ib_news_lock = threading.Lock()

TICKER_PROVIDERS = ("DJ-N", "BRFUPDN")
MARKET_PROVIDERS = ("BRFG", "DJ-RT", "DJNL")
ALL_PROVIDERS = TICKER_PROVIDERS + MARKET_PROVIDERS
# Match PlayRough/news.py: first 3 providers IBKR returns (BRFG+BRFUPDN+DJ-N)
PREFERRED_PROVIDER_ORDER = ("BRFG", "BRFUPDN", "DJ-N", "DJ-RT", "DJNL", "DJ-RTA", "DJ-RTE", "DJ-RTG")

DEFAULT_LOOKBACK_DAYS = 10
DEFAULT_MAX_HEADLINES = 20
CACHE_TTL_SECONDS = 1800  # 30 minutes

# IBKR informational / farm status codes — not errors
_INFO_ERROR_CODES = frozenset({2104, 2106, 2107, 2158, 2119, 2103, 2105, 2108, 2168})


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


class _IbkrNewsApi(EWrapper, EClient):
    """Short-lived ibapi session for news provider / contract / headline requests."""

    def __init__(self) -> None:
        EClient.__init__(self, self)
        self.providers: list[str] = []
        self.con_id: int | None = None
        self.headlines: list[IbkrHeadline] = []
        self.news_done = False
        self.last_error: str | None = None

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson="") -> None:
        if errorCode in _INFO_ERROR_CODES:
            logger.debug("IBKR info %s: %s", errorCode, errorString)
            return
        msg = f"IBKR error {errorCode}: {errorString}"
        logger.warning(msg)
        self.last_error = msg

    def newsProviders(self, providers) -> None:
        self.providers = [p.code for p in providers] if providers else []

    def contractDetails(self, reqId, contractDetails) -> None:
        self.con_id = contractDetails.contract.conId

    def historicalNews(self, reqId, timeStamp, providerCode, articleId, headline) -> None:
        text = (headline or "").strip()
        if not text:
            return
        self.headlines.append(
            IbkrHeadline(
                timestamp=str(timeStamp or ""),
                provider_code=str(providerCode or ""),
                article_id=str(articleId or ""),
                headline=text,
            )
        )

    def historicalNewsEnd(self, reqId, hasMore) -> None:
        self.news_done = True


class IbkrNewsClient:
    """Connects to IB Gateway/TWS via native ibapi for historical news."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        cache_ttl: int = CACHE_TTL_SECONDS,
    ) -> None:
        self._host = host or settings.tws_host
        self._port = port or settings.tws_port
        self._client_id = client_id or settings.ibkr_news_client_id
        self._cache_ttl = cache_ttl
        self._app: _IbkrNewsApi | None = None
        self._thread: threading.Thread | None = None
        self._available_providers: list[str] = []
        self._con_id_cache: dict[str, int] = {}
        self._news_cache: dict[str, _CacheEntry] = {}
        self._connected = False
        self._news_wait_seconds = settings.ibkr_news_wait_seconds

    def _start_message_loop(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        assert self._app is not None
        self._thread = threading.Thread(target=self._app.run, daemon=True)
        self._thread.start()
        time.sleep(2)

    def connect(self) -> bool:
        with _ib_news_lock:
            if self._connected and self._app and self._app.isConnected():
                return True
            try:
                self._app = _IbkrNewsApi()
                self._app.connect(self._host, self._port, clientId=self._client_id)
                self._start_message_loop()
                if self._app.isConnected():
                    self._connected = True
                    logger.info("IBKR News client connected on %s:%s", self._host, self._port)
                    return True
                self._connected = False
                return False
            except Exception as exc:
                logger.warning("IBKR News connection failed: %s", exc)
                self._connected = False
                return False

    def disconnect(self) -> None:
        with _ib_news_lock:
            if self._app and self._app.isConnected():
                try:
                    self._app.disconnect()
                except Exception:
                    pass
            self._app = None
            self._thread = None
            self._connected = False

    def is_available(self) -> tuple[bool, str]:
        try:
            if self.connect():
                return True, f"IBKR News connected on {self._host}:{self._port}"
            return False, f"IBKR News unavailable on {self._host}:{self._port}"
        except Exception as exc:
            return False, f"IBKR News unavailable: {exc}"

    def fetch_providers(self) -> list[str]:
        if not self.connect() or not self._app:
            return []
        with _ib_news_lock:
            try:
                self._app.providers = []
                self._app.reqNewsProviders()
                time.sleep(4)
                self._available_providers = list(self._app.providers)
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

        if not self.connect() or not self._app:
            return None

        with _ib_news_lock:
            try:
                contract = Contract()
                contract.symbol = sym
                contract.secType = "STK"
                contract.exchange = "SMART"
                contract.currency = "USD"
                self._app.con_id = None
                self._app.reqContractDetails(1, contract)
                time.sleep(4)
                if self._app.con_id:
                    self._con_id_cache[sym] = self._app.con_id
                    return self._app.con_id
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
        if result.error or not result.headlines:
            return
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

        if not self.connect() or not self._app:
            return IbkrNewsResult(symbol=sym, con_id=None, error="IBKR unavailable")

        con_id = self._resolve_con_id(sym)
        if not con_id:
            return IbkrNewsResult(symbol=sym, con_id=None, error=f"Cannot resolve conId for {sym}")

        available = self.available_providers
        if not available:
            return IbkrNewsResult(symbol=sym, con_id=con_id, error="No news providers available")

        if provider_codes:
            valid_codes = [c for c in provider_codes if c in available]
        else:
            valid_codes = [c for c in PREFERRED_PROVIDER_ORDER if c in available][:3]
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
                self._app.headlines = []
                self._app.news_done = False
                self._app.last_error = None
                self._app.reqHistoricalNews(
                    reqId=2,
                    conId=con_id,
                    providerCodes=providers_str,
                    startDateTime=start_dt.strftime("%Y%m%d %H:%M:%S"),
                    endDateTime=end_dt.strftime("%Y%m%d %H:%M:%S"),
                    totalResults=max_headlines,
                    historicalNewsOptions=[],
                )
                time.sleep(self._news_wait_seconds)
            except Exception as exc:
                return IbkrNewsResult(
                    symbol=sym, con_id=con_id, error=f"reqHistoricalNews failed: {exc}"
                )

        headlines = list(self._app.headlines[:max_headlines])

        if not headlines:
            err = self._app.last_error or (
                f"reqHistoricalNews returned no headlines for {sym} "
                f"(providers={providers_str})"
            )
            return IbkrNewsResult(
                symbol=sym,
                con_id=con_id,
                headlines=[],
                providers_used=valid_codes,
                error=err,
            )

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
