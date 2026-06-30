from __future__ import annotations

from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings


class OptionsChainScheduler:
    """APScheduler jobs for options-chain metadata and quote refresh."""

    def __init__(
        self,
        *,
        metadata_fn: Callable[[str], None],
        quote_fn: Callable[[str], None],
        full_scan_fn: Callable[[str], None] | None = None,
        broker_connected_fn: Callable[[], bool] | None = None,
    ) -> None:
        self._metadata_fn = metadata_fn
        self._quote_fn = quote_fn
        self._full_scan_fn = full_scan_fn or (lambda sym: (self._metadata_fn(sym), self._quote_fn(sym)))
        self._broker_connected = broker_connected_fn or (lambda: True)
        self._scheduler = BackgroundScheduler(job_defaults={"coalesce": True, "max_instances": 1})
        self.last_status = "idle"

    def start(self) -> None:
        if not settings.options_chain.enabled:
            self.last_status = "disabled"
            return
        if self._scheduler.running:
            return
        cfg = settings.options_chain
        for symbol in cfg.symbols:
            sym = symbol.strip().upper()
            if not sym:
                continue
            self._scheduler.add_job(
                self._metadata_fn,
                "interval",
                minutes=cfg.metadata_refresh_minutes,
                args=[sym],
                id=f"options-metadata-{sym}",
                replace_existing=True,
            )
            self._scheduler.add_job(
                self._quote_fn,
                "interval",
                seconds=cfg.refresh_seconds,
                args=[sym],
                id=f"options-quote-{sym}",
                replace_existing=True,
            )
            if self._broker_connected():
                self._metadata_fn(sym)
                self._quote_fn(sym)
        self._scheduler.start()
        self.last_status = "running"

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self.last_status = "stopped"

    def trigger_quote_scan(self, symbol: str) -> bool:
        sym = symbol.strip().upper()
        if not settings.options_chain.is_scanner_symbol(sym):
            return False
        self._scheduler.add_job(
            self._quote_fn,
            args=[sym],
            id=f"options-quote-manual-{sym}",
            replace_existing=True,
            max_instances=1,
        )
        return True

    def trigger_full_scan(self, symbol: str) -> bool:
        """Enqueue metadata refresh + quote scan in the scheduler thread (non-blocking for HTTP)."""
        sym = symbol.strip().upper()
        if not settings.options_chain.is_scanner_symbol(sym):
            return False
        if not self._scheduler.running:
            return False
        self._scheduler.add_job(
            self._full_scan_fn,
            args=[sym],
            id=f"options-full-scan-{sym}",
            replace_existing=True,
            max_instances=1,
        )
        return True
