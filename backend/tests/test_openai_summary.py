"""Unit tests for the Part 8 OpenAI cluster-summary layer."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from news_intelligence.openai_summary import (
    SUMMARY_KEYS,
    build_llm_ticker_summary,
    cluster_fingerprint,
    select_events_for_llm,
)


def _event(
    cluster_id: str,
    *,
    primary_ticker_score: float = 90.0,
    importance_score: float = 90.0,
    impact_score: float = 40.0,
    title: str = "Nvidia files 8-K on new supply agreement",
) -> dict:
    return {
        "id": cluster_id,
        "cluster_id": cluster_id,
        "symbol": "NVDA",
        "primary_category": "SEC_FILING",
        "title": title,
        "sources_json": ["SEC_EDGAR"],
        "importance_score": importance_score,
        "primary_ticker_score": primary_ticker_score,
        "impact_score": impact_score,
        "sentiment_score": 0.6,
        "latest_time": datetime.now(UTC),
    }


class SelectEventsForLlmTests(unittest.TestCase):
    def test_excludes_low_primary_ticker_score(self) -> None:
        events = [_event("a", primary_ticker_score=65.0)]
        self.assertEqual(select_events_for_llm(events), [])

    def test_excludes_low_importance(self) -> None:
        events = [_event("a", importance_score=45.0)]  # Medium, not Critical/High
        self.assertEqual(select_events_for_llm(events), [])

    def test_includes_qualifying_and_caps_at_ten(self) -> None:
        events = [_event(f"e{i}", impact_score=float(i)) for i in range(15)]
        selected = select_events_for_llm(events)
        self.assertEqual(len(selected), 10)
        # Sorted by |impact_score| descending within equal importance.
        self.assertEqual(selected[0]["cluster_id"], "e14")

    def test_ranks_critical_above_high(self) -> None:
        critical = _event("crit", importance_score=90.0, impact_score=5.0)
        high = _event("high", importance_score=65.0, impact_score=90.0)
        selected = select_events_for_llm([high, critical])
        self.assertEqual(selected[0]["cluster_id"], "crit")


class ClusterFingerprintTests(unittest.TestCase):
    def test_stable_for_same_input(self) -> None:
        events = [_event("a"), _event("b")]
        self.assertEqual(cluster_fingerprint(events), cluster_fingerprint(list(reversed(events))))

    def test_changes_when_impact_score_moves(self) -> None:
        e1 = [_event("a", impact_score=10.0)]
        e2 = [_event("a", impact_score=50.0)]
        self.assertNotEqual(cluster_fingerprint(e1), cluster_fingerprint(e2))

    def test_empty_events_is_deterministic(self) -> None:
        self.assertEqual(cluster_fingerprint([]), cluster_fingerprint([]))


class BuildLlmTickerSummaryTests(unittest.TestCase):
    def test_no_qualifying_events_returns_none(self) -> None:
        events = [_event("a", primary_ticker_score=50.0)]
        summary, fingerprint = build_llm_ticker_summary("NVDA", events, api_key="sk-test")
        self.assertIsNone(summary)
        self.assertTrue(fingerprint)

    def test_missing_api_key_uses_rule_based_fallback(self) -> None:
        events = [_event("a")]
        summary, _ = build_llm_ticker_summary("NVDA", events, api_key="")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["source"], "rule_based")
        for key in SUMMARY_KEYS:
            self.assertIn(key, summary)

    @patch("news_intelligence.openai_summary._call_openai")
    def test_openai_success_path(self, mock_call) -> None:
        mock_call.return_value = {
            "ticker_summary": "NVDA filed an 8-K disclosing a new supply agreement.",
            "bullish_factors": ["New supply agreement"],
            "bearish_factors": [],
            "key_catalyst": "8-K supply agreement",
            "key_risk": None,
            "sentiment_label": "Bullish",
            "confidence": "High",
            "one_sentence_trade_context": "Bullish catalyst from a fresh SEC filing.",
            "source": "openai",
        }
        events = [_event("a")]
        summary, fingerprint = build_llm_ticker_summary("NVDA", events, api_key="sk-test")
        mock_call.assert_called_once()
        self.assertEqual(summary["source"], "openai")
        self.assertTrue(fingerprint)

    @patch("news_intelligence.openai_summary._call_openai")
    def test_openai_failure_falls_back_to_rule_based(self, mock_call) -> None:
        mock_call.return_value = None
        events = [_event("a")]
        summary, _ = build_llm_ticker_summary("NVDA", events, api_key="sk-test")
        self.assertEqual(summary["source"], "rule_based")

    @patch("news_intelligence.openai_summary._call_openai")
    def test_cache_hit_skips_openai_call(self, mock_call) -> None:
        events = [_event("a")]
        fingerprint = cluster_fingerprint(select_events_for_llm(events))
        cached_summary = {
            "ticker_summary": "cached summary",
            "bullish_factors": [],
            "bearish_factors": [],
            "key_catalyst": None,
            "key_risk": None,
            "sentiment_label": "Neutral",
            "confidence": "Low",
            "one_sentence_trade_context": "cached summary",
        }
        summary, out_fingerprint = build_llm_ticker_summary(
            "NVDA",
            events,
            cached_hash=fingerprint,
            cached_summary=cached_summary,
            api_key="sk-test",
        )
        mock_call.assert_not_called()
        self.assertEqual(summary["source"], "cached")
        self.assertEqual(out_fingerprint, fingerprint)

    @patch("news_intelligence.openai_summary._call_openai")
    def test_cache_miss_when_events_change(self, mock_call) -> None:
        mock_call.return_value = None  # force rule-based path so we don't need a real payload
        old_events = [_event("a", impact_score=10.0)]
        stale_fingerprint = cluster_fingerprint(select_events_for_llm(old_events))
        new_events = [_event("a", impact_score=90.0)]
        summary, out_fingerprint = build_llm_ticker_summary(
            "NVDA",
            new_events,
            cached_hash=stale_fingerprint,
            cached_summary={"ticker_summary": "stale"},
            api_key="sk-test",
        )
        self.assertNotEqual(out_fingerprint, stale_fingerprint)
        self.assertEqual(summary["source"], "rule_based")
        mock_call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
