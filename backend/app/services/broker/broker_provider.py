from __future__ import annotations

from typing import Any, Protocol

from app.config import settings
from app.services.broker.ibkr_gateway import IbkrGatewayClient, IbkrGatewayConfig
from app.services.broker.tws_broker import TwsBroker


class BrokerProvider(Protocol):
    name: str

    def is_available(self) -> tuple[bool, str]: ...

    def list_option_positions(self) -> list[dict[str, Any]]: ...

    def fetch_quotes_for_trades(self, trades: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]: ...

    def fetch_underlying_price(self, symbol: str) -> float: ...

    def enrich_spreads_with_quotes(self, spreads: list[Any]) -> int:
        """Return failed request count."""
        ...


class TwsBrokerProvider:
    name = "tws"

    def __init__(self) -> None:
        self._broker = TwsBroker()

    def is_available(self) -> tuple[bool, str]:
        return self._broker.is_available()

    def list_option_positions(self) -> list[dict[str, Any]]:
        return self._broker.list_option_positions()

    def fetch_quotes_for_trades(self, trades: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
        return self._broker.fetch_quotes_for_trades(trades)

    def fetch_underlying_price(self, symbol: str) -> float:
        return self._broker.fetch_underlying_price(symbol)

    def enrich_spreads_with_quotes(self, spreads: list[Any]) -> int:
        if not spreads:
            return 0
        legs: list[dict[str, Any]] = []
        leg_to_spread: dict[str, Any] = {}
        for sp in spreads:
            for side, leg in ("long", sp.long_leg), ("short", sp.short_leg):
                key = f"{sp.ibkr_sync_key}|{side}"
                legs.append({
                    "leg_key": key,
                    "symbol": leg.symbol,
                    "expiry": leg.expiry,
                    "strike": leg.strike,
                    "right": leg.right,
                })
                leg_to_spread[key] = (sp, side)
        quotes = self._broker.fetch_leg_quotes(legs)
        if not quotes:
            return 1 if legs else 0
        for key, data in quotes.items():
            sp, side = leg_to_spread[key]
            target = sp.long_leg if side == "long" else sp.short_leg
            target.bid = data.get("bid")
            target.ask = data.get("ask")
            target.last = data.get("last")
            target.mkt_price = data.get("mid") or target.mkt_price
            target.iv = data.get("iv")
            target.delta = data.get("delta")
            target.gamma = data.get("gamma")
            target.theta = data.get("theta")
            target.vega = data.get("vega")
            if data.get("conId"):
                target.conid = int(data["conId"])
        return 0


class CpGatewayProvider:
    name = "cp_gateway"

    def __init__(self) -> None:
        self._client = IbkrGatewayClient(
            IbkrGatewayConfig(
                base_url=settings.ibkr_gateway_base_url,
                timeout_seconds=settings.ibkr_gateway_timeout_seconds,
                verify_tls=settings.ibkr_gateway_verify_tls,
            )
        )

    def is_available(self) -> tuple[bool, str]:
        ok, msg = self._client.is_available()
        if ok:
            return True, f"CP Gateway authenticated ({settings.ibkr_gateway_base_url})"
        return False, msg

    def _account_id(self) -> str | None:
        accounts = self._client.list_accounts()
        if not accounts:
            return settings.ibkr_default_account or None
        first = accounts[0]
        if isinstance(first, dict):
            return str(first.get("accountId") or first.get("id") or first.get("account") or "")
        return str(first)

    def list_option_positions(self) -> list[dict[str, Any]]:
        account_id = self._account_id()
        if not account_id:
            return []
        return self._client.list_all_positions(account_id)

    def fetch_quotes_for_trades(self, trades: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
        conid_map: dict[int, tuple[str, str]] = {}
        for trade in trades:
            tid = str(trade["id"])
            if trade.get("long_con_id"):
                conid_map[int(trade["long_con_id"])] = (tid, "long")
            if trade.get("short_con_id"):
                conid_map[int(trade["short_con_id"])] = (tid, "short")
        if not conid_map:
            return {}
        try:
            snaps = self._client.market_snapshot(list(conid_map.keys()))
        except Exception:
            return {}
        from app.services.ibkr.spread_valuation_service import SpreadValuationService

        val_svc = SpreadValuationService()
        out: dict[str, dict[str, dict[str, Any]]] = {}
        for snap in snaps:
            cid = int(snap.get("conid") or snap.get("conId") or 0)
            if cid not in conid_map:
                continue
            tid, side = conid_map[cid]
            data = val_svc.apply_market_snapshot({}, snap)
            out.setdefault(tid, {})[side] = data
        return out

    def fetch_underlying_price(self, symbol: str) -> float:
        return 0.0

    def enrich_spreads_with_quotes(self, spreads: list[Any]) -> int:
        conids: list[int] = []
        mapping: dict[int, tuple[Any, str]] = {}
        for sp in spreads:
            if sp.long_leg.conid:
                conids.append(sp.long_leg.conid)
                mapping[sp.long_leg.conid] = (sp, "long")
            if sp.short_leg.conid:
                conids.append(sp.short_leg.conid)
                mapping[sp.short_leg.conid] = (sp, "short")
        if not conids:
            return 0
        try:
            snaps = self._client.market_snapshot(conids)
        except Exception:
            return 1
        from app.services.ibkr.spread_valuation_service import SpreadValuationService

        val_svc = SpreadValuationService()
        by_conid = {int(s.get("conid") or s.get("conId") or 0): s for s in snaps if s}
        for cid, (sp, side) in mapping.items():
            if cid not in by_conid:
                continue
            data = val_svc.apply_market_snapshot({}, by_conid[cid])
            target = sp.long_leg if side == "long" else sp.short_leg
            target.bid = data.get("bid")
            target.ask = data.get("ask")
            target.last = data.get("last")
            target.mkt_price = data.get("mid") or target.mkt_price
            target.iv = data.get("iv")
            target.delta = data.get("delta")
        return 0


class AutoBrokerProvider:
    """Try TWS first, then CP Gateway."""

    name = "auto"

    def __init__(self) -> None:
        self._tws = TwsBrokerProvider()
        self._cp = CpGatewayProvider()
        self._active: BrokerProvider | None = None

    @property
    def active(self) -> BrokerProvider | None:
        return self._active

    @property
    def active_name(self) -> str:
        return self._active.name if self._active else "none"

    def _resolve(self) -> BrokerProvider | None:
        if settings.ibkr_broker_backend == "tws":
            if self._tws.is_available()[0]:
                self._active = self._tws
                return self._tws
            self._active = None
            return None
        if settings.ibkr_broker_backend == "cp_gateway":
            if self._cp.is_available()[0]:
                self._active = self._cp
                return self._cp
            self._active = None
            return None
        ok, _ = self._tws.is_available()
        if ok:
            self._active = self._tws
            return self._tws
        ok, _ = self._cp.is_available()
        if ok:
            self._active = self._cp
            return self._cp
        self._active = None
        return None

    def is_available(self) -> tuple[bool, str]:
        provider = self._resolve()
        if provider:
            ok, msg = provider.is_available()
            return ok, msg
        return False, (
            f"No broker available — start IB Gateway/TWS on {settings.tws_host}:{settings.tws_port} "
            f"(same as Spread Analyzer) or CP Gateway on port 5000"
        )

    def list_option_positions(self) -> list[dict[str, Any]]:
        provider = self._resolve()
        return provider.list_option_positions() if provider else []

    def fetch_quotes_for_trades(self, trades: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
        provider = self._resolve()
        return provider.fetch_quotes_for_trades(trades) if provider else {}

    def fetch_underlying_price(self, symbol: str) -> float:
        provider = self._resolve()
        return provider.fetch_underlying_price(symbol) if provider else 0.0

    def enrich_spreads_with_quotes(self, spreads: list[Any]) -> int:
        provider = self._resolve()
        return provider.enrich_spreads_with_quotes(spreads) if provider else 1


def get_broker_provider() -> AutoBrokerProvider | TwsBrokerProvider | CpGatewayProvider:
    mode = settings.ibkr_broker_backend.lower()
    if mode == "tws":
        return TwsBrokerProvider()
    if mode == "cp_gateway":
        return CpGatewayProvider()
    return AutoBrokerProvider()
