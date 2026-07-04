"""Expiry Search Engine — scores and ranks expiries across DTE buckets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from src.config import Settings, get_settings
from src.options_chain import OptionQuote


@dataclass
class ExpiryScore:
    expiry: str
    dte: int
    bucket: str
    score: float
    dte_fit: float
    liquidity: float
    strike_availability: float
    bid_ask_quality: float
    event_risk: float
    iv_fit: float
    valid_strikes: int
    liquid_quotes: int
    total_quotes: int
    status: str  # "available", "poor_liquidity", "no_strikes", "unavailable"
    reason: str
    has_event_risk: bool = False


@dataclass
class ExpirySearchResult:
    best_expiry: ExpiryScore | None
    best_bucket: str | None
    rankings: list[ExpiryScore]
    rejected: list[ExpiryScore]
    alternatives: list[ExpiryScore]
    buckets_scanned: list[str]
    expiries_scanned: int
    total_expiries_available: int


def _dte(expiry: str) -> int:
    today = datetime.now(timezone.utc).date()
    exp_str = expiry.replace("-", "")
    if len(exp_str) == 8:
        exp_dt = date(int(exp_str[:4]), int(exp_str[4:6]), int(exp_str[6:8]))
    else:
        exp_dt = date.fromisoformat(expiry[:10])
    return max(0, (exp_dt - today).days)


def _bucket_label(lo: int, hi: int) -> str:
    return f"{lo}-{hi} DTE"


def _dte_fit_score(dte: int, bucket: tuple[int, int], confidence: str, volatility: str) -> float:
    lo, hi = bucket
    mid = (lo + hi) / 2
    dist = abs(dte - mid) / max(1, (hi - lo) / 2)
    base = max(0, 100 - dist * 50)

    if confidence == "High" and 15 <= dte <= 35:
        base = min(100, base + 10)
    elif confidence == "Low" and 36 <= dte <= 60:
        base = min(100, base + 10)

    if volatility == "High" and dte >= 36:
        base = min(100, base + 8)
    elif volatility == "Low" and dte <= 35:
        base = min(100, base + 5)

    return round(base, 1)


def _liquidity_score_for_expiry(quotes: list[OptionQuote]) -> float:
    if not quotes:
        return 0.0
    liquid = [q for q in quotes if q.bid > 0 and q.ask > 0 and q.spread_pct <= 0.15]
    if not liquid:
        return 0.0
    avg_oi = sum(q.open_interest for q in liquid) / len(liquid)
    avg_vol = sum(q.volume for q in liquid) / len(liquid)
    oi_score = min(100, avg_oi / 20)
    vol_score = min(100, avg_vol / 5)
    ratio = len(liquid) / len(quotes)
    return round(ratio * 50 + oi_score * 0.3 + vol_score * 0.2, 1)


def _strike_availability_score(quotes: list[OptionQuote], spot: float) -> float:
    if not quotes:
        return 0.0
    strikes = sorted(set(q.strike for q in quotes))
    in_range = [s for s in strikes if abs(s - spot) / spot <= 0.10]
    if not in_range:
        return 10.0
    return min(100, len(in_range) * 8)


def _bid_ask_quality_score(quotes: list[OptionQuote]) -> float:
    if not quotes:
        return 0.0
    valid = [q for q in quotes if q.bid > 0 and q.ask > 0]
    if not valid:
        return 0.0
    avg_spread = sum(q.spread_pct for q in valid) / len(valid)
    return round(max(0, (1 - avg_spread / 0.20) * 100), 1)


def _event_risk_score(expiry: str, earnings_date: str | None, penalty: int = 20) -> tuple[float, bool]:
    if not earnings_date:
        return 100.0, False
    try:
        exp_dt = date.fromisoformat(expiry[:10])
        earn_dt = date.fromisoformat(earnings_date[:10])
        if earn_dt <= exp_dt:
            return max(0, 100.0 - penalty), True
    except (ValueError, TypeError):
        pass
    return 100.0, False


def _iv_fit_score(quotes: list[OptionQuote]) -> float:
    if not quotes:
        return 50.0
    ivs = [q.iv for q in quotes if q.iv > 0]
    if not ivs:
        return 50.0
    avg_iv = sum(ivs) / len(ivs)
    if 0.15 <= avg_iv <= 0.45:
        return 80.0
    elif avg_iv < 0.15:
        return 60.0
    else:
        return max(30, 80 - (avg_iv - 0.45) * 100)


class ExpirySearchEngine:
    WEIGHTS = {
        "dte_fit": 25,
        "liquidity": 25,
        "strike_availability": 15,
        "bid_ask_quality": 15,
        "event_risk": 10,
        "iv_fit": 10,
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def search(
        self,
        all_quotes: list[OptionQuote],
        spot: float,
        *,
        confidence: str = "Medium",
        volatility: str = "Medium",
        earnings_date: str | None = None,
    ) -> ExpirySearchResult:
        buckets = list(self._settings.dte_buckets)
        if self._settings.aggressive_mode:
            buckets.insert(0, self._settings.dte_bucket_aggressive)

        quotes_by_expiry: dict[str, list[OptionQuote]] = {}
        for q in all_quotes:
            quotes_by_expiry.setdefault(q.expiry, []).append(q)

        scored: list[ExpiryScore] = []
        bucket_labels: list[str] = []

        for bucket in buckets:
            lo, hi = bucket
            label = _bucket_label(lo, hi)
            bucket_labels.append(label)

            for expiry, quotes in quotes_by_expiry.items():
                dte = _dte(expiry)
                if dte < lo or dte > hi:
                    continue

                dte_fit = _dte_fit_score(dte, bucket, confidence, volatility)
                liq = _liquidity_score_for_expiry(quotes)
                strike_avail = _strike_availability_score(quotes, spot)
                baq = _bid_ask_quality_score(quotes)
                event, has_event = _event_risk_score(
                    expiry, earnings_date, self._settings.expiry_event_risk_penalty
                )
                iv = _iv_fit_score(quotes)

                total = (
                    dte_fit * self.WEIGHTS["dte_fit"]
                    + liq * self.WEIGHTS["liquidity"]
                    + strike_avail * self.WEIGHTS["strike_availability"]
                    + baq * self.WEIGHTS["bid_ask_quality"]
                    + event * self.WEIGHTS["event_risk"]
                    + iv * self.WEIGHTS["iv_fit"]
                ) / 100

                liquid_count = len([q for q in quotes if q.bid > 0 and q.ask > 0 and q.spread_pct <= 0.15])

                status = "available"
                reason = "OK"
                if liq < 10:
                    status = "poor_liquidity"
                    reason = "Very low liquidity"
                elif strike_avail < 20:
                    status = "no_strikes"
                    reason = "Insufficient valid strikes near spot"
                elif liquid_count == 0:
                    status = "unavailable"
                    reason = "No liquid contracts"

                scored.append(ExpiryScore(
                    expiry=expiry,
                    dte=dte,
                    bucket=label,
                    score=round(total, 1),
                    dte_fit=dte_fit,
                    liquidity=liq,
                    strike_availability=strike_avail,
                    bid_ask_quality=baq,
                    event_risk=event,
                    iv_fit=iv,
                    valid_strikes=len(set(q.strike for q in quotes)),
                    liquid_quotes=liquid_count,
                    total_quotes=len(quotes),
                    status=status,
                    reason=reason,
                    has_event_risk=has_event,
                ))

        scored.sort(key=lambda x: x.score, reverse=True)

        available = [s for s in scored if s.status == "available"]
        rejected = [s for s in scored if s.status != "available"]

        best = available[0] if available else None
        alternatives = available[1:4] if len(available) > 1 else []

        return ExpirySearchResult(
            best_expiry=best,
            best_bucket=best.bucket if best else None,
            rankings=available,
            rejected=rejected,
            alternatives=alternatives,
            buckets_scanned=bucket_labels,
            expiries_scanned=len(scored),
            total_expiries_available=len(quotes_by_expiry),
        )
