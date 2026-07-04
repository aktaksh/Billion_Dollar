from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.utils.expiry_format import normalize_expiry_iso


@dataclass
class OptionLeg:
    symbol: str
    expiry: str
    strike: float
    right: str  # C or P
    quantity: float
    conid: int | None = None
    avg_cost: float = 0.0
    mkt_price: float = 0.0
    mkt_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    today_pnl: float = 0.0
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    iv: float | None = None
    volume: float | None = None
    open_interest: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchedSpread:
    symbol: str
    strategy_type: str
    expiry: str
    long_strike: float
    short_strike: float
    long_option_type: str
    short_option_type: str
    quantity: int
    long_leg: OptionLeg
    short_leg: OptionLeg
    ibkr_sync_key: str
    is_debit: bool
    entry_debit: float | None
    entry_credit: float | None
    average_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    today_pnl: float


STRATEGY_TYPES = {
    "bull_call": "Bull Call Spread",
    "bear_put": "Bear Put Spread",
    "bull_put": "Bull Put Spread",
    "bear_call": "Bear Call Spread",
}


def parse_option_position(row: dict[str, Any]) -> OptionLeg | None:
    asset = str(row.get("assetClass") or row.get("secType") or row.get("sec_type") or "").upper()
    if asset not in ("OPT", "OPTION"):
        return None
    symbol = str(row.get("symbol") or row.get("ticker") or row.get("description") or "").split()[0].upper()
    if not symbol:
        return None
    expiry_raw = row.get("expiry") or row.get("expiryDate") or row.get("maturityDate") or ""
    expiry = normalize_expiry_iso(str(expiry_raw))
    strike = float(row.get("strike") or 0)
    right = str(row.get("putOrCall") or row.get("right") or "").upper()
    if right in ("CALL", "C"):
        right = "C"
    elif right in ("PUT", "P"):
        right = "P"
    if not expiry or strike <= 0 or right not in ("C", "P"):
        return None
    qty = float(row.get("position") or row.get("quantity") or 0)
    if qty == 0:
        return None
    conid = row.get("conid") or row.get("conId")
    return OptionLeg(
        symbol=symbol,
        expiry=expiry,
        strike=strike,
        right=right,
        quantity=qty,
        conid=int(conid) if conid is not None else None,
        avg_cost=float(row.get("avgCost") or row.get("avgPrice") or 0),
        mkt_price=float(row.get("mktPrice") or row.get("markPrice") or 0),
        mkt_value=float(row.get("mktValue") or row.get("marketValue") or 0),
        unrealized_pnl=float(row.get("unrealizedPnl") or row.get("unrealizedPNL") or 0),
        realized_pnl=float(row.get("realizedPnl") or row.get("realizedPNL") or 0),
        today_pnl=float(row.get("dailyPnl") or row.get("todayPnl") or row.get("changeInDailyPNL") or 0),
        raw=row,
    )


def _spread_key(symbol: str, expiry: str, long_strike: float, short_strike: float, strategy: str) -> str:
    return f"{symbol}|{expiry}|{long_strike:.2f}|{short_strike:.2f}|{strategy}"


def _classify_vertical(long_leg: OptionLeg, short_leg: OptionLeg) -> tuple[str, bool] | None:
    if long_leg.right != short_leg.right:
        return None
    if long_leg.right == "C":
        if long_leg.strike < short_leg.strike:
            return STRATEGY_TYPES["bull_call"], True
        if long_leg.strike > short_leg.strike:
            return STRATEGY_TYPES["bear_call"], False
    else:
        if long_leg.strike > short_leg.strike:
            return STRATEGY_TYPES["bear_put"], True
        if long_leg.strike < short_leg.strike:
            return STRATEGY_TYPES["bull_put"], False
    return None


parse_cp_position = parse_option_position
parse_tws_position = parse_option_position


class SpreadMatcher:
    """Match long/short option legs from IBKR into vertical spreads."""

    def match(self, positions: list[dict[str, Any]]) -> list[MatchedSpread]:
        legs: list[OptionLeg] = []
        for row in positions:
            leg = parse_option_position(row)
            if leg:
                legs.append(leg)
        return self.match_legs(legs)

    def match_legs(self, legs: list[OptionLeg]) -> list[MatchedSpread]:
        spreads: list[MatchedSpread] = []
        used: set[int] = set()
        groups: dict[tuple[str, str, str], list[OptionLeg]] = {}
        for idx, leg in enumerate(legs):
            key = (leg.symbol, leg.expiry, leg.right)
            groups.setdefault(key, []).append(leg)

        for (_symbol, _expiry, _right), group in groups.items():
            longs = sorted([l for l in group if l.quantity > 0], key=lambda l: l.strike)
            shorts = sorted([l for l in group if l.quantity < 0], key=lambda l: l.strike)
            for long_leg in longs:
                li = legs.index(long_leg)
                if li in used:
                    continue
                for short_leg in shorts:
                    si = legs.index(short_leg)
                    if si in used:
                        continue
                    qty = int(min(abs(long_leg.quantity), abs(short_leg.quantity)))
                    if qty <= 0:
                        continue
                    classified = _classify_vertical(long_leg, short_leg)
                    if not classified:
                        continue
                    strategy, is_debit = classified
                    opt_type = "call" if long_leg.right == "C" else "put"
                    avg_cost = (abs(long_leg.avg_cost) + abs(short_leg.avg_cost)) / max(qty, 1) / 100.0
                    entry_debit = round(avg_cost, 4) if is_debit else None
                    entry_credit = round(avg_cost, 4) if not is_debit else None
                    spreads.append(
                        MatchedSpread(
                            symbol=long_leg.symbol,
                            strategy_type=strategy,
                            expiry=long_leg.expiry,
                            long_strike=long_leg.strike,
                            short_strike=short_leg.strike,
                            long_option_type=opt_type,
                            short_option_type=opt_type,
                            quantity=qty,
                            long_leg=long_leg,
                            short_leg=short_leg,
                            ibkr_sync_key=_spread_key(long_leg.symbol, long_leg.expiry, long_leg.strike, short_leg.strike, strategy),
                            is_debit=is_debit,
                            entry_debit=entry_debit,
                            entry_credit=entry_credit,
                            average_cost=avg_cost,
                            market_value=long_leg.mkt_value + short_leg.mkt_value,
                            unrealized_pnl=long_leg.unrealized_pnl + short_leg.unrealized_pnl,
                            realized_pnl=long_leg.realized_pnl + short_leg.realized_pnl,
                            today_pnl=long_leg.today_pnl + short_leg.today_pnl,
                        )
                    )
                    used.add(li)
                    used.add(si)
                    break
        return spreads
