from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Literal

ChainSource = Literal["broker", "mock", "none"]


def _to_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def normalize_market_snapshot(*, ticker: str, ibkr_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize CP snapshot fields or broker-native last/bid/ask/volume dict."""
    row = ibkr_snapshot or {}
    last = _to_float(row.get("31") or row.get("last"), 100.0)
    bid = _to_float(row.get("84") or row.get("bid"), max(0.01, last - 0.2))
    ask = _to_float(row.get("86") or row.get("ask"), max(bid + 0.01, last + 0.2))
    volume = max(0.0, _to_float(row.get("88") or row.get("volume"), 1_000_000.0))
    return {
        "ticker": ticker.upper(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "last": round(last, 4),
        "bid": round(bid, 4),
        "ask": round(ask, 4),
        "volume": int(volume),
    }


def build_mock_option_chain(*, ticker: str, last_price: float) -> list[dict[str, Any]]:
    base = max(5.0, last_price)
    expiries = [(21, "near"), (35, "mid"), (49, "far")]
    strikes = [round(base * x, 2) for x in (0.93, 0.97, 1.0, 1.03, 1.07)]
    out: list[dict[str, Any]] = []
    for dte, _bucket in expiries:
        expiry = datetime.now(timezone.utc).date().toordinal() + dte
        expiry_iso = datetime.fromordinal(expiry).date().isoformat()
        for strike in strikes:
            m = abs(strike - base) / base
            call_mid = max(0.5, base * (0.022 - (m * 0.008)))
            put_mid = max(0.5, base * (0.020 - (m * 0.006)))
            out.append(
                {
                    "symbol": ticker.upper(),
                    "expiry": expiry_iso,
                    "dte": dte,
                    "option_type": "call",
                    "strike": strike,
                    "bid": round(call_mid * 0.97, 4),
                    "ask": round(call_mid * 1.03, 4),
                    "volume": int(500 + (1 - m) * 600),
                    "open_interest": int(1500 + (1 - m) * 1200),
                    "delta": round(0.62 - (m * 1.1), 3),
                    "gamma": round(0.018 + (0.015 if dte <= 24 else 0.006), 4),
                    "theta": round(-0.07 - (0.02 if dte <= 24 else 0.01), 4),
                    "vega": round(0.17 + (0.07 if dte >= 35 else 0.03), 4),
                    "iv": round(0.24 + (m * 0.10), 4),
                }
            )
            out.append(
                {
                    "symbol": ticker.upper(),
                    "expiry": expiry_iso,
                    "dte": dte,
                    "option_type": "put",
                    "strike": strike,
                    "bid": round(put_mid * 0.97, 4),
                    "ask": round(put_mid * 1.03, 4),
                    "volume": int(460 + (1 - m) * 560),
                    "open_interest": int(1400 + (1 - m) * 1100),
                    "delta": round(-0.62 + (m * 1.1), 3),
                    "gamma": round(0.018 + (0.015 if dte <= 24 else 0.006), 4),
                    "theta": round(-0.07 - (0.02 if dte <= 24 else 0.01), 4),
                    "vega": round(0.17 + (0.07 if dte >= 35 else 0.03), 4),
                    "iv": round(0.25 + (m * 0.10), 4),
                }
            )
    return out


def normalize_option_chain_from_broker(
    *,
    ticker: str,
    last_price: float,
    conid: str | None,
    get_fn: Callable[[str, dict | None], dict | list | None] | None,
    allow_mock_fallback: bool,
) -> tuple[list[dict[str, Any]], ChainSource, str]:
    symbol = ticker.upper()
    if conid and get_fn:
        strikes_resp = get_fn("/iserver/secdef/strikes", {"conid": conid, "sectype": "OPT"})
        if isinstance(strikes_resp, dict):
            call_strikes = strikes_resp.get("call") or []
            put_strikes = strikes_resp.get("put") or []
            expiries = strikes_resp.get("expiry") or strikes_resp.get("months") or []
            if (call_strikes or put_strikes) and expiries:
                expiry_raw = expiries[0]
                expiry_iso = str(expiry_raw)
                if len(expiry_iso) == 6 and expiry_iso.isdigit():
                    expiry_iso = f"{expiry_iso[:4]}-{expiry_iso[4:6]}-15"
                dte = max(1, (datetime.fromisoformat(expiry_iso).date() - datetime.now(timezone.utc).date()).days)
                rows: list[dict[str, Any]] = []
                for strike_raw in list(call_strikes)[:8]:
                    strike = _to_float(strike_raw, last_price)
                    mid = max(0.25, abs(last_price - strike) * 0.04 + 0.6)
                    rows.append(
                        {
                            "symbol": symbol,
                            "expiry": expiry_iso,
                            "dte": dte,
                            "option_type": "call",
                            "strike": round(strike, 2),
                            "bid": round(mid * 0.97, 4),
                            "ask": round(mid * 1.03, 4),
                            "volume": 400,
                            "open_interest": 1200,
                            "delta": round(0.55, 3),
                            "gamma": 0.02,
                            "theta": -0.06,
                            "vega": 0.15,
                            "iv": 0.24,
                        }
                    )
                for strike_raw in list(put_strikes)[:8]:
                    strike = _to_float(strike_raw, last_price)
                    mid = max(0.25, abs(last_price - strike) * 0.04 + 0.6)
                    rows.append(
                        {
                            "symbol": symbol,
                            "expiry": expiry_iso,
                            "dte": dte,
                            "option_type": "put",
                            "strike": round(strike, 2),
                            "bid": round(mid * 0.97, 4),
                            "ask": round(mid * 1.03, 4),
                            "volume": 380,
                            "open_interest": 1100,
                            "delta": round(-0.55, 3),
                            "gamma": 0.02,
                            "theta": -0.06,
                            "vega": 0.15,
                            "iv": 0.25,
                        }
                    )
                if rows:
                    return rows, "broker", "ibkr_secdef_strikes"
    if allow_mock_fallback:
        return build_mock_option_chain(ticker=symbol, last_price=last_price), "mock", "deterministic_mock"
    return [], "none", "no_chain_available"


def normalize_option_chain_from_tws(
    *,
    ticker: str,
    last_price: float,
    broker_connected: bool,
    fetch_chain: Callable[[], tuple[list[dict[str, Any]], ChainSource, str]] | None,
    allow_mock_fallback: bool,
) -> tuple[list[dict[str, Any]], ChainSource, str]:
    if broker_connected and fetch_chain:
        rows, source, reason = fetch_chain()
        if rows:
            return rows, source, reason
    if allow_mock_fallback:
        return build_mock_option_chain(ticker=ticker, last_price=last_price), "mock", "deterministic_mock"
    return [], "none", "no_chain_available"


def normalize_context_snapshot(
    *,
    ticker: str,
    market_snapshot: dict[str, Any],
    news_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    spread = 0.0
    bid = _to_float(market_snapshot.get("bid"), 0.0)
    ask = _to_float(market_snapshot.get("ask"), 0.0)
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2.0
        spread = max(0.0, (ask - bid) / mid) if mid > 0 else 0.0
    sentiment = 0.0
    if news_rows:
        blob = " ".join(str(item.get("headline", "")) for item in news_rows).lower()
        positives = ("beat", "growth", "upgrade", "record", "strong", "surge")
        negatives = ("miss", "downgrade", "weak", "warning", "lawsuit", "probe")
        sentiment += sum(1 for word in positives if word in blob)
        sentiment -= sum(1 for word in negatives if word in blob)
    risk_regime = "risk_off" if spread > 0.015 else "risk_on"
    return {
        "ticker": ticker.upper(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "risk_regime": risk_regime,
        "event_risk_score": max(0.0, min(100.0, 50.0 - (sentiment * 6.0))),
        "news_score": max(-1.0, min(1.0, sentiment / 6.0)),
        "earnings_within_days": None,
        "sector_strength_score": 55.0 if risk_regime == "risk_on" else 46.0,
    }
