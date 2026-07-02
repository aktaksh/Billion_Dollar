from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator

from ib_insync import IB, util

from src.config import Settings, get_settings


def _quiet_ib_logging() -> None:
    util.logToConsole(False)
    for name in ("ib_insync", "ib_insync.client", "ib_insync.wrapper", "ib_insync.ib"):
        logging.getLogger(name).setLevel(logging.WARNING)


class IbSession:
    """Read-only IB Gateway session. Never places or modifies orders."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.ib = IB()
        self._connected = False

    def connect(self) -> None:
        util.startLoop()
        _quiet_ib_logging()
        self.ib.connect(
            self.settings.ib_host,
            self.settings.ib_port,
            clientId=self.settings.ib_client_id,
            readonly=self.settings.ib_read_only,
            timeout=15,
        )
        self.ib.reqMarketDataType(self.settings.ib_market_data_type)
        self._connected = True

    def disconnect(self) -> None:
        if self._connected and self.ib.isConnected():
            self.ib.disconnect()
        self._connected = False

    def pace(self) -> None:
        time.sleep(self.settings.historical_pacing_seconds)

    def __enter__(self) -> IB:
        self.connect()
        return self.ib

    def __exit__(self, *_exc: object) -> None:
        self.disconnect()


@contextmanager
def ib_session(settings: Settings | None = None) -> Generator[IB, None, None]:
    session = IbSession(settings)
    try:
        session.connect()
        yield session.ib
    finally:
        session.disconnect()
