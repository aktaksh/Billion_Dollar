from __future__ import annotations

import logging
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Literal

from ib_insync import IB, Option, Stock

from src.config import Settings, get_settings
_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.broker.option_chain_ibkr import (  # noqa: E402
    build_option_contract_specs,
    parse_secdef_option_chains,
    select_option_chain,
)
from app.services.options_chain_planner import plan_scan_scope  # noqa: E402

PREFERRED_OPTION_EXCHANGES = ("SMART", "AMEX")


@dataclass
class OptionQuote:
    expiry: str
    dte: int
    option_type: Literal["call", "put"]
    strike: float
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    delta: float
    gamma: float
    theta: float
    vega: float
    iv: float

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last if self.last > 0 else 0.0

    @property
    def spread_pct(self) -> float:
        mid = self.mid
        if mid <= 0:
            return 1.0
        return max(0.0, (self.ask - self.bid) / mid)


def _dte(expiry: str, today: date | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    exp = expiry.replace("-", "")
    if len(exp) == 8:
        exp_dt = date(int(exp[:4]), int(exp[4:6]), int(exp[6:8]))
    else:
        exp_dt = date.fromisoformat(expiry[:10])
    return max(0, (exp_dt - today).days)


def _normalize_expiry_iso(expiry: str) -> str:
    if "-" in expiry:
        return expiry[:10]
    if len(expiry) == 8:
        return f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:8]}"
    return expiry


def _option_from_spec(spec: dict[str, Any], exchange: str) -> Option:
    return Option(
        spec["symbol"],
        spec["expiry"],
        float(spec["strike"]),
        spec["right"],
        exchange,
        multiplier=str(spec.get("multiplier") or 100),
        tradingClass=spec.get("trading_class") or "",
        currency=spec.get("currency") or "USD",
    )


def _qualify_options_with_exchange_fallback(
    ib: IB,
    specs: list[dict[str, Any]],
    *,
    preferred_exchanges: tuple[str, ...] = PREFERRED_OPTION_EXCHANGES,
) -> list[Any]:
    if not specs:
        return []
    qualified: list[Any] = []
    pending = list(specs)
    for exchange in preferred_exchanges:
        if not pending:
            break
        contracts = [_option_from_spec(spec, exchange) for spec in pending]
        results = ib.qualifyContracts(*contracts)
        next_pending: list[dict[str, Any]] = []
        for spec, result in zip(pending, results, strict=False):
            if result is not None and int(getattr(result, "conId", 0) or 0) > 0:
                qualified.append(result)
            else:
                next_pending.append(spec)
        pending = next_pending
    return qualified


def _contract_lookup_key(contract: Any) -> tuple[str, float, str]:
    expiry = str(getattr(contract, "lastTradeDateOrContractMonth", "") or "")
    strike = float(getattr(contract, "strike", 0) or 0)
    right = str(getattr(contract, "right", "") or "").upper()
    return expiry, strike, right


def _spec_lookup_key(spec: dict[str, Any]) -> tuple[str, float, str]:
    return str(spec["expiry"]), float(spec["strike"]), str(spec["right"]).upper()


def _safe_float(value: Any, default: float = 0.0, *, allow_negative: bool = False) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    if not allow_negative and out < 0:
        return default
    return out


def _safe_int(value: Any, default: int = 0) -> int:
    f = _safe_float(value, float(default), allow_negative=False)
    return int(f)


def _read_ticker_row(ticker: Any, spec: dict[str, Any]) -> OptionQuote | None:
    raw_vol = getattr(ticker, "volume", 0)
    raw_oi = getattr(ticker, "openInterest", 0)
    bid = _safe_float(ticker.bid)
    ask = _safe_float(ticker.ask)
    last = _safe_float(ticker.last)
    greeks = getattr(ticker, "modelGreeks", None)
    delta = _safe_float(getattr(greeks, "delta", 0) if greeks else 0, allow_negative=True)
    gamma = _safe_float(getattr(greeks, "gamma", 0) if greeks else 0, allow_negative=True)
    theta = _safe_float(getattr(greeks, "theta", 0) if greeks else 0, allow_negative=True)
    vega = _safe_float(getattr(greeks, "vega", 0) if greeks else 0, allow_negative=True)
    iv = _safe_float(getattr(greeks, "impliedVol", 0) if greeks else 0)
    expiry = _normalize_expiry_iso(str(spec.get("expiry_iso") or spec["expiry"]))
    right = str(spec.get("right", "C")).upper()
    return OptionQuote(
        expiry=expiry,
        dte=int(spec.get("dte") or _dte(expiry)),
        option_type="call" if right == "C" else "put",
        strike=float(spec["strike"]),
        bid=bid,
        ask=ask,
        last=last,
        volume=_safe_int(raw_vol),
        open_interest=_safe_int(raw_oi),
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        iv=iv,
    )


