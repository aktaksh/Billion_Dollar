from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, insert, select, update
from sqlalchemy.engine import Engine

from app.db import paper_trade_reviews, paper_trade_snapshots, paper_trades
from app.services.paper_trade_review import generate_trade_review
from app.services.pnl_calculator import (
    is_expired,
    mark_debit_spread,
    percent_return,
    spread_entry_value,
    unrealized_pnl,
)
from app.utils.expiry_format import dte_from_expiry, normalize_expiry_iso

STRATEGY_TYPE_MAP = {
    "bull_call_spread": "Bull Call Spread",
    "bear_put_spread": "Bear Put Spread",
    "bull_put_spread": "Bull Put Spread",
    "bear_call_spread": "Bear Call Spread",
}

OPTION_TYPES_BY_STRATEGY = {
    "bull_call_spread": ("call", "call"),
    "bear_put_spread": ("put", "put"),
    "Bull Call Spread": ("call", "call"),
    "Bear Put Spread": ("put", "put"),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row._mapping)


def _parse_delta_from_leg(leg: str | None) -> float | None:
    if not leg:
        return None
    if "δ" in leg:
        try:
            return float(leg.split("δ")[1].split(")")[0])
        except (IndexError, ValueError):
            return None
    return None


def _find_option_quote(
    options: list[dict[str, Any]],
    *,
    expiry: str,
    strike: float,
    option_type: str,
) -> dict[str, Any] | None:
    for opt in options:
        if normalize_expiry_iso(str(opt.get("expiry", ""))) != normalize_expiry_iso(expiry):
            continue
        if opt.get("option_type") != option_type:
            continue
        if abs(float(opt.get("strike", 0)) - strike) > 0.01:
            continue
        return opt
    return None


def _option_types_for_trade(trade: dict[str, Any]) -> tuple[str, str]:
    if trade.get("long_option_type") and trade.get("short_option_type"):
        return trade["long_option_type"], trade["short_option_type"]
    spread_type = trade.get("strategy_type", "")
    for key, types in OPTION_TYPES_BY_STRATEGY.items():
        if key in spread_type or spread_type == key:
            return types
    return "call", "call"


