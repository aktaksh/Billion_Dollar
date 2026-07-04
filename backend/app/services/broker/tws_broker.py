from __future__ import annotations

import math
import threading
from typing import Any

from app.config import settings
from app.utils.expiry_format import expiry_compact, normalize_expiry_iso

_loop_lock = threading.Lock()
_loop_started = False
_ib_lock = threading.Lock()


def _ensure_event_loop() -> None:
    global _loop_started
    with _loop_lock:
        if _loop_started:
            return
        from ib_insync import util

        util.startLoop()
        _loop_started = True


def _to_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _option_open_interest(ticker: Any, *, is_call: bool) -> float:
    if is_call:
        raw = getattr(ticker, "callOpenInterest", None)
    else:
        raw = getattr(ticker, "putOpenInterest", None)
    if raw is None:
        raw = getattr(ticker, "openInterest", None)
    return _to_float(raw, 0.0)


class TwsBroker:
    """Read-only TWS/IB Gateway session via ib_insync."""

    name = "tws"

    def __init__(self) -> None:
        _ensure_event_loop()
        from ib_insync import IB

        self._ib = IB()

    def connect(self) -> None:
        with _ib_lock:
            if self._ib.isConnected():
                return
            self._ib.connect(
                settings.tws_host,
                settings.tws_port,
                clientId=settings.tws_client_id,
                readonly=settings.tws_read_only,
                timeout=settings.tws_connect_timeout_seconds,
            )
            self._ib.reqMarketDataType(settings.tws_market_data_type)

    def disconnect(self) -> None:
        with _ib_lock:
            if self._ib.isConnected():
                self._ib.disconnect()

    def is_available(self) -> tuple[bool, str]:
        try:
            self.connect()
            if self._ib.isConnected():
                return True, f"TWS connected on {settings.tws_host}:{settings.tws_port}"
            return False, f"TWS not connected on {settings.tws_host}:{settings.tws_port}"
        except Exception as exc:
            return False, f"TWS unavailable: {exc}"

    def list_option_positions(self) -> list[dict[str, Any]]:
        ok, _ = self.is_available()
        if not ok:
            return []
        out: list[dict[str, Any]] = []
        with _ib_lock:
            for pos in self._ib.positions():
                contract = pos.contract
                if str(contract.secType).upper() != "OPT":
                    continue
                expiry = normalize_expiry_iso(str(getattr(contract, "lastTradeDateOrContractMonth", "") or ""))
                out.append(
                    {
                        "account": pos.account,
                        "symbol": str(contract.symbol),
                        "secType": "OPT",
                        "expiry": expiry,
                        "strike": float(contract.strike),
                        "right": str(contract.right),
                        "position": float(pos.position),
                        "avgCost": float(pos.avgCost),
                        "conId": int(contract.conId),
                    }
                )
        return out

    def fetch_underlying_price(self, symbol: str) -> float:
        from ib_insync import Stock

        ok, _ = self.is_available()
        if not ok:
            return 0.0
        sym = symbol.strip().upper()
        with _ib_lock:
            contracts = self._ib.qualifyContracts(Stock(sym, "SMART", "USD"))
            if not contracts:
                return 0.0
            contract = contracts[0]
            ticker = self._ib.reqMktData(contract, "", False, False)
            self._ib.sleep(2)
            last = _to_float(ticker.last or ticker.close or ticker.marketPrice(), 0.0)
            self._ib.cancelMktData(contract)
            return round(last, 4)

    def fetch_leg_quotes(self, legs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Fetch live quotes for spread legs. Key = leg id string."""
        from ib_insync import Option

        ok, _ = self.is_available()
        if not ok or not legs:
            return {}
        contracts = []
        leg_keys: list[str] = []
        with _ib_lock:
            for leg in legs:
                sym = str(leg["symbol"]).upper()
                expiry = expiry_compact(str(leg["expiry"]))
                strike = float(leg["strike"])
                right = "C" if str(leg.get("right", leg.get("option_type", "call"))).lower().startswith("c") else "P"
                opt = Option(sym, expiry, strike, right, "SMART")
                contracts.append(opt)
                leg_keys.append(str(leg.get("leg_key") or f"{sym}|{leg['expiry']}|{strike}|{right}"))
            qualified = self._ib.qualifyContracts(*contracts)
            if not qualified:
                return {}
            tickers = self._ib.reqTickers(*qualified)
            self._ib.sleep(2)
            result: dict[str, dict[str, Any]] = {}
            for key, t in zip(leg_keys, tickers, strict=False):
                contract = t.contract
                greeks = t.modelGreeks
                bid = _to_float(t.bid, 0.0)
                ask = _to_float(t.ask, 0.0)
                last = _to_float(t.last or t.close, 0.0)
                mid = round((bid + ask) / 2, 4) if bid > 0 and ask > 0 else last
                is_call = contract and contract.right in ("C", "CALL")
                result[key] = {
                    "bid": round(bid, 4),
                    "ask": round(ask, 4),
                    "last": round(last, 4),
                    "mid": mid,
                    "iv": round(_to_float(greeks.impliedVol if greeks else None, 0.0), 4),
                    "delta": round(_to_float(greeks.delta if greeks else None, 0.0), 4),
                    "gamma": round(_to_float(greeks.gamma if greeks else None, 0.0), 4),
                    "theta": round(_to_float(greeks.theta if greeks else None, 0.0), 4),
                    "vega": round(_to_float(greeks.vega if greeks else None, 0.0), 4),
                    "volume": max(0, int(_to_float(t.volume, 0.0))),
                    "open_interest": max(0, int(_option_open_interest(t, is_call=bool(is_call)))),
                    "conId": int(contract.conId) if contract else None,
                }
            for contract in qualified:
                self._ib.cancelMktData(contract)
            return result

    def fetch_quotes_for_trades(self, trades: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
        """Return {trade_id: {long: quote, short: quote}}."""
        legs: list[dict[str, Any]] = []
        trade_leg_map: dict[str, tuple[str, str]] = {}
        for trade in trades:
            tid = str(trade["id"])
            long_key = f"{tid}|long"
            short_key = f"{tid}|short"
            trade_leg_map[tid] = (long_key, short_key)
            expiry = normalize_expiry_iso(trade["expiry_date"])
            long_type = str(trade.get("long_option_type") or "call")
            short_type = str(trade.get("short_option_type") or "call")
            legs.append({
                "leg_key": long_key,
                "symbol": trade["symbol"],
                "expiry": expiry,
                "strike": float(trade["long_strike"]),
                "option_type": long_type,
            })
            legs.append({
                "leg_key": short_key,
                "symbol": trade["symbol"],
                "expiry": expiry,
                "strike": float(trade["short_strike"]),
                "option_type": short_type,
            })
        quotes = self.fetch_leg_quotes(legs)
        out: dict[str, dict[str, dict[str, Any]]] = {}
        for tid, (lk, sk) in trade_leg_map.items():
            if lk in quotes and sk in quotes:
                out[tid] = {"long": quotes[lk], "short": quotes[sk]}
        return out
