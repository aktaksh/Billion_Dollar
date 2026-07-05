"""Environment-based configuration for News Intelligence providers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Default symbols for pipeline runs
DEFAULT_PIPELINE_SYMBOLS = (
    "NVDA",
    "AAPL",
    "MSFT",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "TSLA",
    "AMD",
    "QQQ",
    "SPY",
)

# QQQ top holdings priority for Alpha Vantage (max 3 per run)
QQQ_WEIGHT_PRIORITY = (
    "NVDA",
    "AAPL",
    "MSFT",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "TSLA",
    "AMD",
)

ETF_SYMBOLS = frozenset({"QQQ", "SPY", "IWM", "DIA"})

SEC_ALLOWED_FORMS = frozenset({"8-K", "10-Q", "10-K", "4", "S-1", "S-3"})

HTTP_TIMEOUT_SECONDS = 10.0
FINNHUB_MAX_RETRIES = 2
SEC_MIN_REQUEST_INTERVAL = 0.12  # ~8 req/s
ALPHA_VANTAGE_MAX_TICKERS = 3
HEADLINE_SIMILARITY_THRESHOLD = 0.86
DEDUP_WINDOW_HOURS = 72

# Clustering (coarser grouping of already-deduped items into news_events).
# Default threshold is stricter; the looser threshold only applies when items
# also share the same source family (in addition to same symbol + category).
CLUSTER_SIMILARITY_THRESHOLD = 0.70
CLUSTER_SIMILARITY_THRESHOLD_SAME_FAMILY = 0.55

# Primary-ticker-score gating thresholds (Part 4).
PRIMARY_TICKER_MIN_FOR_CATALYST = 60
PRIMARY_TICKER_MIN_FOR_INCLUSION = 40

# Provider -> source family, used to decide when the looser cluster
# similarity threshold is allowed to apply.
SOURCE_FAMILY: dict[str, str] = {
    "IBKR": "IBKR",
    "SEC_EDGAR": "SEC",
    "FINNHUB": "FINNHUB",
    "ALPHA_VANTAGE": "ALPHA_VANTAGE",
}

BROAD_MARKET_KEYWORDS: tuple[str, ...] = (
    "dow jones",
    "s&p 500",
    "s&p500",
    "nasdaq futures",
    "nasdaq composite",
    "wall street",
    "stock market today",
    "futures point to",
    "stocks to watch",
    "premarket movers",
)

SECTOR_KEYWORDS: tuple[str, ...] = (
    "sector",
    "industry-wide",
    "industry wide",
    "chipmakers",
    "semiconductor stocks",
    "peers",
    "tech stocks",
    "bank stocks",
)

# Recency decay for impact_score: linear from 1.0 at <=24h to a 0.3 floor at 7 days.
RECENCY_FULL_WEIGHT_HOURS = 24.0
RECENCY_DECAY_WINDOW_HOURS = 168.0
RECENCY_MIN_WEIGHT = 0.3

# Ticker News Signal bias thresholds (Part 7).
NEWS_BIAS_BULLISH_THRESHOLD = 20.0
NEWS_BIAS_BEARISH_THRESHOLD = -20.0
NEWS_BIAS_MIXED_MIN_MAGNITUDE = 10.0

# TDE fallback when a symbol has no ticker_news_signals row yet — neutral, not bullish.
TDE_NEWS_FALLBACK_SCORE = 50.0

# IBKR News source quality weights (used by scoring pipeline)
SOURCE_QUALITY_WEIGHTS: dict[str, float] = {
    "SEC_EDGAR": 1.00,
    "IBKR_DJ-N": 0.95,
    "IBKR_DJ-RT": 0.90,
    "IBKR_DJNL": 0.90,
    "IBKR_BRFUPDN": 0.90,
    "IBKR_BRFG": 0.85,
    "FINNHUB": 0.70,
    "ALPHA_VANTAGE": 0.65,
}

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


@dataclass(frozen=True)
class NewsConfig:
    finnhub_api_key: str
    sec_user_agent: str
    alpha_vantage_api_key: str | None = None

    @property
    def has_alpha_vantage(self) -> bool:
        return bool(self.alpha_vantage_api_key and self.alpha_vantage_api_key.strip())


def mask_secret(value: str | None, visible: int = 4) -> str:
    if not value:
        return "(not set)"
    if len(value) <= visible:
        return "*" * len(value)
    return value[:visible] + "*" * (len(value) - visible)


def _validate_sec_user_agent(value: str) -> None:
    if not value or " " not in value.strip():
        raise ValueError(
            "SEC_USER_AGENT must be in format 'AppName email@domain' (required by SEC EDGAR)"
        )
    parts = value.strip().split()
    if len(parts) < 2 or not EMAIL_RE.search(parts[-1]):
        raise ValueError(
            "SEC_USER_AGENT must include a contact email, e.g. 'BillionDollarApp you@example.com'"
        )


def load_config(*, require_finnhub: bool = True, require_sec: bool = True) -> NewsConfig:
    finnhub = os.environ.get("FINNHUB_API_KEY", "").strip()
    sec_ua = os.environ.get("SEC_USER_AGENT", "").strip()
    av_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip() or None

    if require_finnhub and not finnhub:
        raise ValueError("FINNHUB_API_KEY environment variable is required")
    if require_sec:
        _validate_sec_user_agent(sec_ua)

    return NewsConfig(
        finnhub_api_key=finnhub,
        sec_user_agent=sec_ua,
        alpha_vantage_api_key=av_key,
    )
