"""Shared pytest fixtures — fast smoke tests without live IBKR/network."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class MockBroker:
    """Stub broker so smoke tests never block on TWS/Gateway connect."""

    name = "mock"

    def is_available(self) -> tuple[bool, str]:
        return False, "mock broker (tests)"

    def list_option_positions(self) -> list[dict[str, Any]]:
        return []

    def fetch_quotes_for_trades(self, trades: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
        return {}

    def fetch_underlying_price(self, symbol: str) -> float:
        return 0.0

    def enrich_spreads_with_quotes(self, spreads: list[Any]) -> int:
        return 0


@pytest.fixture
def mock_broker() -> MockBroker:
    return MockBroker()


@pytest.fixture
def client(mock_broker: MockBroker) -> TestClient:
    """FastAPI client with broker/IBKR-news disabled — use in smoke/API tests only."""
    from app.config import settings

    orig_ibkr_news = settings.ibkr_news_enabled
    settings.ibkr_news_enabled = False

    with (
        patch("app.services.broker.broker_provider.get_broker_provider", return_value=mock_broker),
        patch("app.services.market_regime.data_adapters.get_broker_provider", return_value=mock_broker),
    ):
        from app.main import app

        with TestClient(app) as test_client:
            yield test_client

    settings.ibkr_news_enabled = orig_ibkr_news
