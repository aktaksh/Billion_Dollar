from __future__ import annotations

import threading
import time
from typing import Callable


class BrokerTickleWorker:
    """Keeps IBKR Client Portal Gateway session alive (recommended ~every 60s)."""

    def __init__(self, *, interval_seconds: int, tickle_fn: Callable[[], None]) -> None:
        self._interval_seconds = max(30, interval_seconds)
        self._tickle_fn = tickle_fn
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_run_at: str | None = None
        self.last_status: str = "idle"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="broker-tickle-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def tick_once(self) -> None:
        try:
            self._tickle_fn()
            self.last_status = "ok"
        except Exception:
            self.last_status = "error"
        self.last_run_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick_once()
            self._stop.wait(self._interval_seconds)
