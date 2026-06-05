from __future__ import annotations

import threading
import time
from typing import Callable


class TwsConnectionWorker:
    """Keeps TWS session alive and reconnects when disconnected."""

    def __init__(
        self,
        *,
        interval_seconds: int,
        heartbeat_fn: Callable[[], None],
        reconnect_fn: Callable[[], None] | None = None,
    ) -> None:
        self._interval_seconds = max(30, interval_seconds)
        self._heartbeat_fn = heartbeat_fn
        self._reconnect_fn = reconnect_fn
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_run_at: str | None = None
        self.last_status: str = "idle"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="tws-connection-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def tick_once(self) -> None:
        try:
            self._heartbeat_fn()
            self.last_status = "ok"
        except Exception:
            self.last_status = "error"
            if self._reconnect_fn:
                try:
                    self._reconnect_fn()
                    self.last_status = "reconnected"
                except Exception:
                    self.last_status = "reconnect_failed"
        self.last_run_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick_once()
            self._stop.wait(self._interval_seconds)
