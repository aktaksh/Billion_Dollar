from __future__ import annotations

import logging
import math
import threading
from datetime import UTC, datetime, timezone
from typing import Any

from app.config import settings
from app.services.broker.option_chain_ibkr import (
    ChainFetchDiagnostics,
    build_option_contract_specs,
    filter_expiries_by_dte,
    filter_strikes_by_pct,
    parse_secdef_option_chains,
    select_option_chain,
)

log = logging.getLogger(__name__)

_loop_lock = threading.Lock()
_loop_started = False

PREFERRED_OPTION_EXCHANGES = ("SMART", "AMEX")
LIVE_MARKET_DATA_TYPE = 1
DELAYED_MARKET_DATA_TYPE = 3


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


def _expiry_compact(expiry: str) -> str:
    if len(expiry) == 8 and expiry.isdigit():
        return expiry
    return expiry.replace("-", "")


def _qualified_options(contracts: list[Any]) -> list[Any]:
    """Keep only contracts IB resolved (conId > 0)."""
    return [c for c in contracts if int(getattr(c, "conId", 0) or 0) > 0]


def _has_bid_ask(ticker: Any) -> bool:
    bid = _to_float(getattr(ticker, "bid", None), 0.0)
    ask = _to_float(getattr(ticker, "ask", None), 0.0)
    return bid > 0 and ask > 0


def _model_greeks_snapshot(greeks: Any) -> dict[str, float] | None:
    if greeks is None:
        return None
    return {
        "delta": round(_to_float(getattr(greeks, "delta", None), 0.0), 4),
        "gamma": round(_to_float(getattr(greeks, "gamma", None), 0.0), 4),
        "theta": round(_to_float(getattr(greeks, "theta", None), 0.0), 4),
        "vega": round(_to_float(getattr(greeks, "vega", None), 0.0), 4),
        "implied_vol": round(_to_float(getattr(greeks, "impliedVol", None), 0.0), 4),
    }


def _ticker_row_from_contract(
    ticker: Any,
    *,
    symbol: str,
    expiry: str,
    dte: int,
    data_type: str,
) -> dict[str, Any] | None:
    contract = getattr(ticker, "contract", None)
    if contract is None:
        return None
    greeks = getattr(ticker, "modelGreeks", None)
    greek_snap = _model_greeks_snapshot(greeks)
    bid = _to_float(getattr(ticker, "bid", None), 0.0)
    ask = _to_float(getattr(ticker, "ask", None), 0.0)
    last = _to_float(getattr(ticker, "last", None) or getattr(ticker, "close", None), 0.0)
    mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else last
    is_call = contract.right in ("C", "CALL")
    implied_vol = greek_snap["implied_vol"] if greek_snap else 0.0
    return {
        "symbol": symbol,
        "expiry": expiry,
        "dte": dte,
        "option_type": "call" if is_call else "put",
        "strike": round(float(contract.strike), 2),
        "bid": round(bid, 4),
        "ask": round(ask, 4),
        "last": round(last, 4) if last > 0 else None,
        "mid": round(mid, 4),
        "volume": max(0, int(_to_float(getattr(ticker, "volume", None), 0.0))),
        "open_interest": max(0, int(_option_open_interest(ticker, is_call=is_call))),
        "delta": round(_to_float(greeks.delta if greeks else 0.0, 0.0), 3),
        "gamma": round(_to_float(greeks.gamma if greeks else 0.0, 0.0), 4),
        "theta": round(_to_float(greeks.theta if greeks else 0.0, 0.0), 4),
        "vega": round(_to_float(greeks.vega if greeks else 0.0, 0.0), 4),
        "iv": round(implied_vol, 4),
        "implied_vol": round(implied_vol, 4),
        "model_greeks": greek_snap,
        "data_type": data_type,
    }


