import unittest

from app.engines.feature_engine import build_symbol_features
from app.engines.ingestion_engine import build_mock_option_chain, normalize_context_snapshot, normalize_market_snapshot
from app.engines.paper_trade_engine import simulate_paper_trade
from app.engines.replay_engine import replay_candidates_under_scenarios
from app.engines.strategy_runtime_engine import run_strategy_runtime


class RuntimeEnginesTests(unittest.TestCase):
    def test_ingestion_feature_runtime_flow(self):
        market = normalize_market_snapshot(
            ticker="QQQ",
            ibkr_snapshot={"31": 500.0, "84": 499.8, "86": 500.2, "88": 1_250_000},
        )
        option_chain = build_mock_option_chain(ticker="QQQ", last_price=500.0)
        context = normalize_context_snapshot(ticker="QQQ", market_snapshot=market, news_rows=[{"headline": "QQQ growth strong"}])
        features = build_symbol_features(
            ticker="QQQ",
            market_snapshot=market,
            option_chain=option_chain,
            context_snapshot=context,
        )
        rows, _leg_diag = run_strategy_runtime(
            ticker="QQQ",
            direction="bullish",
            market_snapshot=market,
            feature_snapshot=features,
            option_chain_snapshot=option_chain,
            reconciliation_mismatch_active=False,
            thresholds={},
        )
        self.assertTrue(rows)
        self.assertTrue(any(row["strategy_type"] in {"long_call", "bull_call_debit_spread"} for row in rows))

    def test_replay_and_paper_trade(self):
        candidates = [
            {
                "strategy_type": "bull_call_debit_spread",
                "risk_status": "allow",
                "strategy_score": 82.0,
                "probability_profit": 0.58,
                "expected_value": 42.0,
                "max_profit": 180.0,
                "max_loss": 95.0,
                "direction": "bullish",
                "debit_or_credit": 2.1,
            }
        ]
        replay = replay_candidates_under_scenarios(candidates=candidates, scenarios=[-0.03, 0.0, 0.03])
        self.assertEqual(len(replay), 1)
        self.assertIn("replay_avg_pnl", replay[0])

        paper = simulate_paper_trade(
            signal_id="sig_test",
            ticker="QQQ",
            candidate=candidates[0],
            scenario_return=0.02,
        )
        self.assertTrue(paper.order_intent_id.startswith("paper_intent_"))
        self.assertNotEqual(paper.entry_price, 0.0)


if __name__ == "__main__":
    unittest.main()
