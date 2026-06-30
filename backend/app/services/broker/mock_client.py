from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.engines.ingestion_engine import build_mock_option_chain
from app.services.broker.base import BrokerConnectionState, ChainSource, StockContractInfo


class MockBrokerClient:
    """In-memory broker for CI and local dev without TWS."""

    _connected: bool = False

    def connection_state(self) -> BrokerConnectionState:
        now = datetime.now(UTC).isoformat()
        connected = self._connected
        return BrokerConnectionState(
            tws_reachable=connected,
            broker_connected=connected,
            broker_authenticated=connected,
            read_only=True,
            tws_host=settings.tws_host,
            tws_port=settings.tws_port,
            tws_client_id=settings.tws_client_id,
            message="mock broker connected" if connected else "mock broker disconnected",
            checked_at=now,
        )

    def connect(self) -> BrokerConnectionState:
        MockBrokerClient._connected = True
        return self.connection_state()

    def disconnect(self) -> None:
        MockBrokerClient._connected = False

    def heartbeat(self) -> None:
        return None

    def qualify_stock(self, symbol: str) -> StockContractInfo | None:
        if not self._connected:
            return None
        return StockContractInfo(symbol=symbol.upper(), conid=1)

    def market_snapshot(self, symbol: str) -> dict[str, Any] | None:
        if not self._connected:
            return None
        sym = symbol.upper()
        base = {"QQQ": 480.0, "SPY": 540.0, "AAPL": 220.0}.get(sym, 100.0)
        return {
            "ticker": sym,
            "captured_at": datetime.now(UTC).isoformat(),
            "last": base,
            "bid": round(base - 0.05, 4),
            "ask": round(base + 0.05, 4),
            "volume": 1_000_000,
            "conid": 1,
        }

    def option_chain(self, *, symbol: str, last_price: float) -> tuple[list[dict[str, Any]], ChainSource, str]:
        if not self._connected:
            return [], "none", "mock_disconnected"
        return build_mock_option_chain(ticker=symbol, last_price=last_price), "mock", "mock_chain"

    def fetch_secdef_metadata(self, symbol: str) -> dict[str, Any] | None:
        if not self._connected:
            return None
        sym = symbol.upper()
        snap = self.market_snapshot(sym)
        last = float(snap["last"]) if snap else 700.0
        strikes = [round(last + offset, 0) for offset in range(-80, 81, 5)]
        today = datetime.now(timezone.utc).date()
        expiries = [(today + timedelta(days=dte)).isoformat() for dte in (21, 28, 35, 42)]
        return {
            "symbol": sym,
            "exchange": "SMART",
            "trading_class": sym,
            "multiplier": 100,
            "expiries": expiries,
            "strikes": strikes,
            "conid": 1,
            "chains_returned": 1,
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
        del exchange, trading_class, multiplier
        if not self._connected or not strikes:
            return []
        snap = self.market_snapshot(symbol)
        last = float(snap["last"]) if snap else 700.0
        today = datetime.now(timezone.utc).date()
        try:
            dte = max(1, (datetime.fromisoformat(expiry).date() - today).days)
        except ValueError:
            dte = 28
        rows: list[dict[str, Any]] = []
        for strike in strikes:
            m = abs(strike - last) / max(last, 1.0)
            for option_type, delta_base in (("call", 0.62), ("put", -0.62)):
                mid = max(0.5, last * (0.022 - m * 0.008))
                bid = round(mid * 0.97, 4)
                ask = round(mid * 1.03, 4)
                rows.append(
                    {
                        "symbol": symbol.upper(),
                        "expiry": expiry,
                        "dte": dte,
                        "option_type": option_type,
                        "strike": round(float(strike), 2),
                        "bid": bid,
                        "ask": ask,
                        "last": round(mid, 4),
                        "mid": round(mid, 4),
                        "volume": int(800 + (1 - m) * 400),
                        "open_interest": int(2000 + (1 - m) * 800),
                        "delta": round(delta_base - (m * 1.1), 3),
                        "gamma": 0.018,
                        "theta": -0.07,
                        "vega": 0.17,
                        "iv": round(0.24 + m * 0.1, 4),
                        "implied_vol": round(0.24 + m * 0.1, 4),
                        "data_type": "LIVE",
                    }
                )
        return rows

    def fetch_exact_option_quotes(
        self,
        *,
        symbol: str,
        contracts: list[dict[str, Any]],
        trading_class: str | None = None,
        multiplier: int = 100,
    ) -> list[dict[str, Any]]:
        del trading_class, multiplier
        if not self._connected:
            return [{"qualified": False, "error": "mock_disconnected", **c} for c in contracts]
        out: list[dict[str, Any]] = []
        for raw in contracts:
            strike = float(raw.get("strike") or 0)
            right = str(raw.get("right") or "C").upper()[0]
            expiry = str(raw.get("expiry") or "")
            out.append(
                {
                    "symbol": symbol.upper(),
                    "expiry": expiry,
                    "strike": strike,
                    "right": right,
                    "qualified": True,
                    "conid": 1,
                    "bid": 10.0,
                    "ask": 10.5,
                    "last": 10.25,
                    "data_type": "LIVE",
                    "has_quote": True,
                    "error": None,
                }
            )
        return out

    def list_positions(self) -> list[dict[str, Any]]:
        return []

    def list_open_orders(self) -> list[dict[str, Any]]:
        return []

    def list_executions(self) -> list[dict[str, Any]]:
        return []

    def list_accounts(self) -> list[str]:
        return ["DU000000"] if self._connected else []