def _scan_cfg(settings: Settings) -> SimpleNamespace:
    return SimpleNamespace(
        min_dte=settings.min_dte,
        max_dte=settings.max_dte,
        max_expiries=settings.max_expiries,
        strikes_below=settings.strikes_below,
        strikes_above=settings.strikes_above,
        strike_interval=settings.strike_interval,
        strike_pct_range=settings.strike_pct_range,
        max_contracts_per_scan=settings.max_contracts_per_scan,
        allow_exceed_max_contracts=False,
    )


def fetch_option_chain(
    ib: IB,
    symbol: str,
    underlying_price: float,
    *,
    settings: Settings | None = None,
    progress: Callable[[str], None] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> list[OptionQuote]:
    settings = settings or get_settings()
    sym = symbol.upper()
    contracts_planned = 0
    contracts_qualified = 0
    qualification_failures: dict[str, int] = {}
    ib_error_200_count = 0
    stk = Stock(sym, "SMART", "USD")
    qualified_stk = ib.qualifyContracts(stk)
    if not qualified_stk:
        return []
    conid = qualified_stk[0].conId
    chains_raw = ib.reqSecDefOptParams(sym, "", "STK", conid)
    chains = parse_secdef_option_chains(chains_raw)
    selected = select_option_chain(chains, symbol=sym)
    if not selected:
        return []

    all_expiries = [_normalize_expiry_iso(e) for e in selected.expirations]
    all_strikes = [float(s) for s in selected.strikes]
    plan = plan_scan_scope(
        spot=underlying_price,
        all_expiries=all_expiries,
        all_strikes=all_strikes,
        cfg=_scan_cfg(settings),
    )
    if progress:
        progress(
            f"Scan plan: {len(plan.expiries)} expiries, {len(plan.strikes)} $5 strikes "
            f"({plan.strike_low:.0f}–{plan.strike_high:.0f}), ~{plan.planned_contracts} contracts"
        )
    if not plan.expiries or not plan.strikes:
        if diagnostics is not None:
            diagnostics.update({
                "contracts_planned": 0,
                "contracts_qualified": 0,
                "raw_quotes": 0,
                "qualification_failures": [],
                "ib_error_200_count": 0,
            })
        return []

    contracts_planned = plan.planned_contracts

    quotes: list[OptionQuote] = []
    batch_strikes = max(1, settings.quote_batch_size // 2)

    for expiry in plan.expiries:
        expiry_iso = _normalize_expiry_iso(expiry)
        dte = _dte(expiry_iso)
        for start in range(0, len(plan.strikes), batch_strikes):
            strike_chunk = plan.strikes[start : start + batch_strikes]
            specs = build_option_contract_specs(
                symbol=sym,
                expiry=expiry_iso,
                strikes=strike_chunk,
                exchange=selected.exchange,
                trading_class=selected.trading_class,
                multiplier=selected.multiplier,
            )
            for spec in specs:
                spec["dte"] = dte

            qualified_opts = _qualify_options_with_exchange_fallback(ib, specs)
            contracts_qualified += len(qualified_opts)
            failed = len(specs) - len(qualified_opts)
            if failed > 0:
                ib_error_200_count += failed
                qualification_failures[expiry_iso] = qualification_failures.get(expiry_iso, 0) + failed
            if not qualified_opts:
                continue

            spec_by_key = {_spec_lookup_key(s): s for s in specs}
            tickers = ib.reqTickers(*qualified_opts)
            ib.sleep(settings.quote_tick_wait_seconds)
            for ticker in tickers:
                contract = getattr(ticker, "contract", None)
                if contract is None:
                    continue
                spec = spec_by_key.get(_contract_lookup_key(contract))
                if not spec:
                    continue
                row = _read_ticker_row(ticker, spec)
                if row:
                    quotes.append(row)

    if diagnostics is not None:
        diagnostics.update({
            "contracts_planned": contracts_planned,
            "contracts_qualified": contracts_qualified,
            "raw_quotes": len(quotes),
            "ib_error_200_count": ib_error_200_count,
            "qualification_failures": [
                {
                    "expiry": expiry,
                    "failed_count": count,
                    "reason_hint": "Likely invalid expiry/strike combination or contract not listed",
                }
                for expiry, count in sorted(qualification_failures.items())
            ],
        })
    return quotes


def filter_liquid_options(quotes: list[OptionQuote], settings: Settings | None = None) -> list[OptionQuote]:
    settings = settings or get_settings()
    out: list[OptionQuote] = []
    for q in quotes:
        if q.bid <= 0 or q.ask <= 0:
            continue
        if q.spread_pct > settings.max_option_spread_pct:
            continue
        if q.open_interest > 0 and q.open_interest < settings.min_open_interest:
            continue
        if q.volume > 0 and q.volume < settings.min_volume:
            continue
        out.append(q)
    return out
