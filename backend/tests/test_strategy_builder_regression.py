import unittest

from app.engines.strategy_builder_engine import (
    _calc_bear_put_spread,
    _calc_bull_call_spread,
    build_and_rank_candidates,
    candidate_unique_key,
    dedupe_candidates,
    OptionLeg,
)
from app.main import _partition_runtime_candidates


def base_feature():
    return {
        "trend_score": 72.0,
        "news_score": 0.2,
        "sector_strength_score": 65.0,
        "overextended_penalty": 0.0,
        "iv_percentile": 45.0,
        "atr_14": 8.0,
        "beta_to_spy": 1.1,
        "beta_to_qqq": 1.15,
    }


def qqq_chain_near_spot(underlying: float = 735.0) -> list[dict]:
    rows = []
    for strike in (underlying - 10, underlying - 5, underlying, underlying + 5, underlying + 10):
        rows.append(
            {
                "expiry": "2026-07-18",
                "dte": 30,
                "option_type": "call",
                "strike": strike,
                "bid": 8.0,
                "ask": 8.4,
                "volume": 600,
                "open_interest": 2200,
                "delta": 0.55,
                "gamma": 0.02,
                "iv": 0.25,
            }
        )
        rows.append(
            {
                "expiry": "2026-07-18",
                "dte": 30,
                "option_type": "put",
                "strike": strike,
                "bid": 7.8,
                "ask": 8.2,
                "volume": 560,
                "open_interest": 2100,
                "delta": -0.52,
                "gamma": 0.02,
                "iv": 0.26,
            }
        )
    return rows


