from src.options_chain import OptionQuote
from src.spread_builder import build_spread_candidates


def _call(expiry: str, strike: float, delta: float, bid: float, ask: float) -> OptionQuote:
    return OptionQuote(
        expiry=expiry,
        dte=30,
        option_type="call",
        strike=strike,
        bid=bid,
        ask=ask,
        last=(bid + ask) / 2,
        volume=200,
        open_interest=1000,
        delta=delta,
        gamma=0.01,
        theta=-0.05,
        vega=0.1,
        iv=0.2,
    )


def test_bull_call_spread_metrics() -> None:
    buy = _call("2026-04-17", 500.0, 0.40, 5.0, 5.2)
    sell = _call("2026-04-17", 510.0, 0.25, 2.0, 2.2)
    spreads = build_spread_candidates([buy, sell], "bull_call_spread", limit=5)
    assert len(spreads) == 1
    sp = spreads[0]
    assert sp.net_debit == round(5.2 - 2.0, 2)
    assert sp.max_loss == sp.net_debit * 100
    assert sp.max_profit > 0
    assert sp.breakeven == round(500.0 + sp.net_debit, 2)
