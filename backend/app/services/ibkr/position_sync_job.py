from __future__ import annotations

import threading
from typing import Callable


class PositionSyncJob:
    """Optional background IBKR sync on a fixed interval."""

    def __init__(self, *, sync_fn: Callable[[], dict], interval_seconds: int = 0) -> None:
        self._sync_fn = sync_fn
        self._interval_seconds = max(0, interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict | None = None

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    def set_interval(self, seconds: int) -> None:
        self._interval_seconds = max(0, seconds)
        if self._interval_seconds == 0:
            self.stop()
        elif not self._thread or not self._thread.is_alive():
            self.start()

    def start(self) -> None:
        if self._interval_seconds <= 0:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="position-sync-job", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def run_once(self) -> dict:
        try:
            self.last_result = self._sync_fn()
        except Exception as exc:
            self.last_result = {"message": str(exc), "failed_requests": 1}
        return self.last_result or {}

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            if self._interval_seconds <= 0:
                break
            self._stop.wait(self._interval_seconds)