class StrategyBuilderRegressionTests(unittest.TestCase):
    def test_duplicate_candidates_removed(self):
        duplicate = {
            "symbol": "QQQ",
            "direction": "bullish",
            "strategy_type": "bull_call_debit_spread",
            "expiry": "2026-07-18",
            "legs": [
                {"action": "BUY", "option_type": "call", "strike": 730.0, "qty": 1},
                {"action": "SELL", "option_type": "call", "strike": 735.0, "qty": 1},
            ],
        }
        unique = dedupe_candidates([duplicate, duplicate.copy()])
        self.assertEqual(len(unique), 1)
        self.assertEqual(
            candidate_unique_key(unique[0]),
            ("QQQ", "bullish", "bull_call_debit_spread", "2026-07-18", 730.0, 735.0, "call", "call"),
        )

    def test_dte_below_min_dte_rejects_candidate(self):
        chain = qqq_chain_near_spot()
        for row in chain:
            row["dte"] = 14
        rows = build_and_rank_candidates(
            symbol="QQQ",
            direction="bullish",
            last_price=735.0,
            feature=base_feature(),
            option_chain=chain,
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0, "min_dte": 21.0},
        )
        self.assertTrue(rows)
        self.assertTrue(all(row["risk_status"] == "reject" for row in rows))
        self.assertTrue(any(any(r["rule_id"] == "OPT-DTE-001" for r in row["rule_reasons"]) for row in rows))

    def test_invalid_debit_rejects_spread_candidate(self):
        buy = OptionLeg("2026-07-18", 30, "call", 730.0, 8.0, 8.4, 600, 2200, 0.55, 0.02, 0.0, 0.0, 0.25)
        sell = OptionLeg("2026-07-18", 30, "call", 735.0, 9.0, 9.4, 600, 2200, 0.45, 0.02, 0.0, 0.0, 0.24)
        spread = _calc_bull_call_spread("QQQ", 735.0, buy, sell, base_feature(), 2000.0)
        self.assertIsNone(spread)

    def test_bull_call_spread_payoff_math(self):
        buy = OptionLeg("2026-07-18", 30, "call", 730.0, 8.0, 8.4, 600, 2200, 0.55, 0.02, 0.0, 0.0, 0.25)
        sell = OptionLeg("2026-07-18", 30, "call", 735.0, 6.0, 6.4, 600, 2200, 0.45, 0.02, 0.0, 0.0, 0.24)
        spread = _calc_bull_call_spread("QQQ", 735.0, buy, sell, base_feature(), 2000.0)
        self.assertIsNotNone(spread)
        assert spread is not None
        self.assertAlmostEqual(spread["debit_or_credit"], 2.4, places=4)
        self.assertAlmostEqual(spread["spread_width"], 5.0, places=4)
        self.assertAlmostEqual(spread["max_loss"], 240.0, places=4)
        self.assertAlmostEqual(spread["max_profit"], 260.0, places=4)
        self.assertAlmostEqual(spread["breakeven"], 732.4, places=4)

    def test_bear_put_spread_payoff_math(self):
        buy = OptionLeg("2026-07-18", 30, "put", 735.0, 8.0, 8.4, 600, 2200, -0.55, 0.02, 0.0, 0.0, 0.26)
        sell = OptionLeg("2026-07-18", 30, "put", 730.0, 6.0, 6.4, 600, 2200, -0.45, 0.02, 0.0, 0.0, 0.25)
        spread = _calc_bear_put_spread("QQQ", 735.0, buy, sell, base_feature(), 2000.0)
        self.assertIsNotNone(spread)
        assert spread is not None
        self.assertAlmostEqual(spread["debit_or_credit"], 2.4, places=4)
        self.assertAlmostEqual(spread["spread_width"], 5.0, places=4)
        self.assertAlmostEqual(spread["max_loss"], 240.0, places=4)
        self.assertAlmostEqual(spread["max_profit"], 260.0, places=4)
        self.assertAlmostEqual(spread["breakeven"], 732.6, places=4)

    def test_no_far_strike_recommendations_at_spot(self):
        rows = build_and_rank_candidates(
            symbol="QQQ",
            direction="bullish",
            last_price=735.0,
            feature=base_feature(),
            option_chain=qqq_chain_near_spot(735.0),
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0},
        )
        for row in rows:
            for leg in row["legs"]:
                dist = abs(float(leg["strike"]) - 735.0) / 735.0
                self.assertLessEqual(dist, 0.12)

    def test_top_recommendations_only_allowed(self):
        base = {
            "symbol": "QQQ",
            "direction": "bullish",
            "expiry": "2026-07-18",
            "dte": 30,
            "legs": [],
            "debit_or_credit": 2.0,
            "max_profit": 300.0,
            "max_loss": 200.0,
            "breakeven": 732.0,
            "probability_profit": 0.5,
            "expected_value": 10.0,
            "alpha_score": 70.0,
            "beta_score": 80.0,
            "gamma_score": 75.0,
            "liquidity_score": 80.0,
            "strategy_score": 78.0,
            "rule_reasons": [],
        }
        rows = [
            {**base, "risk_status": "allow", "strategy_type": "bull_call_debit_spread"},
            {**base, "risk_status": "reject", "strategy_type": "long_call"},
        ]
        partitioned = _partition_runtime_candidates(rows)
        self.assertEqual(len(partitioned["top_recommendations"]), 1)
        self.assertEqual(partitioned["top_recommendations"][0].risk_status, "allow")
        self.assertEqual(len(partitioned["rejected_candidates"]), 1)

    def test_top_recommendations_excludes_dte_below_min(self):
        base = {
            "symbol": "QQQ",
            "direction": "bullish",
            "expiry": "2026-07-18",
            "legs": [],
            "debit_or_credit": 2.0,
            "max_profit": 300.0,
            "max_loss": 200.0,
            "breakeven": 732.0,
            "probability_profit": 0.5,
            "expected_value": 10.0,
            "alpha_score": 70.0,
            "beta_score": 80.0,
            "gamma_score": 75.0,
            "liquidity_score": 80.0,
            "strategy_score": 78.0,
            "rule_reasons": [],
        }
        rows = [
            {**base, "risk_status": "allow", "strategy_type": "bull_call_debit_spread", "dte": 30},
            {**base, "risk_status": "reject", "strategy_type": "long_call", "dte": 14},
        ]
        partitioned = _partition_runtime_candidates(rows)
        self.assertEqual(len(partitioned["top_recommendations"]), 1)
        self.assertEqual(partitioned["top_recommendations"][0].dte, 30)
        for top in partitioned["top_recommendations"]:
            self.assertGreaterEqual(top.dte, 21)
            self.assertEqual(top.risk_status, "allow")

    def test_top_recommendations_max_three_allowed(self):
        base = {
            "symbol": "QQQ",
            "direction": "bullish",
            "expiry": "2026-07-18",
            "dte": 30,
            "legs": [],
            "debit_or_credit": 2.0,
            "max_profit": 300.0,
            "max_loss": 200.0,
            "breakeven": 732.0,
            "probability_profit": 0.5,
            "expected_value": 10.0,
            "alpha_score": 70.0,
            "beta_score": 80.0,
            "gamma_score": 75.0,
            "liquidity_score": 80.0,
            "rule_reasons": [],
        }
        rows = [
            {**base, "risk_status": "allow", "strategy_type": "bull_call_debit_spread", "strategy_score": 95.0},
            {**base, "risk_status": "allow", "strategy_type": "bull_call_debit_spread", "strategy_score": 90.0},
            {**base, "risk_status": "allow", "strategy_type": "bull_call_debit_spread", "strategy_score": 85.0},
            {**base, "risk_status": "allow", "strategy_type": "bull_call_debit_spread", "strategy_score": 80.0},
        ]
        partitioned = _partition_runtime_candidates(rows)
        self.assertEqual(len(partitioned["top_recommendations"]), 3)
        self.assertTrue(all(top.risk_status == "allow" for top in partitioned["top_recommendations"]))


if __name__ == "__main__":
    unittest.main()
