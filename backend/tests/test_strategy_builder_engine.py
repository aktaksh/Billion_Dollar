import unittest

from app.engines.strategy_builder_engine import build_and_rank_candidates


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


def bullish_chain():
    return [
        {
            "expiry": "2026-06-19",
            "dte": 30,
            "option_type": "call",
            "strike": 500,
            "bid": 12.0,
            "ask": 12.6,
            "volume": 600,
            "open_interest": 2200,
            "delta": 0.58,
            "gamma": 0.022,
            "theta": -0.12,
            "vega": 0.31,
            "iv": 0.28,
        },
        {
            "expiry": "2026-06-19",
            "dte": 30,
            "option_type": "call",
            "strike": 520,
            "bid": 6.8,
            "ask": 7.2,
            "volume": 700,
            "open_interest": 2100,
            "delta": 0.33,
            "gamma": 0.018,
            "theta": -0.09,
            "vega": 0.22,
            "iv": 0.27,
        },
    ]


def bearish_chain():
    return [
        {
            "expiry": "2026-06-19",
            "dte": 30,
            "option_type": "put",
            "strike": 500,
            "bid": 11.8,
            "ask": 12.3,
            "volume": 560,
            "open_interest": 2500,
            "delta": -0.57,
            "gamma": 0.021,
            "theta": -0.11,
            "vega": 0.29,
            "iv": 0.29,
        },
        {
            "expiry": "2026-06-19",
            "dte": 30,
            "option_type": "put",
            "strike": 480,
            "bid": 6.4,
            "ask": 6.9,
            "volume": 620,
            "open_interest": 2100,
            "delta": -0.31,
            "gamma": 0.017,
            "theta": -0.08,
            "vega": 0.21,
            "iv": 0.27,
        },
    ]


class StrategyBuilderEngineTests(unittest.TestCase):
    def test_bull_call_debit_spread_generated(self):
        rows = build_and_rank_candidates(
            symbol="QQQ",
            direction="bullish",
            last_price=505.0,
            feature={**base_feature(), "vwap": 500.0, "ema_20": 498.0, "ema_20_slope": 0.1, "rsi_14": 58.0, "regime": "risk_on"},
            option_chain=bullish_chain(),
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0, "min_reward_risk": 0.0, "min_probability_profit": 0.0},
        )
        strategies = {r["strategy_type"] for r in rows}
        self.assertIn("bull_call_debit_spread", strategies)
        self.assertNotIn("long_call", strategies)

    def test_long_put_and_bear_spread_generated(self):
        rows = build_and_rank_candidates(
            symbol="QQQ",
            direction="bearish",
            last_price=505.0,
            feature=base_feature(),
            option_chain=bearish_chain(),
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0},
        )
        strategies = {r["strategy_type"] for r in rows}
        self.assertIn("bear_put_debit_spread", strategies)

    def test_dte_rejection(self):
        chain = bullish_chain()
        chain[0]["dte"] = 5
        rows = build_and_rank_candidates(
            symbol="SPY",
            direction="bullish",
            last_price=505.0,
            feature=base_feature(),
            option_chain=chain,
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0},
        )
        rejected = [r for r in rows if r["risk_status"] == "reject"]
        self.assertTrue(any(any(rr["rule_id"] == "OPT-DTE-001" for rr in r["rule_reasons"]) for r in rejected))

    def test_bid_ask_spread_rejection(self):
        chain = bullish_chain()
        chain[0]["bid"] = 8.0
        chain[0]["ask"] = 12.0  # very wide
        rows = build_and_rank_candidates(
            symbol="SPY",
            direction="bullish",
            last_price=505.0,
            feature=base_feature(),
            option_chain=chain,
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0},
        )
        self.assertTrue(any(any(rr["rule_id"] == "OPT-LIQ-002" for rr in r["rule_reasons"]) for r in rows))

    def test_open_interest_rejection(self):
        chain = bullish_chain()
        chain[0]["open_interest"] = 10
        rows = build_and_rank_candidates(
            symbol="SPY",
            direction="bullish",
            last_price=505.0,
            feature=base_feature(),
            option_chain=chain,
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0},
        )
        self.assertTrue(any(any(rr["rule_id"] == "OPT-LIQ-001" for rr in r["rule_reasons"]) for r in rows))

    def test_volume_rejection(self):
        chain = bullish_chain()
        chain[0]["volume"] = 2
        rows = build_and_rank_candidates(
            symbol="SPY",
            direction="bullish",
            last_price=505.0,
            feature=base_feature(),
            option_chain=chain,
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0},
        )
        self.assertTrue(any(any(rr["rule_id"] == "OPT-LIQ-003" for rr in r["rule_reasons"]) for r in rows))

    def test_max_loss_rejection(self):
        chain = bullish_chain()
        rows = build_and_rank_candidates(
            symbol="SPY",
            direction="bullish",
            last_price=505.0,
            feature=base_feature(),
            option_chain=chain,
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 100.0},
        )
        self.assertTrue(any(any(rr["rule_id"] == "OPT-EXP-001" for rr in r["rule_reasons"]) for r in rows))

    def test_gamma_override_rule(self):
        chain = bullish_chain()
        chain[0]["gamma"] = 0.06
        rows = build_and_rank_candidates(
            symbol="SPY",
            direction="bullish",
            last_price=500.0,
            feature=base_feature(),
            option_chain=chain,
            reconciliation_mismatch_active=False,
            thresholds={
                "min_reward_risk": 0.0,
                "min_probability_profit": 0.0,
                "max_loss_per_trade_usd": 10_000.0,
            },
        )
        self.assertTrue(
            any(
                any(rr["rule_id"] == "OPT-GRK-001" for rr in r["rule_reasons"])
                and r["risk_status"] == "override_required"
                for r in rows
            )
        )

    def test_reconciliation_rejection(self):
        rows = build_and_rank_candidates(
            symbol="SPY",
            direction="bullish",
            last_price=500.0,
            feature=base_feature(),
            option_chain=bullish_chain(),
            reconciliation_mismatch_active=True,
        )
        self.assertTrue(all(r["risk_status"] == "reject" for r in rows))

    def test_ranking_order(self):
        rows = build_and_rank_candidates(
            symbol="QQQ",
            direction="bullish",
            last_price=505.0,
            feature=base_feature(),
            option_chain=bullish_chain(),
            reconciliation_mismatch_active=False,
        )
        scores = [r["strategy_score"] for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()

