from __future__ import annotations

import os

import pytest

from app.engines.ingestion_engine import normalize_option_chain_from_tws
from app.services.broker.factory import get_broker_client
from app.services.broker.mock_client import MockBrokerClient
from app.services.broker_session import connect_broker_session, evaluate_broker_connection


def _apply_tws_integration_settings() -> None:
    from app.config import settings

    settings.broker_backend = "tws"
    if port := os.environ.get("TWS_PORT"):
        settings.tws_port = int(port)


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
@pytest.mark.skipif(os.environ.get("TWS_INTEGRATION") != "1", reason="Set TWS_INTEGRATION=1 with IB Gateway/TWS running")
def test_tws_connect_integration() -> None:
    get_broker_client.cache_clear()
    os.environ["BROKER_BACKEND"] = "tws"
    _apply_tws_integration_settings()
    client = get_broker_client()
    state = client.connect()
    assert state.broker_connected
    snap = client.market_snapshot("QQQ")
    assert snap is not None
    client.disconnect()


@pytest.mark.tws
@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("TWS_INTEGRATION") != "1", reason="Set TWS_INTEGRATION=1 with IB Gateway/TWS running")
def test_tws_options_chain_scanner_integration() -> None:
    from uuid import uuid4

    from app.config import settings
    from app.db import get_engine
    from app.services.market_hours import is_us_equity_regular_session
    from app.services.options_chain_scanner import OptionsChainScanner
    from app.services.options_chain_store import get_contracts, get_scan_status

    get_broker_client.cache_clear()
    os.environ["BROKER_BACKEND"] = "tws"
    _apply_tws_integration_settings()
    client = get_broker_client()
    state = client.connect()
    assert state.broker_connected

    symbol = settings.options_chain.default_symbol or "QQQ"
    engine = get_engine()

    def _trace() -> tuple[str, str]:
        cid = f"tws_test_{uuid4().hex[:8]}"
        return cid, cid

    scanner = OptionsChainScanner(
        engine=engine,
        broker=client,
        trace_fn=_trace,
        broker_connected_fn=lambda: bool(client.connection_state().broker_connected),
    )

    assert scanner.refresh_metadata(symbol) or client.fetch_secdef_metadata(symbol)
    prior_count = len(get_contracts(engine, symbol))
    scanner.run_quote_scan(symbol)
    status = get_scan_status(engine, symbol) or {}
    scanner_status = str(status.get("scanner_status", "idle"))
    contract_count = len(get_contracts(engine, symbol))

    assert scanner_status != "failed", status.get("last_error")
    if is_us_equity_regular_session():
        assert scanner_status in {"fresh", "partial", "stale"}
        assert contract_count > 0
    elif prior_count > 0:
        assert scanner_status == "stale"
        assert contract_count == prior_count
    else:
        assert scanner_status in {"partial", "stale", "fresh"}

    client.disconnect()


@pytest.mark.tws
@pytest.mark.skipif(os.environ.get("TWS_INTEGRATION") != "1", reason="Set TWS_INTEGRATION=1 with IB Gateway/TWS running")
def test_tws_known_position_quotes() -> None:
    get_broker_client.cache_clear()
    os.environ["BROKER_BACKEND"] = "tws"
    _apply_tws_integration_settings()
    client = get_broker_client()
    state = client.connect()
    assert state.broker_connected

    fetch = getattr(client, "fetch_exact_option_quotes", None)
    assert fetch is not None
    results = fetch(
        symbol="QQQ",
        contracts=[
            {"expiry": "20260717", "strike": 710.0, "right": "C"},
            {"expiry": "20260717", "strike": 740.0, "right": "C"},
        ],
        trading_class="QQQ",
    )
    assert len(results) == 2
    for row in results:
        assert row.get("qualified") is True, row
    client.disconnect()
