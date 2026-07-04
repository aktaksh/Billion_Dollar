"""Global Refresh Status service — orchestrates Market Open Refresh."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import settings
from app.services.market_intelligence.market_intelligence_service import MarketIntelligenceService
from app.services.market_regime.market_regime_service import MarketRegimeService
from app.services.opportunity_scanner.opportunity_scanner_service import OpportunityScannerService

logger = logging.getLogger(__name__)


@dataclass
class ModuleRefreshResult:
    module: str
    status: str  # "ok" | "error"
    refreshed_at: str | None = None
    duration_ms: int = 0
    error: str | None = None


@dataclass
class MarketOpenRefreshResult:
    status: str  # "ok" | "partial" | "failed"
    modules: list[ModuleRefreshResult] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0
    next_recommended_refresh_at: str = ""
    scanner_payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "timestamps": {
                "news_refreshed_at": self._module_ts("market_intelligence"),
                "regime_refreshed_at": self._module_ts("market_regime"),
                "scanner_refreshed_at": self._module_ts("opportunity_scanner"),
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "duration_ms": self.duration_ms,
                "next_recommended_refresh_at": self.next_recommended_refresh_at,
            },
            "modules": [
                {
                    "module": m.module,
                    "status": m.status,
                    "refreshed_at": m.refreshed_at,
                    "duration_ms": m.duration_ms,
                    "error": m.error,
                }
                for m in self.modules
            ],
            "scanner_payload": self.scanner_payload,
        }

    def _module_ts(self, name: str) -> str | None:
        for m in self.modules:
            if m.module == name:
                return m.refreshed_at
        return None


class GlobalRefreshService:
    """Orchestrates lightweight Market Open Refresh — NO IBKR/option chains."""

    def __init__(
        self,
        *,
        market_intelligence_service: MarketIntelligenceService,
        market_regime_service: MarketRegimeService,
        opportunity_scanner_service: OpportunityScannerService,
    ) -> None:
        self._mi = market_intelligence_service
        self._mr = market_regime_service
        self._os = opportunity_scanner_service
        self._last_result: MarketOpenRefreshResult | None = None

    @property
    def last_result(self) -> MarketOpenRefreshResult | None:
        return self._last_result

    def market_open_refresh(self) -> MarketOpenRefreshResult:
        """Run sequential: MI → MR → OS. No option chains."""
        started = datetime.now(UTC)
        result = MarketOpenRefreshResult(
            status="ok",
            started_at=started.isoformat(),
        )

        result.modules.append(self._refresh_mi())
        result.modules.append(self._refresh_mr())
        scanner_mod, scanner_payload = self._refresh_os()
        result.modules.append(scanner_mod)
        result.scanner_payload = scanner_payload

        completed = datetime.now(UTC)
        result.completed_at = completed.isoformat()
        result.duration_ms = int((completed - started).total_seconds() * 1000)

        min_stale = min(
            settings.news_stale_minutes,
            settings.regime_stale_minutes,
            settings.scanner_stale_minutes,
        )
        result.next_recommended_refresh_at = (completed + timedelta(minutes=min_stale)).isoformat()

        errors = [m for m in result.modules if m.status == "error"]
        if len(errors) == len(result.modules):
            result.status = "failed"
        elif errors:
            result.status = "partial"

        self._last_result = result
        return result

    def _refresh_mi(self) -> ModuleRefreshResult:
        t0 = time.time()
        try:
            self._mi.refresh("standard")
            ts = datetime.now(UTC).isoformat()
            return ModuleRefreshResult(
                module="market_intelligence",
                status="ok",
                refreshed_at=ts,
                duration_ms=int((time.time() - t0) * 1000),
            )
        except Exception as exc:
            logger.exception("Market Intelligence refresh failed")
            return ModuleRefreshResult(
                module="market_intelligence",
                status="error",
                duration_ms=int((time.time() - t0) * 1000),
                error=str(exc)[:500],
            )

    def _refresh_mr(self) -> ModuleRefreshResult:
        t0 = time.time()
        try:
            self._mr.build_dashboard()
            ts = datetime.now(UTC).isoformat()
            return ModuleRefreshResult(
                module="market_regime",
                status="ok",
                refreshed_at=ts,
                duration_ms=int((time.time() - t0) * 1000),
            )
        except Exception as exc:
            logger.exception("Market Regime refresh failed")
            return ModuleRefreshResult(
                module="market_regime",
                status="error",
                duration_ms=int((time.time() - t0) * 1000),
                error=str(exc)[:500],
            )

    def _refresh_os(self) -> tuple[ModuleRefreshResult, dict[str, Any] | None]:
        t0 = time.time()
        try:
            payload = self._os.scan(refresh_news=False)
            ts = datetime.now(UTC).isoformat()
            return (
                ModuleRefreshResult(
                    module="opportunity_scanner",
                    status="ok",
                    refreshed_at=ts,
                    duration_ms=int((time.time() - t0) * 1000),
                ),
                payload,
            )
        except Exception as exc:
            logger.exception("Opportunity Scanner refresh failed")
            return (
                ModuleRefreshResult(
                    module="opportunity_scanner",
                    status="error",
                    duration_ms=int((time.time() - t0) * 1000),
                    error=str(exc)[:500],
                ),
                None,
            )
