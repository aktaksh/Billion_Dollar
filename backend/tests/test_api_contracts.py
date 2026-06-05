import unittest
from datetime import UTC, datetime

from app.engines.strategy_builder_engine import build_and_rank_candidates
from app.models import StrategyBuilderCandidatesOut, StrategyCandidateOut


class ContractInvariantTests(unittest.TestCase):
    def _sample_chain(self):
        return [
            {
                "symbol": "QQQ",
                "expiry": "2026-06-19",
                "dte": 24,
                "option_type": "call",
                "strike": 500.0,
                "bid": 4.5,
                "ask": 4.8,
                "volume": 800,
                "open_interest": 2200,
                "delta": 0.52,
                "gamma": 0.02,
                "theta": -0.07,
                "vega": 0.16,
                "iv": 0.24,
            },
            {
                "symbol": "QQQ",
                "expiry": "2026-06-19",
                "dte": 24,
                "option_type": "put",
                "strike": 480.0,
                "bid": 3.8,
                "ask": 4.1,
                "volume": 760,
                "open_interest": 2100,
                "delta": -0.48,
                "gamma": 0.02,
                "theta": -0.07,
                "vega": 0.16,
                "iv": 0.25,
            },
        ]

    def test_strategy_candidates_include_risk_fields(self):
        rows = build_and_rank_candidates(
            symbol="QQQ",
            direction="bullish",
            last_price=500.0,
            feature={
                "iv_percentile": 50.0,
                "trend_score": 55.0,
                "atr_14": 8.0,
                "news_score": 0.0,
                "beta_to_spy": 1.0,
                "beta_to_qqq": 1.0,
                "sector_strength_score": 55.0,
                "overextended_penalty": 0.0,
            },
            option_chain=self._sample_chain(),
            reconciliation_mismatch_active=False,
            thresholds={"max_loss_per_trade_usd": 750.0},
        )
        self.assertTrue(rows)
        for row in rows:
            self.assertIn(row["risk_status"], {"allow", "reject", "override_required"})
            self.assertIsInstance(row["rule_reasons"], list)

    def test_builder_out_contract_fields(self):
        rows = build_and_rank_candidates(
            symbol="QQQ",
            direction="bullish",
            last_price=500.0,
            feature={"iv_percentile": 50.0, "trend_score": 55.0, "atr_14": 8.0},
            option_chain=self._sample_chain(),
            reconciliation_mismatch_active=False,
            thresholds={},
        )
        out = StrategyBuilderCandidatesOut(
            symbol="QQQ",
            direction="bullish",
            candidates=[StrategyCandidateOut(**row) for row in rows],
            as_of=datetime.now(UTC),
            data_status="live",
        )
        self.assertEqual(out.symbol, "QQQ")
        self.assertIsNotNone(out.as_of)
        self.assertEqual(out.data_status, "live")
        self.assertTrue(out.candidates)


if __name__ == "__main__":
    unittest.main()
