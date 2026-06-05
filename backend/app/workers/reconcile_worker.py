from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from typing import Callable
from uuid import uuid4


class ReconcileWorker:
    def __init__(
        self,
        *,
        interval_seconds: int,
        mismatch_halt_seconds: int,
        evaluate_fn: Callable[[], dict],
        emit_halt_fn: Callable[[dict], None] | None = None,
    ) -> None:
        self._interval_seconds = max(15, interval_seconds)
        self._mismatch_halt_seconds = max(60, mismatch_halt_seconds)
        self._evaluate_fn = evaluate_fn
        self._emit_halt_fn = emit_halt_fn
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_run_at: str | None = None
        self.last_status: str = "idle"
        self.last_blocking_count: int = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="reconcile-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def tick_once(self) -> dict:
        result = self._evaluate_fn()
        self.last_run_at = datetime.now(UTC).isoformat()
        blocking = int(result.get("blocking_count", 0))
        self.last_blocking_count = blocking
        self.last_status = str(result.get("status", "ok"))
        stale_seconds = int(result.get("oldest_blocking_age_seconds", 0))
        if blocking > 0 and stale_seconds >= self._mismatch_halt_seconds and self._emit_halt_fn:
            halt_id = f"halt_reconcile_worker_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:6]}"
            self._emit_halt_fn(
                {
                    "halt_id": halt_id,
                    "scope": "global",
                    "reason_code": "RECONCILE_WORKER_ESCALATION",
                    "reason_detail": f"{blocking} blocking mismatches older than {self._mismatch_halt_seconds}s",
                    "trigger_metrics": f"blocking_count={blocking};age_seconds={stale_seconds}",
                    "start_time": datetime.now(UTC).isoformat(),
                    "end_time": None,
                    "cleared_by": None,
                }
            )
            self.last_status = "halt_emitted"
        return result

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick_once()
            except Exception:
                self.last_status = "error"
            self._stop.wait(self._interval_seconds)
