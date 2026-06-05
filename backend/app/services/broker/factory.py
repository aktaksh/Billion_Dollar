from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.services.broker.base import BrokerClient
from app.services.broker.mock_client import MockBrokerClient
from app.services.broker.tws_client import TwsBrokerClient


@lru_cache(maxsize=1)
def get_broker_client() -> BrokerClient:
    if settings.broker_backend == "mock":
        return MockBrokerClient()
    if settings.broker_backend == "tws":
        return TwsBrokerClient()
    raise RuntimeError(f"Unsupported broker_backend={settings.broker_backend!r}")
