from __future__ import annotations

import os

import pytest

from app.engines.ingestion_engine import normalize_option_chain_from_tws
from app.services.broker.factory import get_broker_client
from app.services.broker.mock_client import MockBrokerClient
from app.services.broker_session import connect_broker_session, evaluate_broker_connection


@pytest.fixture
def mock_broker() -> MockBrokerClient:
    get_broker_client.cache_clear()
    os.environ["BROKER_BACKEND"] = "mock"
    from app.config import settings

    settings.broker_backend = "mock"
    client = get_broker_client()
    assert isinstance(client, MockBrokerClient)
    client.connect()
    yield client
    client.disconnect()
    get_broker_client.cache_clear()


def test_evaluate_broker_connection_mock(mock_broker: MockBrokerClient) -> None:
    state = evaluate_broker_connection()
    assert state["connected"] is True
    assert state["read_only"] is True


def test_connect_broker_session_mock(mock_broker: MockBrokerClient) -> None:
    result = connect_broker_session()
    assert result["status"] == "connected"


def test_mock_option_chain(mock_broker: MockBrokerClient) -> None:
    rows, source, _reason = mock_broker.option_chain(symbol="QQQ", last_price=480.0)
    assert source == "mock"
    assert len(rows) > 0


def test_normalize_option_chain_from_tws(mock_broker: MockBrokerClient) -> None:
    rows, source, _ = normalize_option_chain_from_tws(
        ticker="QQQ",
        last_price=480.0,
        broker_connected=True,
        fetch_chain=lambda: mock_broker.option_chain(symbol="QQQ", last_price=480.0),
        allow_mock_fallback=True,
    )
    assert source in {"broker", "mock"}
    assert rows


@pytest.mark.tws
@pytest.mark.skipif(os.environ.get("TWS_INTEGRATION") != "1", reason="Set TWS_INTEGRATION=1 with TWS paper running")
def test_tws_connect_integration() -> None:
    get_broker_client.cache_clear()
    os.environ["BROKER_BACKEND"] = "tws"
    from app.config import settings

    settings.broker_backend = "tws"
    client = get_broker_client()
    state = client.connect()
    assert state.broker_connected
    snap = client.market_snapshot("QQQ")
    assert snap is not None
    client.disconnect()
