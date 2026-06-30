import unittest

from app.engines.strategy_builder_engine import build_and_rank_candidates
from app.main import _partition_runtime_candidates


def base_feature() -> dict:
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


def bullish_confirmed_feature() -> dict:
    return {
        **base_feature(),
        "vwap": 730.0,
        "ema_20": 728.0,
        "ema_20_slope": 0.1,
        "rsi_14": 58.0,
        "regime": "risk_on",
    }


def bullish_conflict_feature() -> dict:
    return {
        **base_feature(),
        "vwap": 740.0,
        "ema_20": 738.0,
        "ema_20_slope": -0.1,
        "rsi_14": 40.0,
        "regime": "risk_on",
    }


def bullish_mixed_risk_off_feature() -> dict:
    return {
        **base_feature(),
        "vwap": 730.0,
        "ema_20": 740.0,
        "ema_20_slope": 0.1,
        "rsi_14": 58.0,
        "regime": "risk_off",
    }


def qqq_chain_near_spot(underlying: float = 735.0) -> list[dict]:
    rows = []
    for strike in (underlying - 35, underlying - 5, underlying, underlying + 5, underlying + 10):
        rows.append(
            {
                "expiry": "2026-07-18",
                "dte": 30,
                "option_type": "call",
                "strike": strike,
                "bid": 8.0 if strike >= underlying - 10 else 18.0,
                "ask": 8.4 if strike >= underlying - 10 else 18.6,
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


class SwingSetupTests(unittest.TestCase):
    def test_bullish_below_vwap_and_ema_has_no_allow(self):
        rows = build_and_rank_candidates(
            symbol="QQQ",
            direction="bullish",
            last_price=735.0,
            feature=bullish_conflict_feature(),
            option_chain=qqq_chain_near_spot(735.0),
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0, "min_reward_risk": 0.0, "min_probability_profit": 0.0},
        )
        self.assertTrue(rows)
        self.assertFalse(any(row["risk_status"] == "allow" for row in rows))
        self.assertTrue(any(row["risk_status"] == "watch_only" for row in rows))

    def test_bullish_confirmed_setup_has_allow_spread(self):
        rows = build_and_rank_candidates(
            symbol="QQQ",
            direction="bullish",
            last_price=735.0,
            feature=bullish_confirmed_feature(),
            option_chain=qqq_chain_near_spot(735.0),
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0, "min_reward_risk": 0.0, "min_probability_profit": 0.0},
        )
        allowed = [row for row in rows if row["risk_status"] == "allow"]
        self.assertTrue(allowed)
        self.assertTrue(all(row["strategy_type"] == "bull_call_debit_spread" for row in allowed))

    def test_risk_off_bullish_mixed_setup_override_required(self):
        rows = build_and_rank_candidates(
            symbol="QQQ",
            direction="bullish",
            last_price=735.0,
            feature=bullish_mixed_risk_off_feature(),
            option_chain=qqq_chain_near_spot(735.0),
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 2000.0, "min_reward_risk": 0.0, "min_probability_profit": 0.0},
        )
        overrides = [row for row in rows if row["risk_status"] == "override_required"]
        self.assertTrue(overrides)
        self.assertTrue(
            any(any(reason["rule_id"] == "REGIME_CONFLICT" for reason in row["rule_reasons"]) for row in overrides)
        )

    def test_breakeven_too_far_watch_only_and_ranks_below_nearer(self):
        rows = build_and_rank_candidates(
            symbol="QQQ",
            direction="bullish",
            last_price=735.0,
            feature=bullish_confirmed_feature(),
            option_chain=qqq_chain_near_spot(735.0),
            reconciliation_mismatch_active=False,
            thresholds={
                "max_loss_per_trade_usd": 5000.0,
                "min_reward_risk": 0.0,
                "min_probability_profit": 0.0,
                "max_breakeven_distance_pct": 0.03,
            },
        )
        watch_only = [row for row in rows if row["risk_status"] == "watch_only"]
        self.assertTrue(watch_only)
        self.assertTrue(
            any(any(reason["rule_id"] == "BREAKEVEN_TOO_FAR" for reason in row["rule_reasons"]) for row in watch_only)
        )
        allowed = [row for row in rows if row["risk_status"] == "allow"]
        if allowed and watch_only:
            first_watch_idx = next(i for i, row in enumerate(rows) if row["risk_status"] == "watch_only")
            first_allow_idx = next((i for i, row in enumerate(rows) if row["risk_status"] == "allow"), None)
            if first_allow_idx is not None:
                self.assertLess(first_allow_idx, first_watch_idx)

    def test_top_recommendations_only_allow_max_three(self):
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
            {**base, "risk_status": "allow", "strategy_type": "bull_call_debit_spread", "strategy_score": 90.0},
            {**base, "risk_status": "allow", "strategy_type": "bull_call_debit_spread", "strategy_score": 85.0},
            {**base, "risk_status": "allow", "strategy_type": "bull_call_debit_spread", "strategy_score": 80.0},
            {**base, "risk_status": "allow", "strategy_type": "bull_call_debit_spread", "strategy_score": 75.0},
            {**base, "risk_status": "watch_only", "strategy_type": "bull_call_debit_spread", "strategy_score": 95.0},
            {**base, "risk_status": "reject", "strategy_type": "bull_call_debit_spread"},
        ]
        partitioned = _partition_runtime_candidates(rows)
        self.assertLessEqual(len(partitioned["top_recommendations"]), 3)
        self.assertTrue(all(row.risk_status == "allow" for row in partitioned["top_recommendations"]))
        self.assertEqual(len(partitioned["watch_only_candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