def _ticker_rows_from_qualified(
    tickers: list[Any],
    *,
    symbol: str,
    expiry: str,
    dte: int,
    data_types: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        contract = getattr(ticker, "contract", None)
        con_id = int(getattr(contract, "conId", 0) or 0) if contract else 0
        data_type = (data_types or {}).get(con_id, "LIVE")
        row = _ticker_row_from_contract(
            ticker,
            symbol=symbol,
            expiry=expiry,
            dte=dte,
            data_type=data_type,
        )
        if row:
            rows.append(row)
    return rows


class TwsBrokerClient:
    """TWS API read-only client (ib_insync). Never places or modifies orders."""

    def __init__(self) -> None:
        _ensure_event_loop()
        from ib_insync import IB

        self._ib = IB()
        self._lock = threading.RLock()

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
        with self._lock:
            if not self._ib.isConnected():
                try:
                    self._ib.connect(
                        settings.tws_host,
                        settings.tws_port,
                        clientId=settings.tws_client_id,
                        timeout=settings.tws_connect_timeout_seconds,
                        readonly=settings.tws_read_only,
                    )
                except Exception:
                    if self._ib.isConnected():
                        try:
                            self._ib.disconnect()
                        except Exception:
                            pass
                    raise
                try:
                    self._ib.reqMarketDataType(settings.tws_market_data_type)
                except Exception as exc:
                    log.warning(
                        "reqMarketDataType(%s) failed after connect; session kept open: %s",
                        settings.tws_market_data_type,
                        exc,
                    )
        state = self.connection_state()
        state.message = "TWS read-only session connected" if state.broker_connected else "TWS connection failed"
        return state

    def disconnect(self) -> None:
        with self._lock:
            if self._ib.isConnected():
                self._ib.disconnect()

    def heartbeat(self) -> None:
        with self._lock:
            if self._ib.isConnected():
                self._ib.reqCurrentTime()

    def _resolve_underlying(self, symbol: str) -> Any | None:
        from ib_insync import Stock

        target = symbol.strip().upper()
        for primary in ("NASDAQ", ""):
            stock = Stock(target, "SMART", "USD")
            if primary:
                stock.primaryExchange = primary
            qualified = self._ib.qualifyContracts(stock)
            if qualified:
                return qualified[0]
        return None

    def qualify_stock(self, symbol: str) -> "StockContractInfo | None":
        from app.services.broker.base import StockContractInfo

        with self._lock:
            if not self._ib.isConnected():
                return None
            row = self._resolve_underlying(symbol)
            if not row:
                return None
            return StockContractInfo(
                symbol=symbol.strip().upper(),
                conid=int(row.conId),
                exchange=str(row.exchange or "SMART"),
                currency=str(row.currency or "USD"),
            )

    def market_snapshot(self, symbol: str) -> dict[str, Any] | None:
        with self._lock:
            if not self._ib.isConnected():
                return None
            underlying = self._resolve_underlying(symbol)
            if not underlying:
                return None
            ticker = self._ib.reqMktData(underlying, "", False, False)
            self._ib.sleep(2)
            last = _to_float(ticker.last or ticker.close or ticker.marketPrice(), 0.0)
            bid = _to_float(ticker.bid, max(0.01, last - 0.2) if last > 0 else 0.01)
            ask = _to_float(ticker.ask, max(bid + 0.01, last + 0.2) if last > 0 else 0.02)
            volume = max(0, int(_to_float(ticker.volume, 0.0)))
            self._ib.cancelMktData(underlying)
            if last <= 0:
                return None
            return {
                "ticker": symbol.strip().upper(),
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "last": round(last, 4),
                "bid": round(bid, 4),
                "ask": round(ask, 4),
                "volume": volume,
                "conid": int(underlying.conId),
            }

    def _fetch_all_option_chains(self, underlying: Any) -> list[Any]:
        raw = self._ib.reqSecDefOptParams(
            underlying.symbol,
            "",
            underlying.secType,
            underlying.conId,
        )
        return parse_secdef_option_chains(raw or [])

    def _option_from_spec(self, spec: dict[str, Any], exchange: str) -> Any:
        from ib_insync import Option

        return Option(
            spec["symbol"],
            spec["expiry"],
            spec["strike"],
            spec["right"],
            exchange,
            multiplier=str(spec.get("multiplier") or 100),
            tradingClass=spec.get("trading_class") or "",
            currency=spec.get("currency") or "USD",
        )

    def _qualify_options_with_exchange_fallback(
        self,
        specs: list[dict[str, Any]],
        *,
        preferred_exchanges: tuple[str, ...] = PREFERRED_OPTION_EXCHANGES,
    ) -> list[Any]:
        qualified: list[Any] = []
        for spec in specs:
            resolved = None
            for exchange in preferred_exchanges:
                candidate = self._option_from_spec(spec, exchange)
                rows = _qualified_options(self._ib.qualifyContracts(candidate))
                if rows:
                    resolved = rows[0]
                    break
            if resolved is not None:
                qualified.append(resolved)
        return qualified

    def _fetch_tickers_with_delayed_fallback(
        self,
        contracts: list[Any],
        *,
        wait_secs: float,
    ) -> tuple[list[Any], dict[int, str]]:
        if not contracts:
            return [], {}
        data_types: dict[int, str] = {}
        ticker_by_conid: dict[int, Any] = {}
        try:
            self._ib.reqMarketDataType(settings.tws_market_data_type or LIVE_MARKET_DATA_TYPE)
        except Exception as exc:
            log.warning("reqMarketDataType live failed: %s", exc)
        live_tickers = self._ib.reqTickers(*contracts)
        self._ib.sleep(wait_secs)
        missing: list[Any] = []
        for ticker in live_tickers:
            con_id = int(getattr(getattr(ticker, "contract", None), "conId", 0) or 0)
            ticker_by_conid[con_id] = ticker
            if _has_bid_ask(ticker):
                data_types[con_id] = "LIVE"
            else:
                missing.append(ticker.contract)
        if missing:
            try:
                self._ib.reqMarketDataType(DELAYED_MARKET_DATA_TYPE)
            except Exception as exc:
                log.warning("reqMarketDataType delayed failed: %s", exc)
            delayed_tickers = self._ib.reqTickers(*missing)
            self._ib.sleep(wait_secs)
            for ticker in delayed_tickers:
                con_id = int(getattr(getattr(ticker, "contract", None), "conId", 0) or 0)
                ticker_by_conid[con_id] = ticker
                data_types[con_id] = "DELAYED"
        for con_id, ticker in ticker_by_conid.items():
            if con_id not in data_types:
                data_types[con_id] = "LIVE" if _has_bid_ask(ticker) else "LIVE"
        return list(ticker_by_conid.values()), data_types

    def _expiry_dte(self, expiry: str) -> int:
        today = datetime.now(timezone.utc).date()
        try:
            return max(1, (datetime.fromisoformat(_parse_expiry(expiry)).date() - today).days)
        except ValueError:
            return 1

    def fetch_secdef_metadata(self, symbol: str) -> dict[str, Any] | None:
        cfg = settings.options_chain
        sym = symbol.strip().upper()
        diagnostics = ChainFetchDiagnostics(symbol=sym)

        with self._lock:
            if not self._ib.isConnected():
                return None
            underlying = self._resolve_underlying(sym)
            if not underlying:
                log.warning("option_chain_fetch %s: underlying qualify failed", sym)
                return None
            diagnostics.underlying_conid = int(underlying.conId)

            all_chains = self._fetch_all_option_chains(underlying)
            diagnostics.chains_returned = len(all_chains)
            if not all_chains:
                diagnostics.notes.append("reqSecDefOptParams returned no chains")
                diagnostics.log_summary()
                return None

            selected = select_option_chain(all_chains, symbol=sym)
            if not selected:
                diagnostics.notes.append("no matching chain for tradingClass/multiplier")
                diagnostics.log_summary()
                return None

            diagnostics.selected_exchange = selected.exchange
            diagnostics.selected_trading_class = selected.trading_class
            diagnostics.selected_multiplier = selected.multiplier

            snap = self.market_snapshot(sym)
            spot = float(snap["last"]) if snap else 0.0
            all_expiries_iso = sorted(_parse_expiry(exp) for exp in selected.expirations)
            all_strikes = sorted(float(s) for s in selected.strikes)

            filtered_expiries = filter_expiries_by_dte(
                all_expiries_iso,
                min_dte=int(cfg.min_dte),
                max_dte=int(cfg.max_dte),
            )
            filtered_strikes = filter_strikes_by_pct(
                all_strikes,
                spot=spot,
                pct=float(getattr(cfg, "strike_pct_range", 0.10) or 0.10),
            )
            diagnostics.selected_expiries = filtered_expiries
            if filtered_strikes:
                diagnostics.strike_low = min(filtered_strikes)
                diagnostics.strike_high = max(filtered_strikes)
            diagnostics.log_summary()

            return {
                "symbol": sym,
                "conid": diagnostics.underlying_conid,
                "exchange": selected.exchange,
                "trading_class": selected.trading_class,
                "multiplier": selected.multiplier,
                "expiries": filtered_expiries or all_expiries_iso,
                "strikes": filtered_strikes or all_strikes,
                "all_expiries": all_expiries_iso,
                "all_strikes": all_strikes,
                "chains_returned": diagnostics.chains_returned,
                "underlying_price": spot,
                "diagnostics": {
                    "underlying_conid": diagnostics.underlying_conid,
                    "chains_returned": diagnostics.chains_returned,
                    "selected_exchange": diagnostics.selected_exchange,
                    "selected_trading_class": diagnostics.selected_trading_class,
                    "selected_multiplier": diagnostics.selected_multiplier,
                    "selected_expiries": diagnostics.selected_expiries,
                    "strike_low": diagnostics.strike_low,
                    "strike_high": diagnostics.strike_high,
                },
            }

    def fetch_expiry_quotes(
        self,
        *,
        symbol: str,
        expiry: str,
        strikes: list[float],
        exchange: str = "SMART",
        trading_class: str | None = None,
        multiplier: int = 100,
    ) -> list[dict[str, Any]]:
        cfg = settings.options_chain
        sym = symbol.strip().upper()
        diagnostics = ChainFetchDiagnostics(symbol=sym)
        wait_secs = float(getattr(cfg, "quote_tick_wait_seconds", 3) or 3)
        batch_size = int(getattr(cfg, "quote_batch_size", 40) or 40)
        strikes_per_batch = max(1, batch_size // 2)
        dte = self._expiry_dte(expiry)
        expiry_iso = _parse_expiry(expiry)
        tc = (trading_class or sym).upper()

        with self._lock:
            if not self._ib.isConnected() or not strikes:
                return []

            all_rows: list[dict[str, Any]] = []
            for start in range(0, len(strikes), strikes_per_batch):
                chunk = strikes[start : start + strikes_per_batch]
                specs = build_option_contract_specs(
                    symbol=sym,
                    expiry=expiry,
                    strikes=chunk,
                    exchange=exchange,
                    trading_class=tc,
                    multiplier=multiplier,
                )
                diagnostics.contracts_built += len(specs)
                qualified_opts = self._qualify_options_with_exchange_fallback(specs)
                diagnostics.contracts_qualified += len(qualified_opts)
                if not qualified_opts:
                    log.warning(
                        "option_chain_fetch %s expiry=%s: 0/%s contracts qualified (check exchange/tradingClass)",
                        sym,
                        expiry_iso,
                        len(specs),
                    )
                    continue

                tickers, data_types = self._fetch_tickers_with_delayed_fallback(
                    qualified_opts,
                    wait_secs=wait_secs,
                )
                for ticker in tickers:
                    con_id = int(getattr(getattr(ticker, "contract", None), "conId", 0) or 0)
                    data_type = data_types.get(con_id, "LIVE")
                    if _has_bid_ask(ticker):
                        diagnostics.contracts_with_bid_ask += 1
                        if data_type == "DELAYED":
                            diagnostics.delayed_quotes += 1
                        else:
                            diagnostics.live_quotes += 1
                    else:
                        diagnostics.contracts_missing_quotes += 1

                batch_rows = _ticker_rows_from_qualified(
                    tickers,
                    symbol=sym,
                    expiry=expiry_iso,
                    dte=dte,
                    data_types=data_types,
                )
                all_rows.extend(batch_rows)

            diagnostics.selected_expiries = [expiry_iso]
            if strikes:
                diagnostics.strike_low = min(strikes)
                diagnostics.strike_high = max(strikes)
            if diagnostics.contracts_missing_quotes and diagnostics.contracts_with_bid_ask == 0:
                diagnostics.notes.append(
                    "no bid/ask — check market data permissions or try off-hours delayed/frozen data"
                )
            diagnostics.log_summary()
            return all_rows

    def fetch_exact_option_quotes(
        self,
        *,
        symbol: str,
        contracts: list[dict[str, Any]],
        trading_class: str | None = None,
        multiplier: int = 100,
    ) -> list[dict[str, Any]]:
        """Qualify and quote specific option contracts (smoke test / known positions)."""
        cfg = settings.options_chain
        sym = symbol.strip().upper()
        tc = (trading_class or sym).upper()
        wait_secs = float(getattr(cfg, "quote_tick_wait_seconds", 3) or 3)
        results: list[dict[str, Any]] = []

        with self._lock:
            if not self._ib.isConnected():
                return [{"qualified": False, "error": "tws_disconnected", **c} for c in contracts]

            for raw in contracts:
                expiry = _expiry_compact(str(raw.get("expiry") or ""))
                strike = float(raw.get("strike") or 0)
                right = str(raw.get("right") or "C").upper()[0]
                spec = {
                    "symbol": sym,
                    "expiry": expiry,
                    "strike": strike,
                    "right": right,
                    "trading_class": tc,
                    "multiplier": multiplier,
                    "currency": "USD",
                }
                qualified = self._qualify_options_with_exchange_fallback([spec])
                if not qualified:
                    results.append(
                        {
                            **raw,
                            "symbol": sym,
                            "expiry": _parse_expiry(expiry),
                            "strike": strike,
                            "right": right,
                            "qualified": False,
                            "error": "qualify_failed",
                        }
                    )
                    continue

                contract = qualified[0]
                tickers, data_types = self._fetch_tickers_with_delayed_fallback(
                    [contract],
                    wait_secs=wait_secs,
                )
                if not tickers:
                    results.append(
                        {
                            **raw,
                            "symbol": sym,
                            "expiry": _parse_expiry(expiry),
                            "strike": strike,
                            "right": right,
                            "qualified": True,
                            "conid": int(contract.conId),
                            "error": "no_ticker",
                        }
                    )
                    continue

                ticker = tickers[0]
                con_id = int(getattr(contract, "conId", 0) or 0)
                data_type = data_types.get(con_id, "LIVE")
                bid = _to_float(getattr(ticker, "bid", None), 0.0)
                ask = _to_float(getattr(ticker, "ask", None), 0.0)
                last = _to_float(getattr(ticker, "last", None) or getattr(ticker, "close", None), 0.0)
                greeks = getattr(ticker, "modelGreeks", None)
                greek_snap = _model_greeks_snapshot(greeks)
                has_quote = bid > 0 or ask > 0 or last > 0
                results.append(
                    {
                        "symbol": sym,
                        "expiry": _parse_expiry(expiry),
                        "strike": strike,
                        "right": right,
                        "qualified": True,
                        "conid": con_id,
                        "exchange": str(getattr(contract, "exchange", "") or ""),
                        "bid": round(bid, 4),
                        "ask": round(ask, 4),
                        "last": round(last, 4) if last > 0 else None,
                        "data_type": data_type,
                        "model_greeks": greek_snap,
                        "has_quote": has_quote,
                        "error": None if has_quote else "missing_market_data",
                    }
                )
        return results

    def option_chain(self, *, symbol: str, last_price: float) -> tuple[list[dict[str, Any]], "ChainSource", str]:
        from app.services.broker.base import ChainSource

        with self._lock:
            if not self._ib.isConnected():
                return [], "none", "tws_disconnected"

        meta = self.fetch_secdef_metadata(symbol)
        if not meta:
            return [], "none", "no_secdef_opt"

        expiries = meta.get("expiries") or []
        strikes = meta.get("strikes") or []
        if not expiries or not strikes:
            return [], "none", "empty_chain"

        cfg = settings.options_chain
        pct = float(getattr(cfg, "strike_pct_range", 0.10) or 0.10)
        bounded_strikes = filter_strikes_by_pct(strikes, spot=last_price, pct=pct)
        if not bounded_strikes:
            bounded_strikes = strikes

        atm = min(bounded_strikes, key=lambda s: abs(s - last_price))
        idx = bounded_strikes.index(atm)
        window = bounded_strikes[max(0, idx - 2) : min(len(bounded_strikes), idx + 3)]

        expiry = expiries[0]
        rows = self.fetch_expiry_quotes(
            symbol=symbol,
            expiry=expiry,
            strikes=window,
            exchange=str(meta.get("exchange") or "SMART"),
            trading_class=str(meta.get("trading_class") or symbol),
            multiplier=int(meta.get("multiplier") or 100),
        )
        if not rows:
            return [], "none", "empty_option_ticks"
        return rows, "broker", "tws_secdef_opt"

    def list_positions(self) -> list[dict[str, Any]]:
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            if not self._ib.isConnected():
                return []
            raw = self._ib.managedAccounts()
            if isinstance(raw, (list, tuple)):
                return [str(a).strip() for a in raw if str(a).strip()]
            return [a.strip() for a in str(raw).split(",") if a.strip()]

    def list_executions(self) -> list[dict[str, Any]]:
        with self._lock:
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
