"""Unit tests for News Intelligence (mocked HTTP + pure logic)."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.db import get_engine, init_db
from news_intelligence.news_deduplicator import deduplicate_items, is_similar, normalize_headline
from news_intelligence.news_models import NewsItem, normalize_finnhub_company, normalize_sec_filing
from news_intelligence.news_relevance import classify_event_type, compute_impact, compute_relevance
from news_intelligence.news_repository import NewsRepository
from news_intelligence.news_sentiment_rules import score_sentiment


class NewsDeduplicatorTests(unittest.TestCase):
    def test_normalize_headline_strips_publisher(self):
        h = normalize_headline("Apple beats earnings - Reuters")
        self.assertNotIn("reuters", h)

    def test_similar_headlines(self):
        a = normalize_headline("NVIDIA stock rises on AI demand")
        b = normalize_headline("NVIDIA stock rises on AI demand!")
        self.assertTrue(is_similar(a, b))

    def test_dedup_handles_mixed_timezone(self):
        from datetime import UTC, datetime

        from news_intelligence.news_deduplicator import deduplicate_items

        item = NewsItem(
            provider="FINNHUB",
            source="test",
            symbol="NVDA",
            category="company_news",
            headline="NVDA rises",
            summary="",
            url="http://example.com/tz-test",
            published_at=datetime.now(UTC),
        )
        repo = MagicMock()
        repo.find_recent_items.return_value = [
            NewsItem(
                provider="FINNHUB",
                source="test",
                symbol="NVDA",
                category="company_news",
                headline="Other",
                summary="",
                url="http://example.com/other",
                published_at=datetime.now(),  # naive from SQLite
            )
        ]
        repo.url_exists.return_value = False
        unique, _ = deduplicate_items([item], repo)
        self.assertEqual(len(unique), 1)


class NewsSentimentTests(unittest.TestCase):
    def test_bullish_keywords(self):
        item = NewsItem(
            provider="FINNHUB",
            source="test",
            symbol="NVDA",
            category="company_news",
            headline="Company beats earnings and raises guidance",
            summary="",
            url="http://example.com/1",
            published_at=datetime.now(UTC),
        )
        score_sentiment(item)
        self.assertEqual(item.sentiment_label, "bullish")
        self.assertEqual(item.sentiment_score, 1.0)

    def test_bearish_keywords(self):
        item = NewsItem(
            provider="FINNHUB",
            source="test",
            symbol="NVDA",
            category="company_news",
            headline="Company misses estimates amid weak demand",
            summary="",
            url="http://example.com/2",
            published_at=datetime.now(UTC),
        )
        score_sentiment(item)
        self.assertEqual(item.sentiment_label, "bearish")


class NewsRelevanceTests(unittest.TestCase):
    def test_sec_filing_relevance(self):
        item = NewsItem(
            provider="SEC_EDGAR",
            source="SEC",
            symbol="AAPL",
            category="filing",
            headline="AAPL filed 10-K",
            summary="",
            url="http://sec.gov/1",
            published_at=datetime.now(UTC),
        )
        self.assertEqual(compute_relevance(item), 1.0)

    def test_impact_calculation(self):
        impact = compute_impact(1.0, 0.8, "earnings")
        self.assertAlmostEqual(impact, 0.8)


class NewsNormalizerTests(unittest.TestCase):
    def test_finnhub_company_normalizer(self):
        raw = {
            "headline": "Test headline",
            "summary": "Summary",
            "url": "http://x.com",
            "datetime": 1700000000,
            "source": "CNBC",
            "related": "NVDA",
        }
        item = normalize_finnhub_company(raw, "NVDA")
        self.assertEqual(item.symbol, "NVDA")
        self.assertEqual(item.provider, "FINNHUB")

    def test_sec_filing_normalizer(self):
        item = normalize_sec_filing(
            symbol="AAPL",
            form_type="8-K",
            filing_date="20240115",
            accession="0000320193-24-000001",
            primary_document="aapl-8k.htm",
            cik="320193",
        )
        self.assertEqual(item.event_type, "legal_regulatory")
        self.assertIn("sec.gov", item.url)


class NewsRepositoryTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "test.db"
        self.engine = get_engine(f"sqlite:///{db_path}")
        init_db(self.engine)
        self.repo = NewsRepository(self.engine)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_insert_and_url_dedup(self):
        item = NewsItem(
            provider="FINNHUB",
            source="test",
            symbol="NVDA",
            category="company_news",
            headline="Test",
            summary="",
            url="http://example.com/dup",
            published_at=datetime.now(UTC),
            sentiment_label="neutral",
        )
        saved, skipped = self.repo.insert_items_batch([item], set())
        self.assertEqual(saved, 1)
        saved2, skipped2 = self.repo.insert_items_batch([item], set())
        self.assertEqual(saved2, 0)
        self.assertEqual(skipped2, 1)


class FinnhubClientTests(unittest.TestCase):
    @patch("news_intelligence.finnhub_client.httpx.Client")
    def test_fetch_market_news(self, mock_client_cls):
        from news_intelligence.finnhub_client import FinnhubClient
        from news_intelligence.news_config import NewsConfig

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"headline": "Market news", "datetime": 1700000000}]
        mock_client_cls.return_value.get.return_value = mock_resp

        cfg = NewsConfig(finnhub_api_key="test-key", sec_user_agent="App test@example.com")
        client = FinnhubClient(cfg)
        data = client.fetch_market_news()
        client.close()
        self.assertEqual(len(data), 1)


@unittest.skipUnless(os.getenv("FINNHUB_API_KEY") and os.getenv("SEC_USER_AGENT"), "live keys required")
class NewsLiveIntegrationTests(unittest.TestCase):
    def test_live_pipeline_smoke(self):
        from news_intelligence.news_config import load_config
        from news_intelligence.news_orchestrator import run_news_pipeline

        cfg = load_config()
        summary = run_news_pipeline(
            symbols=["NVDA"],
            from_date=datetime.now(UTC) - timedelta(days=3),
            to_date=datetime.now(UTC),
            config=cfg,
        )
        self.assertGreaterEqual(summary.total_fetched, 0)


if __name__ == "__main__":
    unittest.main()
