import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("BROKER_BACKEND", "mock")

from app.config import settings
from app.services.broker.factory import get_broker_client

settings.broker_backend = "mock"
get_broker_client.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _connected_mock_broker() -> None:
    client = get_broker_client()
    client.connect()


@pytest.fixture(scope="session")
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
