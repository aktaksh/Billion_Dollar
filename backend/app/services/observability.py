from __future__ import annotations

import json
import logging
import time
from collections import Counter
from typing import Callable

logger = logging.getLogger("billion_dollar.api")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

REQUEST_COUNTER: Counter[str] = Counter()
ERROR_COUNTER: Counter[str] = Counter()


def log_request(*, method: str, path: str, status_code: int, duration_ms: float) -> None:
    key = f"{method} {path}"
    REQUEST_COUNTER[key] += 1
    payload = {
        "event": "http_request",
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "request_count": REQUEST_COUNTER[key],
    }
    logger.info(json.dumps(payload, sort_keys=True))


def log_runtime_event(*, event: str, **fields: object) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, sort_keys=True, default=str))


def metrics_snapshot() -> dict:
    return {
        "requests": dict(REQUEST_COUNTER),
        "errors": dict(ERROR_COUNTER),
    }


def request_timing_middleware(app_call: Callable):
    async def middleware(scope, receive, send):
        if scope.get("type") != "http":
            await app_call(scope, receive, send)
            return
        started = time.perf_counter()
        status_holder = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        try:
            await app_call(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            method = scope.get("method", "")
            duration_ms = (time.perf_counter() - started) * 1000.0
            log_request(method=method, path=path, status_code=status_holder["code"], duration_ms=duration_ms)
            if status_holder["code"] >= 500:
                ERROR_COUNTER[path] += 1

    return middleware
