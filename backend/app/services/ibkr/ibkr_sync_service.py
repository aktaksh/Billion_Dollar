from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from sqlalchemy.engine import Engine

from app.repositories.paper_trade_repository import PaperTradeRepository
from app.services.broker.broker_provider import AutoBrokerProvider, get_broker_provider
from app.services.ibkr.spread_matcher import MatchedSpread, SpreadMatcher
from app.services.ibkr.spread_valuation_service import SpreadValuationService
from app.services.paper_trade_service import PaperTradeService
from app.services.pnl_calculator import is_expired
from app.utils.expiry_format import normalize_expiry_iso

logger = logging.getLogger(__name__)


class IBKRSyncService:
    def __init__(self, engine: Engine, paper_service: PaperTradeService) -> None:
        self.repo = PaperTradeRepository(engine)
        self.paper_service = paper_service
        self.matcher = SpreadMatcher()
        self.valuation = SpreadValuationService()
        self._broker = get_broker_provider()

    def _active_backend(self) -> str:
        if isinstance(self._broker, AutoBrokerProvider):
            return self._broker.active_name
        return self._broker.name

    def broker_status(self) -> dict[str, Any]:
        ok, message = self._broker.is_available()
        return {"available": ok, "backend": self._active_backend() if ok else "none", "message": message}

    gateway_status = broker_status

    def _enrich_with_quotes(self, spreads: list[MatchedSpread]) -> int:
        return self._broker.enrich_spreads_with_quotes(spreads)

    def _value_spread(self, spread: MatchedSpread, underlying: float = 0.0) -> dict[str, Any]:
        long_mid = float(spread.long_leg.mkt_price or spread.long_leg.last or 0)
        short_mid = float(spread.short_leg.mkt_price or spread.short_leg.last or 0)
        val = self.valuation.value_spread(
            strategy_type=spread.strategy_type,
            long_strike=spread.long_strike,
            short_strike=spread.short_strike,
            quantity=spread.quantity,
            entry_debit=spread.entry_debit,
            entry_credit=spread.entry_credit,
            long_mid=long_mid,
            short_mid=short_mid,
            underlying_price=underlying,
            expiry=spread.expiry,
            is_debit=spread.is_debit,
        )
        out = asdict(val)
        if spread.unrealized_pnl and not out.get("unrealized_pnl"):
            out["unrealized_pnl"] = spread.unrealized_pnl
        return out

    def _value_trade_from_quotes(self, trade: dict[str, Any], quotes: dict[str, dict[str, Any]]) -> dict[str, Any]:
        long_q = quotes.get("long") or {}
        short_q = quotes.get("short") or {}
        long_mid = float(long_q.get("mid") or trade.get("long_mid") or 0)
        short_mid = float(short_q.get("mid") or trade.get("short_mid") or 0)
        symbol = str(trade["symbol"]).upper()
        underlying = float(trade.get("current_underlying_price") or 0)
        if underlying <= 0:
            underlying = self._broker.fetch_underlying_price(symbol)
        is_debit = "Bull Call" in trade["strategy_type"] or "Bear Put" in trade["strategy_type"]
        val = self.valuation.value_spread(
            strategy_type=trade["strategy_type"],
            long_strike=float(trade["long_strike"]),
            short_strike=float(trade["short_strike"]),
            quantity=int(trade.get("quantity") or 1),
            entry_debit=trade.get("entry_debit"),
            entry_credit=trade.get("entry_credit"),
            long_mid=long_mid,
            short_mid=short_mid,
            underlying_price=underlying,
            expiry=trade["expiry_date"],
            is_debit=is_debit if trade.get("entry_credit") is None else None,
        )
        out = asdict(val)
        out["long_bid"] = long_q.get("bid")
        out["long_ask"] = long_q.get("ask")
        out["long_mid"] = long_mid
        out["short_bid"] = short_q.get("bid")
        out["short_ask"] = short_q.get("ask")
        out["short_mid"] = short_mid
        return out

    def fetch_open_positions(self) -> dict[str, Any]:
        ok, msg = self._broker.is_available()
        if not ok:
            return self._fail_result("fetch_open_positions", msg)
        positions = self._broker.list_option_positions()
        spreads = self.matcher.match(positions)
        failed = self._enrich_with_quotes(spreads)
        new_trades = 0
        updated = 0
        for sp in spreads:
            underlying = self._broker.fetch_underlying_price(sp.symbol)
            val = self._value_spread(sp, underlying)
            _trade, created = self.repo.upsert_from_ibkr_spread(sp, valuation=val)
            if created:
                new_trades += 1
            else:
                updated += 1
        result = {
            "action": "fetch_open_positions",
            "records_updated": updated,
            "new_trades": new_trades,
            "closed_trades": 0,
            "failed_requests": failed,
            "spreads_matched": len(spreads),
            "backend": self._active_backend(),
            "message": f"Matched {len(spreads)} spreads via {self._active_backend()}",
        }
        self.repo.write_sync_log(action="fetch_open_positions", result=result)
        return result

    def refresh_market_prices(self) -> dict[str, Any]:
        ok, msg = self._broker.is_available()
        if not ok:
            return self._fail_result("refresh_market_prices", msg)
        open_trades = self.paper_service.list_trades(status="OPEN")
        if not open_trades:
            return {"action": "refresh_market_prices", "records_updated": 0, "message": "No open trades", "backend": self._active_backend()}
        quotes_by_trade = self._broker.fetch_quotes_for_trades(open_trades)
        failed = 0 if quotes_by_trade else (1 if open_trades else 0)
        updated = 0
        for trade in open_trades:
            tid = str(trade["id"])
            quotes = quotes_by_trade.get(tid)
            if not quotes:
                failed += 1
                continue
            val = self._value_trade_from_quotes(trade, quotes)
            self.repo.update_valuation(tid, val)
            updated += 1
        result = {
            "action": "refresh_market_prices",
            "records_updated": updated,
            "new_trades": 0,
            "closed_trades": 0,
            "failed_requests": failed,
            "backend": self._active_backend(),
            "message": f"Refreshed live quotes for {updated} trades via {self._active_backend()}",
        }
        self.repo.write_sync_log(action="refresh_market_prices", result=result)
        return result

    def recalculate_all(self) -> dict[str, Any]:
        open_trades = self.paper_service.list_trades(status="OPEN")
        updated = 0
        for trade in open_trades:
            long_mid = float(trade.get("long_mid") or 0)
            short_mid = float(trade.get("short_mid") or 0)
            if long_mid <= 0 and trade.get("entry_debit"):
                long_mid = float(trade.get("entry_debit") or 0)
            if short_mid <= 0 and long_mid > 0:
                short_mid = max(0.01, long_mid * 0.5)
            val = self.valuation.value_spread(
                strategy_type=trade["strategy_type"],
                long_strike=float(trade["long_strike"]),
                short_strike=float(trade["short_strike"]),
                quantity=int(trade.get("quantity") or 1),
                entry_debit=trade.get("entry_debit"),
                entry_credit=trade.get("entry_credit"),
                long_mid=long_mid,
                short_mid=short_mid,
                underlying_price=float(trade.get("current_underlying_price") or trade.get("underlying_price_at_entry") or 0),
                expiry=trade["expiry_date"],
            )
            self.repo.update_valuation(trade["id"], asdict(val))
            updated += 1
        result = {
            "action": "recalculate_all",
            "records_updated": updated,
            "new_trades": 0,
            "closed_trades": 0,
            "failed_requests": 0,
            "backend": self._active_backend(),
            "message": f"Recalculated {updated} open spreads",
        }
        self.repo.write_sync_log(action="recalculate_all", result=result)
        return result

    def sync_from_ibkr(self) -> dict[str, Any]:
        ok, msg = self._broker.is_available()
        if not ok:
            return self._fail_result("sync_from_ibkr", msg)
        fetch_result = self.fetch_open_positions()
        if fetch_result.get("failed_requests", 0) and fetch_result.get("spreads_matched", 0) == 0 and fetch_result.get("new_trades", 0) == 0:
            return fetch_result
        positions = self._broker.list_option_positions()
        matched = self.matcher.match(positions)
        matched_keys = {s.ibkr_sync_key for s in matched}
        closed = 0
        for trade in self.repo.list_open_ibkr_trades():
            if trade.get("ibkr_sync_key") and trade["ibkr_sync_key"] not in matched_keys:
                self.repo.mark_closed(trade["id"], reason="Position closed on IBKR")
                closed += 1
            elif is_expired(normalize_expiry_iso(trade.get("expiry_date"))):
                self.paper_service.close_trade(trade["id"], "Expired")
                closed += 1
        refresh = self.refresh_market_prices()
        result = {
            "action": "sync_from_ibkr",
            "records_updated": int(fetch_result.get("records_updated", 0)) + int(refresh.get("records_updated", 0)),
            "new_trades": int(fetch_result.get("new_trades", 0)),
            "closed_trades": closed,
            "failed_requests": int(fetch_result.get("failed_requests", 0)) + int(refresh.get("failed_requests", 0)),
            "spreads_matched": len(matched),
            "backend": self._active_backend(),
            "message": f"Sync complete — {len(matched)} spreads, {closed} closed via {self._active_backend()}",
        }
        self.repo.write_sync_log(action="sync_from_ibkr", result=result)
        return result

    def _fail_result(self, action: str, message: str, *, failed_requests: int = 1) -> dict[str, Any]:
        result = {
            "action": action,
            "records_updated": 0,
            "new_trades": 0,
            "closed_trades": 0,
            "failed_requests": failed_requests,
            "gateway_available": False,
            "backend": "none",
            "message": message,
        }
        self.repo.write_sync_log(action=action, result=result)
        return result

    def get_sync_status(self) -> dict[str, Any]:
        broker = self.broker_status()
        latest = self.repo.latest_sync_log()
        return {
            "gateway": broker,
            "broker": broker,
            "last_sync": latest,
        }
