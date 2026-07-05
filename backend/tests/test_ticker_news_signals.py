"""Unit tests for the ticker-level news intelligence redesign:
primary ticker detection, canonical event classification, the new
impact_score formula, dedup/cluster thresholds, and ticker signal
aggregation — covering the exact spec examples from the architecture plan.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.db import get_engine, init_db
from app.repositories.news_events_repository import NewsEventsRepository
from news_intelligence.news_categories import (
    CANONICAL_CATEGORIES,
    IMPORTANCE_SCORES,
    to_legacy_event_type,
)
from news_intelligence.news_clusterer import cluster_events, is_general_market_finnhub
from news_intelligence.news_config import (
    CLUSTER_SIMILARITY_THRESHOLD,
    CLUSTER_SIMILARITY_THRESHOLD_SAME_FAMILY,
    DEDUP_WINDOW_HOURS,
    HEADLINE_SIMILARITY_THRESHOLD,
    PRIMARY_TICKER_MIN_FOR_CATALYST,
    PRIMARY_TICKER_MIN_FOR_INCLUSION,
)
from news_intelligence.news_models import NewsItem
from news_intelligence.news_relevance import classify_event_category, compute_impact_score
from news_intelligence.primary_ticker_detector import (
    compute_primary_ticker_score,
    resolve_primary_symbol,
)
from news_intelligence.ticker_registry import TickerRegistry
from news_intelligence.ticker_signal_builder import build_ticker_signals


def _item(
    headline: str,
    *,
    provider: str = "FINNHUB",
    symbol: str = "NVDA",
    symbols: list[str] | None = None,
    category: str = "company_news",
    summary: str = "",
    published_at: datetime | None = None,
    raw_json: dict | None = None,
) -> NewsItem:
    return NewsItem(
        provider=provider,
        source=provider,
        symbol=symbol,
        symbols=symbols or [symbol],
        category=category,
        headline=headline,
        summary=summary,
        url=f"http://example.com/{abs(hash(headline))}",
        published_at=published_at or datetime.now(UTC),
        raw_json=raw_json or {},
    )


def _registry() -> TickerRegistry:
    reg = TickerRegistry()
    reg.register("NVDA", "NVIDIA Corporation")
    reg.register("AAPL", "Apple Inc.")
    reg.register("PLTR", "Palantir Technologies")
    reg.register("TSLA", "Tesla Inc.")
    return reg


class PrimaryTickerDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = _registry()

    def test_generali_stake_in_nvidia_scores_nvda(self) -> None:
        item = _item("Generali has stake in NVIDIA", provider="SEC_EDGAR", symbol="NVDA")
        score = compute_primary_ticker_score(item, "NVDA", registry=self.reg)
        self.assertGreaterEqual(score, PRIMARY_TICKER_MIN_FOR_INCLUSION)

    def test_palantir_headline_resolves_to_pltr_not_nvda(self) -> None:
        # Fetched under NVDA's query (e.g. broad tech feed), but the headline
        # is really about Palantir.
        item = _item(
            "Palantir upgraded to Buy by analyst",
            provider="FINNHUB",
            symbol="NVDA",
            symbols=["NVDA", "PLTR"],
        )
        symbol, score = resolve_primary_symbol(item, registry=self.reg)
        self.assertEqual(symbol, "PLTR")
        self.assertGreaterEqual(score, PRIMARY_TICKER_MIN_FOR_INCLUSION)

    def test_tesla_headline_resolves_to_tsla(self) -> None:
        item = _item(
            "Tesla beats delivery estimates",
            provider="FINNHUB",
            symbol="QQQ",
            symbols=["QQQ", "TSLA"],
        )
        symbol, _score = resolve_primary_symbol(item, registry=self.reg)
        self.assertEqual(symbol, "TSLA")

    def test_nvidia_files_8k_scores_high_for_nvda(self) -> None:
        item = _item(
            "Nvidia Files 8-K",
            provider="SEC_EDGAR",
            symbol="NVDA",
            raw_json={"form_type": "8-K"},
        )
        score = compute_primary_ticker_score(item, "NVDA", registry=self.reg)
        self.assertGreaterEqual(score, PRIMARY_TICKER_MIN_FOR_CATALYST)

    def test_dow_jones_futures_capped_at_25(self) -> None:
        item = _item(
            "Dow Jones Futures: Stock Market Today Signals Weak Open",
            provider="FINNHUB",
            symbol="NVDA",
        )
        score = compute_primary_ticker_score(item, "NVDA", registry=self.reg)
        self.assertLessEqual(score, 25)

    def test_broad_market_excludes_from_inclusion(self) -> None:
        item = _item("Wall Street stocks to watch this week", symbol="NVDA")
        score = compute_primary_ticker_score(item, "NVDA", registry=self.reg)
        self.assertLess(score, PRIMARY_TICKER_MIN_FOR_INCLUSION)

    def test_different_company_subject_caps_at_30(self) -> None:
        item = _item(
            "Apple Inc reports record iPhone sales",
            provider="FINNHUB",
            symbol="NVDA",
            symbols=["NVDA"],
        )
        score = compute_primary_ticker_score(item, "NVDA", registry=self.reg)
        self.assertLessEqual(score, 30)


class EventCategoryClassifierTests(unittest.TestCase):
    def test_fourteen_canonical_categories(self) -> None:
        self.assertEqual(len(CANONICAL_CATEGORIES), 14)

    def test_sec_filing_priority_over_legal(self) -> None:
        item = _item("Nvidia Files 8-K", provider="SEC_EDGAR", raw_json={"form_type": "8-K"})
        self.assertEqual(classify_event_category(item), "SEC_FILING")
        self.assertEqual(to_legacy_event_type("SEC_FILING"), "sec_filing")

    def test_institutional_ownership(self) -> None:
        item = _item("Generali has stake in NVIDIA", provider="FINNHUB")
        self.assertEqual(classify_event_category(item), "INSTITUTIONAL_OWNERSHIP")

    def test_general_market(self) -> None:
        item = _item("Dow Jones Futures: Stock market today", provider="FINNHUB", category="market_news", symbol="MARKET")
        self.assertEqual(classify_event_category(item), "GENERAL_MARKET")

    def test_analyst_action_not_earnings(self) -> None:
        item = _item("Palantir upgraded to Buy by analyst")
        self.assertEqual(classify_event_category(item), "ANALYST_ACTION")

    def test_earnings_requires_strong_phrase_not_bare_keyword(self) -> None:
        # Mentions "earnings" but isn't an actual earnings report — should
        # not be misclassified purely on keyword presence.
        item = _item("Analyst previews upcoming earnings season for chipmakers")
        self.assertNotEqual(classify_event_category(item), "EARNINGS")

    def test_earnings_with_strong_phrase(self) -> None:
        item = _item("Tesla beats delivery estimates and reports record revenue of $25B")
        self.assertEqual(classify_event_category(item), "EARNINGS")

    def test_priority_order_matches_categories(self) -> None:
        from news_intelligence.news_categories import PRIORITY_ORDER

        self.assertEqual(PRIORITY_ORDER, CANONICAL_CATEGORIES)
        self.assertEqual(PRIORITY_ORDER[0], "SEC_FILING")
        self.assertEqual(PRIORITY_ORDER[-1], "OTHER")


class ImpactScoreFormulaTests(unittest.TestCase):
    def test_impact_score_range(self) -> None:
        score = compute_impact_score(
            sentiment_score=1.0,
            primary_ticker_score=100,
            category="SEC_FILING",
            source_quality=1.0,
            published_at=datetime.now(UTC),
        )
        self.assertLessEqual(score, 100)
        self.assertGreaterEqual(score, -100)
        self.assertAlmostEqual(score, 90.0, delta=0.5)  # importance(SEC_FILING)=90

    def test_impact_score_zero_sentiment(self) -> None:
        score = compute_impact_score(
            sentiment_score=0.0,
            primary_ticker_score=100,
            category="EARNINGS",
            source_quality=1.0,
            published_at=datetime.now(UTC),
        )
        self.assertEqual(score, 0.0)

    def test_recency_decays_impact(self) -> None:
        now = datetime.now(UTC)
        fresh = compute_impact_score(
            sentiment_score=1.0, primary_ticker_score=100, category="EARNINGS",
            source_quality=1.0, published_at=now, now=now,
        )
        stale = compute_impact_score(
            sentiment_score=1.0, primary_ticker_score=100, category="EARNINGS",
            source_quality=1.0, published_at=now - timedelta(days=6), now=now,
        )
        self.assertGreater(fresh, stale)

    def test_importance_scores_cover_all_categories(self) -> None:
        for cat in CANONICAL_CATEGORIES:
            self.assertIn(cat, IMPORTANCE_SCORES)


class DedupClusterConstantsTests(unittest.TestCase):
    def test_dedup_thresholds_updated(self) -> None:
        self.assertEqual(HEADLINE_SIMILARITY_THRESHOLD, 0.86)
        self.assertEqual(DEDUP_WINDOW_HOURS, 72)

    def test_cluster_thresholds(self) -> None:
        self.assertEqual(CLUSTER_SIMILARITY_THRESHOLD, 0.70)
        self.assertEqual(CLUSTER_SIMILARITY_THRESHOLD_SAME_FAMILY, 0.55)


class ClusteringTests(unittest.TestCase):
    def _enriched(self, headline: str, *, provider="IBKR", symbol="NVDA", sentiment=0.5, ptscore=80) -> NewsItem:
        item = _item(headline, provider=provider, symbol=symbol)
        item.sentiment_score = sentiment
        item.resolved_symbol = symbol
        item.primary_ticker_score = ptscore
        item.event_category = "EARNINGS"
        item.source_quality = 0.9
        item.impact_score_v2 = compute_impact_score(
            sentiment_score=sentiment, primary_ticker_score=ptscore,
            category="EARNINGS", source_quality=0.9, published_at=item.published_at,
        )
        return item

    def test_finnhub_general_market_excluded(self) -> None:
        item = _item("Dow Jones Futures today", provider="FINNHUB", category="market_news", symbol="NVDA")
        item.resolved_symbol = "NVDA"
        item.primary_ticker_score = 90  # even if scored high, must be excluded
        item.event_category = "GENERAL_MARKET"
        item.impact_score_v2 = 50.0
        self.assertTrue(is_general_market_finnhub(item))
        events = cluster_events([item])
        self.assertEqual(events, [])

    def test_low_primary_ticker_score_excluded_from_clusters(self) -> None:
        item = self._enriched("Some tangential mention of NVDA", ptscore=30)
        events = cluster_events([item])
        self.assertEqual(events, [])

    def test_similar_headlines_within_same_family_cluster_at_looser_threshold(self) -> None:
        a = self._enriched("NVIDIA reports record quarterly revenue growth", provider="IBKR")
        b = self._enriched("NVIDIA posts record quarterly revenue increase", provider="IBKR")
        events = cluster_events([a, b])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_count"], 1)  # same source name "IBKR"

    def test_dissimilar_headlines_form_separate_clusters(self) -> None:
        a = self._enriched("NVIDIA reports record quarterly revenue growth")
        b = self._enriched("NVIDIA announces new partnership with major cloud provider")
        events = cluster_events([a, b])
        self.assertEqual(len(events), 2)


class TickerSignalBuilderTests(unittest.TestCase):
    def _cluster(self, symbol: str, impact: float, ptscore: int, category="EARNINGS") -> dict:
        now = datetime.now(UTC)
        return {
            "id": "x", "cluster_id": "c1", "symbol": symbol, "primary_category": category,
            "subtype": None, "title": f"{symbol} headline", "summary": None,
            "source_count": 2, "sources_json": ["IBKR", "SEC"], "article_ids_json": ["a", "b"],
            "earliest_time": now, "latest_time": now, "sentiment_score": 0.5,
            "importance_score": IMPORTANCE_SCORES.get(category, 50), "primary_ticker_score": ptscore,
            "source_quality_score": 0.9, "impact_score": impact, "confidence": "High",
            "created_at": now, "updated_at": now,
        }

    def test_bullish_bias(self) -> None:
        clusters = [self._cluster("NVDA", 40, 80), self._cluster("NVDA", 30, 70)]
        signals = build_ticker_signals(clusters)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["news_bias"], "Bullish")
        self.assertEqual(signals[0]["top_catalyst"], "NVDA headline")

    def test_bearish_bias(self) -> None:
        clusters = [self._cluster("NVDA", -40, 80), self._cluster("NVDA", -30, 70)]
        signals = build_ticker_signals(clusters)
        self.assertEqual(signals[0]["news_bias"], "Bearish")
        self.assertIsNotNone(signals[0]["top_risk"])

    def test_mixed_bias(self) -> None:
        clusters = [self._cluster("NVDA", 30, 80), self._cluster("NVDA", -28, 70)]
        signals = build_ticker_signals(clusters)
        self.assertEqual(signals[0]["news_bias"], "Mixed")

    def test_low_primary_ticker_score_excluded_from_bias(self) -> None:
        # primary_ticker_score below 60 -> doesn't qualify -> Neutral, no catalyst.
        clusters = [self._cluster("NVDA", 40, 50)]
        signals = build_ticker_signals(clusters)
        self.assertEqual(signals[0]["news_bias"], "Neutral")
        self.assertIsNone(signals[0]["top_catalyst"])


class NewsEventsRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "test.db"
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)
        self.repo = NewsEventsRepository(self.engine)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_upsert_and_get_ticker_signal(self) -> None:
        now = datetime.now(UTC)
        signal = {
            "symbol": "NVDA", "news_bias": "Bullish", "news_quality_score": 85.0,
            "catalyst_strength_score": 40.0, "net_impact_score": 35.0,
            "bullish_count": 2, "bearish_count": 0, "neutral_count": 1,
            "top_catalyst": "NVDA beats earnings", "top_risk": None,
            "llm_summary": "2 bullish catalysts", "confidence": "High", "last_updated": now,
        }
        self.repo.upsert_ticker_signals([signal])
        row = self.repo.get_ticker_signal("NVDA")
        self.assertIsNotNone(row)
        self.assertEqual(row["news_bias"], "Bullish")

        # Upsert again with updated values — should update, not duplicate.
        signal["news_bias"] = "Bearish"
        self.repo.upsert_ticker_signals([signal])
        rows = self.repo.list_ticker_signals()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["news_bias"], "Bearish")

    def test_replace_events_for_symbols_is_idempotent(self) -> None:
        now = datetime.now(UTC)
        event = {
            "id": "e1", "cluster_id": "c1", "symbol": "NVDA", "primary_category": "EARNINGS",
            "subtype": None, "title": "NVDA beats", "summary": None, "source_count": 1,
            "sources_json": ["IBKR"], "article_ids_json": ["a"], "earliest_time": now,
            "latest_time": now, "sentiment_score": 0.5, "importance_score": 80,
            "primary_ticker_score": 90, "source_quality_score": 0.9, "impact_score": 40,
            "confidence": "High", "created_at": now, "updated_at": now,
        }
        self.repo.replace_events_for_symbols(["NVDA"], [event])
        self.assertEqual(len(self.repo.list_events_for_symbol("NVDA")), 1)
        self.repo.replace_events_for_symbols(["NVDA"], [event])
        self.assertEqual(len(self.repo.list_events_for_symbol("NVDA")), 1)


class NewsSignalServiceTickerSignalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "test.db"
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_signal_for_symbol_prefers_ticker_signal_row(self) -> None:
        from news_intelligence.news_repository import NewsRepository
        from app.services.market_intelligence.news_signal_service import NewsSignalService

        events_repo = NewsEventsRepository(self.engine)
        now = datetime.now(UTC)
        events_repo.upsert_ticker_signals([{
            "symbol": "NVDA", "news_bias": "Bullish", "news_quality_score": 90.0,
            "catalyst_strength_score": 50.0, "net_impact_score": 40.0,
            "bullish_count": 3, "bearish_count": 0, "neutral_count": 0,
            "top_catalyst": "NVDA beats earnings", "top_risk": None,
            "llm_summary": "3 bullish catalysts", "confidence": "High", "last_updated": now,
        }])

        service = NewsSignalService(NewsRepository(self.engine))
        sig = service.signal_for_symbol("NVDA")
        self.assertEqual(sig["label"], "Bullish")
        self.assertEqual(sig["top_catalyst"], "NVDA beats earnings")
        self.assertGreater(sig["news_score_0_to_100"], 50)

    def test_signal_for_symbol_falls_back_when_no_row(self) -> None:
        from news_intelligence.news_repository import NewsRepository
        from app.services.market_intelligence.news_signal_service import NewsSignalService

        service = NewsSignalService(NewsRepository(self.engine))
        sig = service.signal_for_symbol("ZZZZ")
        self.assertEqual(sig["label"], "Neutral")
        self.assertEqual(sig["news_score_0_to_100"], 50)


class TdeNewsFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "test.db"
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_neutral_fallback_when_no_signal_row(self) -> None:
        from app.services.trade_decision.trade_score_calculator import TradeScoreCalculator

        calc = TradeScoreCalculator(engine=self.engine)
        components = calc.component_scores({"symbol": "ZZZZ", "daily_indicators": {}, "score": {}}, {"final": 0})
        self.assertEqual(components["news"], 50.0)

    def test_uses_ticker_signal_when_present(self) -> None:
        from app.services.trade_decision.trade_score_calculator import TradeScoreCalculator

        events_repo = NewsEventsRepository(self.engine)
        events_repo.upsert_ticker_signals([{
            "symbol": "NVDA", "news_bias": "Bullish", "news_quality_score": 90.0,
            "catalyst_strength_score": 50.0, "net_impact_score": 40.0,
            "bullish_count": 3, "bearish_count": 0, "neutral_count": 0,
            "top_catalyst": "NVDA beats earnings", "top_risk": None,
            "llm_summary": "3 bullish catalysts", "confidence": "High",
            "last_updated": datetime.now(UTC),
        }])
        calc = TradeScoreCalculator(engine=self.engine)
        components = calc.component_scores({"symbol": "NVDA", "daily_indicators": {}, "score": {}}, {"final": 0})
        self.assertEqual(components["news"], 70.0)  # 50 + 40/2

    def test_fallback_without_engine_is_neutral_not_bullish(self) -> None:
        from app.services.trade_decision.trade_score_calculator import TradeScoreCalculator

        calc = TradeScoreCalculator()
        components = calc.component_scores({"symbol": "NVDA", "daily_indicators": {}, "score": {}}, {"final": 0})
        self.assertEqual(components["news"], 50.0)
        self.assertNotEqual(components["news"], 70.0)


class TickerRegistryTests(unittest.TestCase):
    def test_register_and_lookup(self) -> None:
        reg = TickerRegistry()
        reg.register("NVDA", "NVIDIA Corporation")
        self.assertEqual(reg.short_name("NVDA"), "NVIDIA")
        self.assertEqual(reg.company_name("NVDA"), "NVIDIA Corporation")

    def test_find_company_mentioned_excludes_target(self) -> None:
        reg = TickerRegistry()
        reg.register("NVDA", "NVIDIA Corporation")
        reg.register("AAPL", "Apple Inc.")
        found = reg.find_company_mentioned("Apple reports record iPhone sales", exclude="NVDA")
        self.assertEqual(found, "AAPL")
        self.assertIsNone(reg.find_company_mentioned("Apple reports record iPhone sales", exclude="AAPL"))

    def test_load_from_watchlist(self) -> None:
        reg = TickerRegistry()
        reg.load_from_watchlist([
            {"symbol": "NVDA", "company": "NVIDIA Corporation"},
            {"symbol": "—", "company": "—"},
        ])
        self.assertIn("NVDA", reg.all_symbols())


class OrchestratorPipelineIntegrationTests(unittest.TestCase):
    """End-to-end: mocked providers through run_news_pipeline() -> verifies
    Finnhub company-news gating (Part 1) and that ticker_news_signals gets
    populated (Parts 6/7/11)."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "test.db"
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_finnhub_company_news_skipped_when_ibkr_covers_symbol(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.services.news_intelligence.ibkr_news_client import IbkrHeadline, IbkrNewsResult
        from news_intelligence.news_config import NewsConfig
        from news_intelligence.news_orchestrator import run_news_pipeline
        from news_intelligence.news_repository import NewsRepository

        repo = NewsRepository(self.engine)
        cfg = NewsConfig(finnhub_api_key="key", sec_user_agent="App test@example.com")

        ibkr_client = MagicMock()
        ibkr_client.is_available.return_value = (True, "ok")
        ibkr_client.fetch_for_symbols.return_value = [
            IbkrNewsResult(
                symbol="NVDA",
                con_id=1,
                headlines=[
                    IbkrHeadline(
                        timestamp="2026-07-01 10:00:00",
                        provider_code="DJ-N",
                        article_id="1",
                        headline="NVIDIA reports record quarterly revenue and beats earnings estimates",
                    )
                ],
            )
        ]

        with patch("news_intelligence.news_orchestrator.FinnhubClient") as MockFinnhub, \
                patch("news_intelligence.news_orchestrator.SecEdgarClient") as MockSec:
            finnhub_instance = MockFinnhub.return_value
            finnhub_instance.fetch_market_news.return_value = []
            finnhub_instance.fetch_company_news.return_value = []
            sec_instance = MockSec.return_value
            sec_instance.fetch_recent_filings.return_value = []

            run_news_pipeline(
                symbols=["NVDA"],
                config=cfg,
                repo=repo,
                ibkr_news_client=ibkr_client,
            )

            finnhub_instance.fetch_company_news.assert_not_called()

        events_repo = NewsEventsRepository(self.engine)
        signal = events_repo.get_ticker_signal("NVDA")
        self.assertIsNotNone(signal)
        self.assertGreaterEqual(signal["net_impact_score"], 0)

    def test_finnhub_company_news_used_when_ibkr_unavailable(self) -> None:
        from unittest.mock import MagicMock, patch

        from news_intelligence.news_config import NewsConfig
        from news_intelligence.news_orchestrator import run_news_pipeline
        from news_intelligence.news_repository import NewsRepository

        repo = NewsRepository(self.engine)
        cfg = NewsConfig(finnhub_api_key="key", sec_user_agent="App test@example.com")

        ibkr_client = MagicMock()
        ibkr_client.is_available.return_value = (False, "not connected")

        with patch("news_intelligence.news_orchestrator.FinnhubClient") as MockFinnhub, \
                patch("news_intelligence.news_orchestrator.SecEdgarClient") as MockSec:
            finnhub_instance = MockFinnhub.return_value
            finnhub_instance.fetch_market_news.return_value = []
            finnhub_instance.fetch_company_news.return_value = []
            sec_instance = MockSec.return_value
            sec_instance.fetch_recent_filings.return_value = []

            run_news_pipeline(
                symbols=["NVDA"],
                config=cfg,
                repo=repo,
                ibkr_news_client=ibkr_client,
            )

            finnhub_instance.fetch_company_news.assert_called_once()


class OpenAiSummaryWiringTests(unittest.TestCase):
    """Part 8 wiring: run_news_pipeline() applies the LLM summary layer on top
    of the rule-based ticker_news_signals row it already builds."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "test.db"
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)
        self._env_patch = patch.dict(os.environ, {"OPENAI_API_KEY": ""})
        self._env_patch.start()

    def tearDown(self) -> None:
        self._env_patch.stop()
        self._tmpdir.cleanup()

    def _run_pipeline_with_sec_filing(self):
        from news_intelligence.news_config import NewsConfig
        from news_intelligence.news_orchestrator import run_news_pipeline
        from news_intelligence.news_repository import NewsRepository

        repo = NewsRepository(self.engine)
        cfg = NewsConfig(finnhub_api_key="key", sec_user_agent="App test@example.com")

        ibkr_client = MagicMock()
        ibkr_client.is_available.return_value = (False, "not connected")

        with patch("news_intelligence.news_orchestrator.FinnhubClient") as MockFinnhub, \
                patch("news_intelligence.news_orchestrator.SecEdgarClient") as MockSec:
            finnhub_instance = MockFinnhub.return_value
            finnhub_instance.fetch_market_news.return_value = []
            finnhub_instance.fetch_company_news.return_value = []
            sec_instance = MockSec.return_value
            sec_instance.fetch_recent_filings.return_value = [
                {
                    "symbol": "NVDA",
                    "form_type": "8-K",
                    "filing_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                    "accession": "0001234567-26-000123",
                    "primary_document": "nvda-8k.htm",
                    "cik": "1045810",
                    "description": "Material agreement disclosure",
                }
            ]
            run_news_pipeline(
                symbols=["NVDA"],
                config=cfg,
                repo=repo,
                ibkr_news_client=ibkr_client,
            )

        return NewsEventsRepository(self.engine)

    def test_qualifying_sec_filing_gets_rule_based_llm_summary_without_key(self) -> None:
        events_repo = self._run_pipeline_with_sec_filing()
        signal = events_repo.get_ticker_signal("NVDA")
        self.assertIsNotNone(signal)
        # An 8-K (SEC_FILING, Critical) with a strong primary-ticker match
        # qualifies for Part 8 — should get a structured rule-based summary
        # (no OPENAI_API_KEY in this test's environment).
        self.assertIsNotNone(signal.get("llm_summary_json"))
        self.assertEqual(signal["llm_summary_json"]["source"], "rule_based")
        self.assertIsNotNone(signal.get("llm_cluster_hash"))

    @patch("news_intelligence.openai_summary._call_openai")
    def test_second_identical_run_reuses_cached_summary(self, mock_call) -> None:
        mock_call.return_value = None  # never actually called when cache hits
        events_repo = self._run_pipeline_with_sec_filing()
        first = events_repo.get_ticker_signal("NVDA")
        self.assertIsNotNone(first.get("llm_summary_json"))

        first_hash = first["llm_cluster_hash"]
        events_repo2 = self._run_pipeline_with_sec_filing()
        second = events_repo2.get_ticker_signal("NVDA")
        self.assertEqual(second["llm_cluster_hash"], first_hash)


if __name__ == "__main__":
    unittest.main()
