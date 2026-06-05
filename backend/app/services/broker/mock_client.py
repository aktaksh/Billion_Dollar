from __future__ import annotations

from datetime import UTC, datetime
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

    def list_positions(self) -> list[dict[str, Any]]:
        return []

    def list_open_orders(self) -> list[dict[str, Any]]:
        return []

    def list_executions(self) -> list[dict[str, Any]]:
        return []

    def list_accounts(self) -> list[str]:
        return ["DU000000"] if self._connected else []
