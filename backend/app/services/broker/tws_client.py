from __future__ import annotations

import math
import threading
from datetime import UTC, datetime, timezone
from typing import Any

from app.config import settings

_loop_lock = threading.Lock()
_loop_started = False


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


def _parse_expiry(expiry: str) -> str:
    if len(expiry) == 8 and expiry.isdigit():
        return f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:8]}"
    return expiry


def _option_open_interest(ticker: Any, *, is_call: bool) -> float:
    if is_call:
        raw = getattr(ticker, "callOpenInterest", None)
    else:
        raw = getattr(ticker, "putOpenInterest", None)
    if raw is None:
        raw = getattr(ticker, "openInterest", None)
    return _to_float(raw, 0.0)


class TwsBrokerClient:
    """TWS API read-only client (ib_insync). Never places or modifies orders."""

    def __init__(self) -> None:
        _ensure_event_loop()
        from ib_insync import IB

        self._ib = IB()
        self._lock = threading.Lock()

    def connection_state(self) -> "BrokerConnectionState":
        from app.services.broker.base import BrokerConnectionState

        now = datetime.now(UTC).isoformat()
        connected = bool(self._ib.isConnected())
        return BrokerConnectionState(
            tws_reachable=connected,
            broker_connected=connected,
            broker_authenticated=connected,
            read_only=settings.tws_read_only,
            tws_host=settings.tws_host,
            tws_port=settings.tws_port,
            tws_client_id=settings.tws_client_id,
            message="TWS connected" if connected else "TWS not connected",
            checked_at=now,
        )

    def connect(self) -> "BrokerConnectionState":
        from app.services.broker.base import BrokerConnectionState

        with self._lock:
            if not self._ib.isConnected():
                self._ib.connect(
                    settings.tws_host,
                    settings.tws_port,
                    clientId=settings.tws_client_id,
                    timeout=settings.tws_connect_timeout_seconds,
                    readonly=settings.tws_read_only,
                )
                self._ib.reqMarketDataType(settings.tws_market_data_type)
        state = self.connection_state()
        state.message = "TWS read-only session connected" if state.broker_connected else "TWS connection failed"
        return state

    def disconnect(self) -> None:
        with self._lock:
            if self._ib.isConnected():
                self._ib.disconnect()

    def heartbeat(self) -> None:
        if self._ib.isConnected():
            self._ib.reqCurrentTime()

    def qualify_stock(self, symbol: str) -> "StockContractInfo | None":
        from ib_insync import Stock

        from app.services.broker.base import StockContractInfo

        if not self._ib.isConnected():
            return None
        target = symbol.strip().upper()
        contracts = self._ib.qualifyContracts(Stock(target, "SMART", "USD"))
        if not contracts:
            return None
        row = contracts[0]
        return StockContractInfo(
            symbol=target,
            conid=int(row.conId),
            exchange=str(row.exchange or "SMART"),
            currency=str(row.currency or "USD"),
        )

    def market_snapshot(self, symbol: str) -> dict[str, Any] | None:
        from ib_insync import Stock

        if not self._ib.isConnected():
            return None
        info = self.qualify_stock(symbol)
        if not info:
            return None
        contract = Stock(info.symbol, info.exchange, info.currency)
        qualified = self._ib.qualifyContracts(contract)
        if not qualified:
            return None
        contract = qualified[0]
        ticker = self._ib.reqMktData(contract, "", False, False)
        self._ib.sleep(2)
        last = _to_float(ticker.last or ticker.close or ticker.marketPrice(), 0.0)
        bid = _to_float(ticker.bid, max(0.01, last - 0.2) if last > 0 else 0.01)
        ask = _to_float(ticker.ask, max(bid + 0.01, last + 0.2) if last > 0 else 0.02)
        volume = max(0, int(_to_float(ticker.volume, 0.0)))
        self._ib.cancelMktData(contract)
        if last <= 0:
            return None
        return {
            "ticker": info.symbol,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "last": round(last, 4),
            "bid": round(bid, 4),
            "ask": round(ask, 4),
            "volume": volume,
            "conid": info.conid,
        }

    def option_chain(self, *, symbol: str, last_price: float) -> tuple[list[dict[str, Any]], "ChainSource", str]:
        from ib_insync import Option, Stock

        from app.services.broker.base import ChainSource

        if not self._ib.isConnected():
            return [], "none", "tws_disconnected"
        info = self.qualify_stock(symbol)
        if not info:
            return [], "none", "qualify_failed"
        underlying = Stock(info.symbol, info.exchange, info.currency)
        qualified = self._ib.qualifyContracts(underlying)
        if not qualified:
            return [], "none", "qualify_failed"
        underlying = qualified[0]
        chains = self._ib.reqSecDefOptParams(underlying.symbol, "", underlying.secType, underlying.conId)
        if not chains:
            return [], "none", "no_secdef_opt"
        chain = next((c for c in chains if c.exchange == "SMART"), chains[0])
        expiries = sorted(chain.expirations)
        if not expiries:
            return [], "none", "no_expiries"
        today = datetime.now(timezone.utc).date()
        chosen_expiry = expiries[0]
        chosen_dte = 1
        for exp in expiries:
            expiry_iso = _parse_expiry(exp)
            try:
                dte = max(1, (datetime.fromisoformat(expiry_iso).date() - today).days)
            except ValueError:
                continue
            if 14 <= dte <= 45:
                chosen_expiry = exp
                chosen_dte = dte
                break
        expiry_iso = _parse_expiry(chosen_expiry)
        strikes = sorted(float(s) for s in chain.strikes if s)
        if not strikes:
            return [], "none", "no_strikes"
        atm = min(strikes, key=lambda s: abs(s - last_price))
        idx = strikes.index(atm) if atm in strikes else 0
        window = strikes[max(0, idx - 2) : min(len(strikes), idx + 3)]
        contracts: list[Any] = []
        for strike in window:
            for right in ("C", "P"):
                contracts.append(
                    Option(
                        underlying.symbol,
                        expiry_iso.replace("-", ""),
                        strike,
                        right,
                        chain.exchange or "SMART",
                        tradingClass=chain.tradingClass,
                    )
                )
        qualified_opts = self._ib.qualifyContracts(*contracts)
        if not qualified_opts:
            return [], "none", "option_qualify_failed"
        tickers = self._ib.reqTickers(*qualified_opts)
        self._ib.sleep(2)
        rows: list[dict[str, Any]] = []
        for t in tickers:
            contract = t.contract
            if contract is None:
                continue
            greeks = t.modelGreeks
            bid = _to_float(t.bid, 0.0)
            ask = _to_float(t.ask, 0.0)
            mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else _to_float(t.last or t.close, 0.5)
            is_call = contract.right in ("C", "CALL")
            rows.append(
                {
                    "symbol": info.symbol,
                    "expiry": expiry_iso,
                    "dte": chosen_dte,
                    "option_type": "call" if is_call else "put",
                    "strike": round(float(contract.strike), 2),
                    "bid": round(bid, 4),
                    "ask": round(ask, 4),
                    "volume": max(0, int(_to_float(t.volume, 0.0))),
                    "open_interest": max(0, int(_option_open_interest(t, is_call=is_call))),
                    "delta": round(_to_float(greeks.delta if greeks else 0.0, 0.0), 3),
                    "gamma": round(_to_float(greeks.gamma if greeks else 0.0, 0.0), 4),
                    "theta": round(_to_float(greeks.theta if greeks else 0.0, 0.0), 4),
                    "vega": round(_to_float(greeks.vega if greeks else 0.0, 0.0), 4),
                    "iv": round(_to_float(greeks.impliedVol if greeks else 0.0, 0.0), 4),
                }
            )
        for contract in qualified_opts:
            self._ib.cancelMktData(contract)
        if not rows:
            return [], "none", "empty_option_ticks"
        return rows, "broker", "tws_secdef_opt"

    def list_positions(self) -> list[dict[str, Any]]:
        if not self._ib.isConnected():
            return []
        out: list[dict[str, Any]] = []
        for pos in self._ib.positions():
            contract = pos.contract
            out.append(
                {
                    "account": pos.account,
                    "symbol": str(contract.symbol),
                    "sec_type": str(contract.secType),
                    "position": float(pos.position),
                    "avg_cost": float(pos.avgCost),
                }
            )
        return out

    def list_open_orders(self) -> list[dict[str, Any]]:
        if not self._ib.isConnected():
            return []
        out: list[dict[str, Any]] = []
        for trade in self._ib.openTrades():
            contract = trade.contract
            order = trade.order
            out.append(
                {
                    "order_id": int(order.orderId) if order else 0,
                    "symbol": str(contract.symbol) if contract else "",
                    "status": str(trade.orderStatus.status) if trade.orderStatus else "",
                    "action": str(order.action) if order else "",
                    "total_quantity": float(order.totalQuantity) if order else 0.0,
                }
            )
        return out

    def list_accounts(self) -> list[str]:
        if not self._ib.isConnected():
            return []
        raw = self._ib.managedAccounts()
        return [a.strip() for a in str(raw).split(",") if a.strip()]

    def list_executions(self) -> list[dict[str, Any]]:
        if not self._ib.isConnected():
            return []
        fills = self._ib.reqExecutions()
        out: list[dict[str, Any]] = []
        for fill in fills:
            contract = fill.contract
            execution = fill.execution
            out.append(
                {
                    "exec_id": str(execution.execId),
                    "symbol": str(contract.symbol) if contract else "",
                    "side": str(execution.side),
                    "shares": float(execution.shares),
                    "price": float(execution.price),
                    "time": str(execution.time),
                }
            )
        return out
