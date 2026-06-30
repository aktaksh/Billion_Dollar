from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

ChainSource = Literal["broker", "mock", "none"]


@dataclass
class BrokerConnectionState:
    tws_reachable: bool = False
    broker_connected: bool = False
    broker_authenticated: bool = False
    read_only: bool = True
    tws_host: str = "127.0.0.1"
    tws_port: int = 7497
    tws_client_id: int = 1
    message: str = ""
    checked_at: str = ""


@dataclass
class StockContractInfo:
    symbol: str
    conid: int
    exchange: str = "SMART"
    currency: str = "USD"


class BrokerClient(Protocol):
    """Read-only broker interface. No order placement methods."""

    def connection_state(self) -> BrokerConnectionState: ...

    def connect(self) -> BrokerConnectionState: ...

    def disconnect(self) -> None: ...

    def heartbeat(self) -> None: ...

    def qualify_stock(self, symbol: str) -> StockContractInfo | None: ...

    def market_snapshot(self, symbol: str) -> dict[str, Any] | None: ...

    def option_chain(self, *, symbol: str, last_price: float) -> tuple[list[dict[str, Any]], ChainSource, str]: ...

    def fetch_secdef_metadata(self, symbol: str) -> dict[str, Any] | None: ...

    def fetch_expiry_quotes(
        self,
        *,
        symbol: str,
        expiry: str,
        strikes: list[float],
        exchange: str = "SMART",
        trading_class: str | None = None,
        multiplier: int = 100,
    ) -> list[dict[str, Any]]: ...

    def fetch_exact_option_quotes(
        self,
        *,
        symbol: str,
        contracts: list[dict[str, Any]],
        trading_class: str | None = None,
        multiplier: int = 100,
    ) -> list[dict[str, Any]]: ...

    def list_positions(self) -> list[dict[str, Any]]: ...

    def list_open_orders(self) -> list[dict[str, Any]]: ...

    def list_executions(self) -> list[dict[str, Any]]: ...

    def list_accounts(self) -> list[str]: ...
