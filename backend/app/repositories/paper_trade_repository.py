from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine

from app.db import paper_trade_snapshots, paper_trade_sync_logs, paper_trades
from app.services.ibkr.spread_matcher import MatchedSpread
from app.utils.expiry_format import dte_from_expiry, normalize_expiry_iso


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class PaperTradeRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def find_by_sync_key(self, sync_key: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(paper_trades).where(paper_trades.c.ibkr_sync_key == sync_key)
            ).first()
            return dict(row._mapping) if row else None

    def list_open_ibkr_trades(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(paper_trades).where(
                    paper_trades.c.status == "OPEN",
                    paper_trades.c.source == "ibkr",
                )
            ).fetchall()
            return [dict(r._mapping) for r in rows]

    def upsert_from_ibkr_spread(self, spread: MatchedSpread, *, valuation: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        existing = self.find_by_sync_key(spread.ibkr_sync_key)
        now = _now()
        expiry = normalize_expiry_iso(spread.expiry)
        ibkr_json = {
            "long_leg": spread.long_leg.raw,
            "short_leg": spread.short_leg.raw,
            "matched": {
                "strategy": spread.strategy_type,
                "quantity": spread.quantity,
            },
        }
        values = {
            "symbol": spread.symbol,
            "underlying_price_at_entry": valuation.get("underlying_price") or 0,
            "strategy_type": spread.strategy_type,
            "expiry_date": expiry,
            "days_to_entry_dte": dte_from_expiry(expiry),
            "long_strike": spread.long_strike,
            "short_strike": spread.short_strike,
            "long_option_type": spread.long_option_type,
            "short_option_type": spread.short_option_type,
            "entry_debit": spread.entry_debit,
            "entry_credit": spread.entry_credit,
            "quantity": spread.quantity,
            "max_profit": valuation.get("max_profit") or 0,
            "max_loss": valuation.get("max_loss") or 0,
            "breakeven": valuation.get("breakeven") or 0,
            "status": "OPEN",
            "current_underlying_price": valuation.get("underlying_price"),
            "current_spread_value": valuation.get("current_spread_value"),
            "unrealized_pnl": valuation.get("unrealized_pnl"),
            "percent_return": valuation.get("percent_return"),
            "highest_profit_seen": valuation.get("unrealized_pnl"),
            "largest_drawdown": min(0.0, float(valuation.get("unrealized_pnl") or 0)),
            "last_marked_at": now,
            "source": "ibkr",
            "ibkr_sync_key": spread.ibkr_sync_key,
            "long_con_id": spread.long_leg.conid,
            "short_con_id": spread.short_leg.conid,
            "average_cost": spread.average_cost,
            "market_value": spread.market_value,
            "today_pnl": spread.today_pnl,
            "long_bid": spread.long_leg.bid,
            "long_ask": spread.long_leg.ask,
            "long_mid": spread.long_leg.mkt_price or valuation.get("long_mid"),
            "short_bid": spread.short_leg.bid,
            "short_ask": spread.short_leg.ask,
            "short_mid": spread.short_leg.mkt_price or valuation.get("short_mid"),
            "max_profit_remaining": valuation.get("max_profit_remaining"),
            "progress_pct": valuation.get("distance_to_max_profit_pct"),
            "breakeven_distance": valuation.get("breakeven_distance"),
            "distance_to_long_strike": valuation.get("distance_to_long_strike"),
            "distance_to_short_strike": valuation.get("distance_to_short_strike"),
            "ibkr_position_json": ibkr_json,
            "broker_status": "synced",
            "reason_for_trade": f"Synced from IBKR — {spread.strategy_type}",
        }
        if existing:
            trade_id = existing["id"]
            with self.engine.begin() as conn:
                conn.execute(update(paper_trades).where(paper_trades.c.id == trade_id).values(**values))
                conn.execute(
                    insert(paper_trade_snapshots).values(
                        id=_new_id(),
                        trade_id=trade_id,
                        marked_at=now,
                        underlying_price=values["current_underlying_price"],
                        spread_value=values["current_spread_value"],
                        unrealized_pnl=values["unrealized_pnl"],
                        percent_return=values["percent_return"],
                        snapshot_json={"source": "ibkr_sync"},
                    )
                )
            return self.find_by_sync_key(spread.ibkr_sync_key) or existing, False

        trade_id = _new_id()
        row = {
            "id": trade_id,
            "created_date": now,
            "execution_enabled": False,
            "broker_order_id": None,
            "notes": None,
            "exit_date": None,
            "exit_reason": None,
            "realized_pnl": None,
            "entry_snapshot_json": {"source": "ibkr"},
            **values,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(paper_trades).values(**row))
            conn.execute(
                insert(paper_trade_snapshots).values(
                    id=_new_id(),
                    trade_id=trade_id,
                    marked_at=now,
                    underlying_price=row["current_underlying_price"],
                    spread_value=row["current_spread_value"],
                    unrealized_pnl=row["unrealized_pnl"],
                    percent_return=row["percent_return"],
                    snapshot_json={"source": "ibkr_entry"},
                )
            )
        return row, True

    def update_valuation(self, trade_id: str, valuation: dict[str, Any], *, spread: MatchedSpread | None = None) -> None:
        now = _now()
        values: dict[str, Any] = {
            "current_underlying_price": valuation.get("underlying_price"),
            "current_spread_value": valuation.get("current_spread_value"),
            "unrealized_pnl": valuation.get("unrealized_pnl"),
            "percent_return": valuation.get("percent_return"),
            "max_profit_remaining": valuation.get("max_profit_remaining"),
            "progress_pct": valuation.get("distance_to_max_profit_pct"),
            "breakeven_distance": valuation.get("breakeven_distance"),
            "distance_to_long_strike": valuation.get("distance_to_long_strike"),
            "distance_to_short_strike": valuation.get("distance_to_short_strike"),
            "last_marked_at": now,
            "long_mid": valuation.get("long_mid"),
            "short_mid": valuation.get("short_mid"),
            "long_bid": valuation.get("long_bid"),
            "long_ask": valuation.get("long_ask"),
            "short_bid": valuation.get("short_bid"),
            "short_ask": valuation.get("short_ask"),
        }
        if spread:
            values.update({
                "quantity": spread.quantity,
                "market_value": spread.market_value,
                "today_pnl": spread.today_pnl,
                "long_bid": spread.long_leg.bid,
                "long_ask": spread.long_leg.ask,
                "short_bid": spread.short_leg.bid,
                "short_ask": spread.short_leg.ask,
            })
        with self.engine.begin() as conn:
            conn.execute(update(paper_trades).where(paper_trades.c.id == trade_id).values(**values))
            conn.execute(
                insert(paper_trade_snapshots).values(
                    id=_new_id(),
                    trade_id=trade_id,
                    marked_at=now,
                    underlying_price=values.get("current_underlying_price"),
                    spread_value=values.get("current_spread_value"),
                    unrealized_pnl=values.get("unrealized_pnl"),
                    percent_return=values.get("percent_return"),
                    snapshot_json={"source": "ibkr_refresh"},
                )
            )

    def mark_closed(self, trade_id: str, *, reason: str = "Closed on IBKR") -> None:
        now = _now()
        with self.engine.connect() as conn:
            row = conn.execute(select(paper_trades).where(paper_trades.c.id == trade_id)).first()
            if not row:
                return
            trade = dict(row._mapping)
        pnl = float(trade.get("unrealized_pnl") or 0)
        with self.engine.begin() as conn:
            conn.execute(
                update(paper_trades)
                .where(paper_trades.c.id == trade_id)
                .values(
                    status="CLOSED",
                    exit_date=now,
                    exit_reason=reason,
                    realized_pnl=pnl,
                    unrealized_pnl=0.0,
                    broker_status="closed_on_ibkr",
                )
            )

    def write_sync_log(self, *, action: str, result: dict[str, Any]) -> dict[str, Any]:
        row = {
            "id": _new_id(),
            "synced_at": _now(),
            "action": action,
            "records_updated": int(result.get("records_updated") or 0),
            "new_trades": int(result.get("new_trades") or 0),
            "closed_trades": int(result.get("closed_trades") or 0),
            "failed_requests": int(result.get("failed_requests") or 0),
            "message": result.get("message"),
            "details_json": result,
        }
        with self.engine.begin() as conn:
            conn.execute(insert(paper_trade_sync_logs).values(**row))
        return row

    def latest_sync_log(self) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(paper_trade_sync_logs).order_by(paper_trade_sync_logs.c.synced_at.desc()).limit(1)
            ).first()
            return dict(row._mapping) if row else None