class PaperTradeService:
    def __init__(self, engine: Engine, *, analysis_dir_fn=None):
        self.engine = engine
        self._analysis_dir_fn = analysis_dir_fn

    def _load_analysis_json(self, symbol: str) -> dict[str, Any] | None:
        if not self._analysis_dir_fn:
            return None
        path = self._analysis_dir_fn(symbol)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def create_from_spread_candidate(
        self,
        analysis: dict[str, Any],
        candidate: dict[str, Any],
        *,
        notes: str = "",
        quantity: int = 1,
    ) -> dict[str, Any]:
        spread_type = candidate.get("spread_type", "")
        strategy_type = STRATEGY_TYPE_MAP.get(spread_type, candidate.get("strategy", spread_type))
        long_type, short_type = OPTION_TYPES_BY_STRATEGY.get(spread_type, ("call", "call"))
        daily = analysis.get("daily_indicators") or {}
        intraday = analysis.get("intraday_indicators") or {}
        entry_iv = self._avg_leg_iv(analysis, candidate, long_type, short_type)

        trade_id = _new_id()
        now = _now()
        expiry_iso = normalize_expiry_iso(candidate["expiry"])
        row = {
            "id": trade_id,
            "created_date": now,
            "symbol": str(analysis.get("symbol", "QQQ")).upper(),
            "underlying_price_at_entry": float(analysis.get("underlying_price") or 0),
            "strategy_type": strategy_type,
            "expiry_date": expiry_iso,
            "days_to_entry_dte": int(candidate.get("dte") or dte_from_expiry(expiry_iso)),
            "long_strike": float(candidate["buy_strike"]),
            "short_strike": float(candidate["sell_strike"]),
            "long_option_type": long_type,
            "short_option_type": short_type,
            "entry_debit": float(candidate.get("net_debit") or 0),
            "entry_credit": None,
            "quantity": max(1, quantity),
            "max_profit": float(candidate.get("max_profit") or 0),
            "max_loss": float(candidate.get("max_loss") or 0),
            "breakeven": float(candidate.get("breakeven") or 0),
            "entry_delta_long": _parse_delta_from_leg(candidate.get("long_leg")),
            "entry_delta_short": _parse_delta_from_leg(candidate.get("short_leg")),
            "entry_iv": entry_iv,
            "entry_atr": daily.get("atr14") or intraday.get("atr14"),
            "entry_rsi": daily.get("rsi14") or intraday.get("rsi14"),
            "entry_macd": daily.get("macd_line") or intraday.get("macd_line"),
            "market_bias": analysis.get("bias"),
            "confidence": analysis.get("confidence"),
            "reason_for_trade": self._build_reason(analysis, candidate),
            "notes": notes or None,
            "status": "OPEN",
            "exit_date": None,
            "exit_reason": None,
            "current_underlying_price": float(analysis.get("underlying_price") or 0),
            "current_spread_value": spread_entry_value(float(candidate.get("net_debit") or 0), max(1, quantity)),
            "realized_pnl": None,
            "unrealized_pnl": 0.0,
            "percent_return": 0.0,
            "highest_profit_seen": 0.0,
            "largest_drawdown": 0.0,
            "last_marked_at": now,
            "entry_snapshot_json": {"analysis": analysis, "candidate": candidate},
            "execution_enabled": False,
            "broker_order_id": None,
            "broker_status": None,
            "source": "manual",
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
                    unrealized_pnl=0.0,
                    percent_return=0.0,
                    snapshot_json={"source": "entry"},
                )
            )
        return row

    def bulk_create_from_analysis(self, analysis: dict[str, Any], *, notes: str = "") -> list[dict[str, Any]]:
        created: list[dict[str, Any]] = []
        for candidate in analysis.get("spread_candidates") or []:
            if str(candidate.get("status", "")).lower() != "accepted":
                continue
            created.append(self.create_from_spread_candidate(analysis, candidate, notes=notes))
        return created

    def list_trades(
        self,
        *,
        symbol: str | None = None,
        strategy_type: str | None = None,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        profit_only: bool | None = None,
        loss_only: bool | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(paper_trades).order_by(paper_trades.c.created_date.desc())
        conditions = []
        if symbol:
            conditions.append(paper_trades.c.symbol == symbol.upper())
        if strategy_type:
            conditions.append(paper_trades.c.strategy_type == strategy_type)
        if status:
            conditions.append(paper_trades.c.status == status.upper())
        if date_from:
            conditions.append(paper_trades.c.created_date >= date_from)
        if date_to:
            conditions.append(paper_trades.c.created_date <= date_to)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        with self.engine.connect() as conn:
            rows = [_row_to_dict(r) for r in conn.execute(stmt).fetchall()]
        if profit_only:
            rows = [r for r in rows if self._trade_pnl(r) > 0]
        if loss_only:
            rows = [r for r in rows if self._trade_pnl(r) < 0]
        return rows

    def get_trade(self, trade_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(paper_trades).where(paper_trades.c.id == trade_id)).first()
            if not row:
                return None
            trade = _row_to_dict(row)
            snaps = conn.execute(
                select(paper_trade_snapshots)
                .where(paper_trade_snapshots.c.trade_id == trade_id)
                .order_by(paper_trade_snapshots.c.marked_at.asc())
            ).fetchall()
            review = conn.execute(
                select(paper_trade_reviews).where(paper_trade_reviews.c.trade_id == trade_id)
            ).first()
        trade["snapshots"] = [_row_to_dict(s) for s in snaps]
        trade["review"] = _row_to_dict(review) if review else None
        return trade

    def update_trade(self, trade_id: str, *, notes: str | None = None) -> dict[str, Any] | None:
        values: dict[str, Any] = {}
        if notes is not None:
            values["notes"] = notes
        if not values:
            return self.get_trade(trade_id)
        with self.engine.begin() as conn:
            conn.execute(update(paper_trades).where(paper_trades.c.id == trade_id).values(**values))
        return self.get_trade(trade_id)

    def close_trade(self, trade_id: str, exit_reason: str) -> dict[str, Any] | None:
        trade = self.get_trade(trade_id)
        if not trade:
            return None
        if trade["status"] != "OPEN":
            return trade
        now = _now()
        pnl = float(trade.get("unrealized_pnl") or 0.0)
        pct = float(trade.get("percent_return") or 0.0)
        last_snap = trade["snapshots"][-1] if trade.get("snapshots") else None
        review_text = generate_trade_review(trade, last_mark_snapshot=last_snap)
        with self.engine.begin() as conn:
            conn.execute(
                update(paper_trades)
                .where(paper_trades.c.id == trade_id)
                .values(
                    status="CLOSED",
                    exit_date=now,
                    exit_reason=exit_reason,
                    realized_pnl=pnl,
                    unrealized_pnl=0.0,
                    percent_return=pct,
                )
            )
            conn.execute(
                insert(paper_trade_reviews).values(
                    id=_new_id(),
                    trade_id=trade_id,
                    created_at=now,
                    **review_text,
                    review_json=review_text,
                )
            )
        return self.get_trade(trade_id)

    def mark_to_market_for_symbol(self, symbol: str) -> int:
        sym = symbol.upper()
        analysis = self._load_analysis_json(sym)
        if not analysis:
            return 0
        options = analysis.get("liquid_options") or analysis.get("raw_options") or []
        underlying = float(analysis.get("underlying_price") or 0)
        updated = 0
        open_trades = self.list_trades(symbol=sym, status="OPEN")
        now = _now()
        for trade in open_trades:
            if is_expired(trade["expiry_date"]):
                self._expire_trade(trade, underlying, now, analysis)
                updated += 1
                continue
            long_type, short_type = _option_types_for_trade(trade)
            long_q = _find_option_quote(
                options,
                expiry=normalize_expiry_iso(trade["expiry_date"]),
                strike=float(trade["long_strike"]),
                option_type=long_type,
            )
            short_q = _find_option_quote(
                options,
                expiry=normalize_expiry_iso(trade["expiry_date"]),
                strike=float(trade["short_strike"]),
                option_type=short_type,
            )
            if not long_q or not short_q:
                continue
            qty = int(trade.get("quantity") or 1)
            entry_val = spread_entry_value(float(trade.get("entry_debit") or 0), qty)
            current_val = mark_debit_spread(float(long_q.get("mid") or 0), float(short_q.get("mid") or 0), qty)
            pnl = unrealized_pnl(entry_val, current_val)
            pct = percent_return(pnl, float(trade.get("max_loss") or 0))
            high = max(float(trade.get("highest_profit_seen") or 0), pnl)
            low = min(float(trade.get("largest_drawdown") or 0), pnl)
            snap_json = {
                "bias": analysis.get("bias"),
                "confidence": analysis.get("confidence"),
                "long_mid": long_q.get("mid"),
                "short_mid": short_q.get("mid"),
                "daily_indicators": analysis.get("daily_indicators"),
                "intraday_indicators": analysis.get("intraday_indicators"),
            }
            with self.engine.begin() as conn:
                conn.execute(
                    update(paper_trades)
                    .where(paper_trades.c.id == trade["id"])
                    .values(
                        current_underlying_price=underlying,
                        current_spread_value=current_val,
                        unrealized_pnl=pnl,
                        percent_return=pct,
                        highest_profit_seen=high,
                        largest_drawdown=low,
                        last_marked_at=now,
                    )
                )
                conn.execute(
                    insert(paper_trade_snapshots).values(
                        id=_new_id(),
                        trade_id=trade["id"],
                        marked_at=now,
                        underlying_price=underlying,
                        spread_value=current_val,
                        unrealized_pnl=pnl,
                        percent_return=pct,
                        snapshot_json=snap_json,
                    )
                )
            updated += 1
        return updated

    def get_summary(self) -> dict[str, Any]:
        all_trades = self.list_trades()
        open_trades = [t for t in all_trades if t["status"] == "OPEN"]
        closed = [t for t in all_trades if t["status"] in ("CLOSED", "EXPIRED")]
        wins = [t for t in closed if self._trade_pnl(t) > 0]
        pnls = [self._trade_pnl(t) for t in closed]
        returns = [float(t.get("percent_return") or 0) for t in closed]
        hold_days: list[int] = []
        for t in closed:
            start = t.get("created_date")
            end = t.get("exit_date") or t.get("last_marked_at")
            if start and end:
                if isinstance(start, str):
                    start = datetime.fromisoformat(start.replace("Z", "+00:00"))
                if isinstance(end, str):
                    end = datetime.fromisoformat(end.replace("Z", "+00:00"))
                hold_days.append(max(0, (end - start).days))
        return {
            "open_count": len(open_trades),
            "closed_count": len(closed),
            "total_trades": len(all_trades),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0.0,
            "total_realized_pnl": round(sum(pnls), 2),
            "total_unrealized_pnl": round(sum(float(t.get("unrealized_pnl") or 0) for t in open_trades), 2),
            "best_trade_pnl": max(pnls) if pnls else 0.0,
            "worst_trade_pnl": min(pnls) if pnls else 0.0,
            "avg_holding_days": round(sum(hold_days) / len(hold_days), 1) if hold_days else 0.0,
        }

    def get_analytics(self) -> dict[str, Any]:
        closed = self.list_trades(status="CLOSED") + self.list_trades(status="EXPIRED")
        by_strategy: dict[str, dict[str, Any]] = {}
        monthly: dict[str, float] = {}
        gross_profit = 0.0
        gross_loss = 0.0
        for t in closed:
            st = t.get("strategy_type") or "Unknown"
            pnl = self._trade_pnl(t)
            bucket = by_strategy.setdefault(st, {"count": 0, "wins": 0, "total_pnl": 0.0})
            bucket["count"] += 1
            bucket["total_pnl"] = round(bucket["total_pnl"] + pnl, 2)
            if pnl > 0:
                bucket["wins"] += 1
                gross_profit += pnl
            elif pnl < 0:
                gross_loss += abs(pnl)
            exit_dt = t.get("exit_date") or t.get("created_date")
            if exit_dt:
                if isinstance(exit_dt, str):
                    exit_dt = datetime.fromisoformat(exit_dt.replace("Z", "+00:00"))
                key = exit_dt.strftime("%Y-%m")
                monthly[key] = round(monthly.get(key, 0.0) + pnl, 2)
        strategy_rows = []
        for name, stats in sorted(by_strategy.items()):
            strategy_rows.append({
                "strategy_type": name,
                "count": stats["count"],
                "win_rate": round(stats["wins"] / stats["count"] * 100, 1) if stats["count"] else 0,
                "total_pnl": stats["total_pnl"],
            })
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
        return {
            "strategy_breakdown": strategy_rows,
            "monthly_returns": [{"month": k, "pnl": v} for k, v in sorted(monthly.items())],
            "profit_factor": profit_factor,
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
        }

    def export_trades(self, fmt: str = "json", **filters) -> tuple[str, str, str]:
        rows = self.list_trades(**filters)
        if fmt == "csv":
            buf = io.StringIO()
            if not rows:
                return "text/csv", "paper_trades.csv", ""
            fieldnames = list(rows[0].keys())
            writer = csv.DictWriter(buf, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: self._serialize_export_val(v) for k, v in row.items()})
            return "text/csv", "paper_trades.csv", buf.getvalue()
        payload = json.dumps([self._serialize_row(r) for r in rows], indent=2, default=str)
        return "application/json", "paper_trades.json", payload

    def _expire_trade(self, trade: dict[str, Any], underlying: float, now: datetime, analysis: dict) -> None:
        pnl = float(trade.get("unrealized_pnl") or 0.0)
        pct = float(trade.get("percent_return") or 0.0)
        review_text = generate_trade_review(trade)
        with self.engine.begin() as conn:
            conn.execute(
                update(paper_trades)
                .where(paper_trades.c.id == trade["id"])
                .values(
                    status="EXPIRED",
                    exit_date=now,
                    exit_reason="Expired",
                    current_underlying_price=underlying,
                    realized_pnl=pnl,
                    unrealized_pnl=0.0,
                    percent_return=pct,
                    last_marked_at=now,
                )
            )
            conn.execute(
                insert(paper_trade_reviews).values(
                    id=_new_id(),
                    trade_id=trade["id"],
                    created_at=now,
                    **review_text,
                    review_json=review_text,
                )
            )

    @staticmethod
    def _trade_pnl(trade: dict[str, Any]) -> float:
        if trade.get("status") == "OPEN":
            return float(trade.get("unrealized_pnl") or 0)
        return float(trade.get("realized_pnl") or 0)

    @staticmethod
    def _build_reason(analysis: dict[str, Any], candidate: dict[str, Any]) -> str:
        parts = [str(analysis.get("reason_summary") or "").strip()]
        if candidate.get("strategy"):
            parts.append(str(candidate["strategy"]))
        return " — ".join(p for p in parts if p)

    @staticmethod
    def _avg_leg_iv(
        analysis: dict[str, Any],
        candidate: dict[str, Any],
        long_type: str,
        short_type: str,
    ) -> float | None:
        options = analysis.get("liquid_options") or analysis.get("raw_options") or []
        long_q = _find_option_quote(
            options,
            expiry=candidate["expiry"],
            strike=float(candidate["buy_strike"]),
            option_type=long_type,
        )
        short_q = _find_option_quote(
            options,
            expiry=candidate["expiry"],
            strike=float(candidate["sell_strike"]),
            option_type=short_type,
        )
        ivs = [float(q["iv"]) for q in (long_q, short_q) if q and q.get("iv") is not None]
        return round(sum(ivs) / len(ivs), 4) if ivs else None

    @staticmethod
    def _serialize_export_val(val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return str(val)

    @staticmethod
    def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out
