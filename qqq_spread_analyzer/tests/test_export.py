import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from src.export import report_to_dict, write_latest_analysis
from src.indicators import IndicatorSnapshot
from src.levels import LevelSet
from src.options_chain import OptionQuote
from src.report import AnalysisReport
from src.scoring import ScoreResult


class ExportTests(unittest.TestCase):
    def test_report_to_dict_includes_levels_and_scores(self):
        score = ScoreResult(
            bullish_score=6,
            bearish_score=1,
            intraday_timing_bull=2,
            intraday_timing_bear=0,
            bias="Neutral",
            confidence="Medium",
            action="no_trade",
            invalid_conditions=[],
            daily_checks={"close_gt_ema20": True},
            intraday_checks={"ema9_gt_ema21": True},
        )
        report = AnalysisReport(
            timestamp=datetime.now(timezone.utc),
            symbol="QQQ",
            underlying_price=725.0,
            score=score,
            daily=IndicatorSnapshot(close=725.0, ema20=721.0, rsi14=52.0),
            intraday=IndicatorSnapshot(close=725.0, ema9=727.0, ema21=724.0),
            levels=LevelSet(prev_week_low=700.0, prev_week_high=740.0),
            spreads=[],
            risk_notes=["Research only"],
        )
        payload = report_to_dict(report, diagnostics={"raw_quotes": 10})
        self.assertEqual(payload["symbol"], "QQQ")
        self.assertEqual(payload["bullish_score"], 6)
        self.assertIn("support_levels", payload)
        self.assertIn("reason_summary", payload)
        self.assertEqual(payload["diagnostics"]["raw_quotes"], 10)

    def test_report_to_dict_includes_option_quotes(self):
        score = ScoreResult(
            bullish_score=7,
            bearish_score=1,
            intraday_timing_bull=3,
            intraday_timing_bear=0,
            bias="Bullish",
            confidence="High",
            action="bull_call_spread",
        )
        report = AnalysisReport(
            timestamp=datetime.now(timezone.utc),
            symbol="QQQ",
            underlying_price=725.0,
            score=score,
            daily=IndicatorSnapshot(close=725.0),
            intraday=IndicatorSnapshot(close=725.0),
            levels=LevelSet(),
            spreads=[],
        )
        buy = OptionQuote(
            expiry="2026-04-17",
            dte=28,
            option_type="call",
            strike=520.0,
            bid=4.0,
            ask=4.2,
            last=4.1,
            volume=200,
            open_interest=1000,
            delta=0.4,
            gamma=0.01,
            theta=-0.05,
            vega=0.1,
            iv=0.18,
        )
        wide = OptionQuote(
            expiry="2026-04-17",
            dte=28,
            option_type="call",
            strike=530.0,
            bid=0.0,
            ask=0.0,
            last=0.0,
            volume=0,
            open_interest=0,
            delta=0.25,
            gamma=0.01,
            theta=-0.04,
            vega=0.08,
            iv=0.17,
        )
        payload = report_to_dict(report, liquid_options=[buy], raw_options=[buy, wide])
        self.assertEqual(len(payload["liquid_options"]), 1)
        self.assertEqual(len(payload["raw_options"]), 2)
        self.assertTrue(payload["liquid_options"][0]["liquid"])
        self.assertFalse(payload["raw_options"][1]["liquid"])
        self.assertEqual(payload["liquid_options"][0]["strike"], 520.0)

    def test_write_latest_analysis_creates_file(self):
        import tempfile
        from pathlib import Path

        score = ScoreResult(
            bullish_score=1,
            bearish_score=1,
            intraday_timing_bull=0,
            intraday_timing_bear=0,
            bias="Neutral",
            confidence="Low",
            action="no_trade",
        )
        report = AnalysisReport(
            timestamp=datetime.now(timezone.utc),
            symbol="QQQ",
            underlying_price=100.0,
            score=score,
            daily=IndicatorSnapshot(close=100.0),
            intraday=IndicatorSnapshot(close=100.0),
            levels=LevelSet(),
            spreads=[],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "latest_analysis_QQQ.json"
            write_latest_analysis(report, diagnostics={}, path=path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["symbol"], "QQQ")


if __name__ == "__main__":
    unittest.main()
