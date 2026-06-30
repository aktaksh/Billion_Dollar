from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.services.broker.option_chain_ibkr import (
    OptionChainParam,
    build_option_contract_specs,
    filter_expiries_by_dte,
    filter_strikes_by_pct,
    parse_secdef_option_chains,
    select_option_chain,
)


class _FakeChain:
    def __init__(
        self,
        *,
        exchange: str,
        trading_class: str,
        multiplier: str | int,
        expirations: list[str],
        strikes: list[float],
    ) -> None:
        self.exchange = exchange
        self.tradingClass = trading_class
        self.multiplier = multiplier
        self.expirations = expirations
        self.strikes = strikes


class OptionChainIbkrTests(unittest.TestCase):
    def test_parse_secdef_option_chains_normalizes_all_callbacks(self) -> None:
        raw = [
            _FakeChain(
                exchange="SMART",
                trading_class="QQQ",
                multiplier="100",
                expirations=["20260717", "20260619"],
                strikes=[700.0, 710.0],
            ),
            _FakeChain(
                exchange="AMEX",
                trading_class="QQQ",
                multiplier="100",
                expirations=["20260717"],
                strikes=[740.0],
            ),
        ]
        parsed = parse_secdef_option_chains(raw)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].exchange, "SMART")
        self.assertEqual(parsed[0].multiplier, 100)

    def test_select_option_chain_prefers_qqq_smart(self) -> None:
        chains = [
            OptionChainParam("CBOE", "QQQ", 100, ("20260717",), (700.0,)),
            OptionChainParam("AMEX", "QQQ", 100, ("20260717",), (700.0,)),
            OptionChainParam("SMART", "QQQ", 100, ("20260717",), (700.0,)),
        ]
        selected = select_option_chain(chains, symbol="QQQ")
        assert selected is not None
        self.assertEqual(selected.exchange, "SMART")

    def test_select_option_chain_falls_back_to_amex(self) -> None:
        chains = [
            OptionChainParam("CBOE", "QQQ", 100, ("20260717",), (700.0,)),
            OptionChainParam("AMEX", "QQQ", 100, ("20260717",), (700.0,)),
        ]
        selected = select_option_chain(chains, symbol="QQQ")
        assert selected is not None
        self.assertEqual(selected.exchange, "AMEX")

    def test_filter_expiries_by_dte(self) -> None:
        today = datetime.now(timezone.utc).date()
        expiries = [
            (today + timedelta(days=10)).strftime("%Y%m%d"),
            (today + timedelta(days=21)).strftime("%Y%m%d"),
            (today + timedelta(days=30)).strftime("%Y%m%d"),
            (today + timedelta(days=40)).strftime("%Y%m%d"),
        ]
        filtered = filter_expiries_by_dte(expiries, min_dte=14, max_dte=35)
        self.assertEqual(len(filtered), 2)

    def test_filter_strikes_by_pct(self) -> None:
        strikes = [600.0, 650.0, 700.0, 710.0, 740.0, 800.0]
        filtered = filter_strikes_by_pct(strikes, spot=700.0, pct=0.10)
        self.assertEqual(filtered, [650.0, 700.0, 710.0, 740.0])

    def test_build_option_contract_specs(self) -> None:
        specs = build_option_contract_specs(
            symbol="QQQ",
            expiry="2026-07-17",
            strikes=[710.0],
            exchange="SMART",
            trading_class="QQQ",
        )
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0]["expiry"], "20260717")
        self.assertEqual(specs[0]["right"], "C")
        self.assertEqual(specs[1]["right"], "P")


if __name__ == "__main__":
    unittest.main()
