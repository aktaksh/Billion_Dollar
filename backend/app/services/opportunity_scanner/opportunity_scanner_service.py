"""Opportunity Scanner orchestration."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.engine import Engine

from app.config import settings
from app.db import paper_trades, trade_decisions
from app.repositories.opportunity_repository import OpportunityRepository
from app.repositories.watchlist_repository import WatchlistRepository
from app.services.broker.broker_provider import get_broker_provider
from app.services.market_intelligence.news_signal_service import NewsSignalService
from app.services.market_regime.catalyst_calendar_service import CatalystCalendarService
from app.services.market_regime.data_adapters import MarketDataAdapters
from app.services.market_regime.market_regime_service import MarketRegimeService
from app.services.market_intelligence.market_intelligence_service import MarketIntelligenceService
from app.services.opportunity_scanner.opportunity_score_calculator import OpportunityScoreCalculator
from news_intelligence.news_repository import NewsRepository


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _age_minutes(ts: str | None) -> float | None:
    parsed = _parse_ts(ts)
    if not parsed:
        return None
    return max(0.0, (datetime.now(UTC) - parsed).total_seconds() / 60.0)


class OpportunityScannerService:
    def __init__(
        self,
        engine: Engine,
        *,
        analysis_dir_fn: Callable[[str], Any],
        market_regime_service: MarketRegimeService,
        market_intelligence_service: MarketIntelligenceService,
    ) -> None:
        self._engine = engine
        self._repo = OpportunityRepository(engine)
        self._watchlist = WatchlistRepository(engine)
        self._adapters = MarketDataAdapters(analysis_dir_fn)
        self._regime_svc = market_regime_service
        self._mi_svc = market_intelligence_service
        self._news_repo = NewsRepository(engine)
        self._news_signals = NewsSignalService(self._news_repo)
        self._catalysts = CatalystCalendarService()
        self._calculator = OpportunityScoreCalculator()

    def scan(self, *, refresh_news: bool = False) -> dict[str, Any]:
        if refresh_news:
            try:
                self._mi_svc.refresh("quick")
            except Exception:
                pass

        self._watchlist.seed_defaults_if_empty()
        watchlist = self._watchlist.list_all()
        enabled = [w for w in watchlist if w.get("enabled")]
        if not enabled:
            return self._empty_payload("No enabled watchlist symbols found.")

        market_regime = self._regime_svc.get_cached_or_build()
        benchmark = self._adapters.load_analyzer_snapshot("QQQ") or self._adapters.load_analyzer_snapshot("SPY")
        catalyst_events = self._catalysts.upcoming()
        paper_trade_rows = self._load_paper_trades()
        news_provider_error = self._news_provider_error()
        ibkr_available = self._ibkr_broker_available()
        recent_tde_symbols = self._recent_trade_decision_symbols()

        # Dependency validation
        upstream_warnings = self._validate_upstream(market_regime)

        rows: list[dict[str, Any]] = []
        for wl in sorted(enabled, key=lambda w: w.get("priority", 99)):
            sym = wl["symbol"]
            analysis = self._adapters.load_analyzer_snapshot(sym)
            news_signal = self._news_signals.signal_for_symbol(sym, since_days=7)
            scored = self._calculator.score_symbol(
                symbol=sym,
                watchlist_row=wl,
                analysis=analysis,
                news_signal=news_signal,
                market_regime=market_regime,
                benchmark_analysis=benchmark,
                paper_trades=paper_trade_rows,
                catalyst_events=catalyst_events,
                news_provider_error=news_provider_error,
                ibkr_available=ibkr_available,
                has_recent_trade_decision=sym.upper() in recent_tde_symbols,
            )
            scored["reason"] = scored.get("reason_json", {}).get("summary", "—")
            rj = scored["reason_json"]
            rj["sector"] = scored.get("sector")
            rj["company"] = scored.get("company")
            rj["priority"] = scored.get("priority")
            rj["catalyst_strength_score"] = scored.get("catalyst_strength_score")
            rj["news_quality_score"] = scored.get("news_quality_score")
            rj["trade_readiness"] = scored.get("trade_readiness")
            rj["top_risk"] = scored.get("top_risk")
            rows.append(scored)

        rows.sort(key=lambda r: (-r["market_opportunity_score"], r.get("priority", 99)))
        for i, row in enumerate(rows, start=1):
            row["rank"] = i

        ts = self._repo.save_batch(rows)
        self._repo.purge_older_than()
        return self._build_payload(rows, ts, len(enabled), news_provider_error, upstream_warnings)

    def get_latest(self) -> dict[str, Any]:
        rows = self._repo.list_latest()
        if not rows:
            scanned = self.scan()
            return scanned
        formatted = [self._format_db_row(r, rank=i + 1) for i, r in enumerate(rows)]
        ts = rows[0]["timestamp"] if rows else None
        return self._build_payload(formatted, ts, len(formatted), self._news_provider_error(), [])

    def get_symbol(self, symbol: str) -> dict[str, Any] | None:
        row = self._repo.get_symbol_latest(symbol.strip().upper())
        if not row:
            return None
        latest = self._repo.list_latest()
        rank = next((i + 1 for i, r in enumerate(latest) if r["symbol"] == row["symbol"]), None)
        return self._format_db_row(row, rank=rank)

    def export_json(self) -> str:
        payload = self.get_latest()
        return json.dumps(payload, indent=2, default=str)

    def _validate_upstream(self, market_regime: dict[str, Any] | None) -> list[str]:
        """Check if upstream data sources are stale and return warnings."""
        warnings: list[str] = []

        # Check regime freshness
        if market_regime:
            regime_ts = (market_regime.get("summary") or {}).get("timestamp")
            age = _age_minutes(regime_ts)
            if age is not None and age > settings.regime_stale_minutes:
                warnings.append(
                    f"Market Regime data is {int(age)}m old (threshold: {settings.regime_stale_minutes}m). "
                    "Consider running Market Open Refresh."
                )
        else:
            warnings.append("Market Regime unavailable. Run Market Open Refresh.")

        # Check news freshness
        with self._engine.connect() as conn:
            from app.db import news_fetch_log
            row = conn.execute(
                select(news_fetch_log.c.created_at)
                .order_by(news_fetch_log.c.created_at.desc())
                .limit(1)
            ).first()
        if row:
            news_age = _age_minutes(row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]))
            if news_age is not None and news_age > settings.news_stale_minutes:
                warnings.append(
                    f"News data is {int(news_age)}m old (threshold: {settings.news_stale_minutes}m). "
                    "Consider running Market Open Refresh."
                )
        else:
            warnings.append("No news data available. Run Market Open Refresh.")

        return warnings

    def _load_paper_trades(self) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = conn.execute(select(paper_trades)).mappings().all()
        return [dict(r) for r in rows]

    def _ibkr_broker_available(self) -> bool:
        """One live check per scan (not per-symbol) — Trade Readiness = Blocked when False.

        Best-effort: any failure to even construct/query the broker provider is treated
        as "unavailable" rather than raising, since this must never break a scan.
        """
        try:
            ok, _ = get_broker_provider().is_available()
            return bool(ok)
        except Exception:
            return False

    def _recent_trade_decision_symbols(self) -> set[str]:
        """Symbols with a Trade Decision Engine record within the technical staleness
        window — used as the "TDE exists" half of Trade Readiness = Ready."""
        cutoff = datetime.now(UTC) - timedelta(minutes=settings.technical_stale_minutes)
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    select(trade_decisions.c.symbol).where(trade_decisions.c.timestamp >= cutoff).distinct()
                ).all()
            return {r[0].upper() for r in rows if r[0]}
        except Exception:
            return set()

    def _news_provider_error(self) -> bool:
        with self._engine.connect() as conn:
            from app.db import news_fetch_log
            row = conn.execute(
                select(news_fetch_log.c.status)
                .order_by(news_fetch_log.c.created_at.desc())
                .limit(1)
            ).first()
        return bool(row and row[0] == "error")

    @staticmethod
    def _format_db_row(row: dict[str, Any], *, rank: int | None) -> dict[str, Any]:
        reason = row.get("reason_json") or {}
        if isinstance(reason, str):
            try:
                reason = json.loads(reason)
            except json.JSONDecodeError:
                reason = {"summary": reason}

        has_snapshot = reason.get("data_availability", {}).get("analyzer_snapshot", False)
        tech_confidence = "Not Evaluated"
        if has_snapshot:
            tech_confidence = "Stale"  # from DB we can't know freshness; conservative default

        return {
            "rank": rank,
            "symbol": row["symbol"],
            "company": reason.get("company"),
            "sector": reason.get("sector"),
            "priority": reason.get("priority"),
            "direction_candidate": row["direction_candidate"],
            "market_opportunity_score": row["opportunity_score"],
            "opportunity_score": row["opportunity_score"],
            "bull_score": row["bull_score"],
            "bear_score": row["bear_score"],
            "confidence_score": row["confidence_score"],
            "risk_score": row["risk_score"],
            "news_score": row["news_score"],
            "news_quality_score": reason.get("news_quality_score", row["news_score"]),
            "catalyst_strength_score": reason.get("catalyst_strength_score", 0.0),
            "technical_score": row["technical_score"],
            "technical_confidence": tech_confidence,
            "trade_readiness": reason.get("trade_readiness", "Needs Analyze Live"),
            "liquidity_score": row.get("liquidity_score", 0),
            "market_regime_score": row.get("market_regime_score"),
            "relative_strength_score": row.get("relative_strength_score"),
            "paper_feedback_score": row.get("paper_feedback_score"),
            "next_earnings": row.get("next_earnings"),
            "top_catalyst": row.get("top_catalyst"),
            "top_risk": reason.get("top_risk"),
            "market_context": row.get("market_context"),
            "data_quality": row.get("data_quality"),
            "reason": reason.get("summary") or "—",
            "reason_json": reason,
            "has_analyzer_snapshot": has_snapshot,
            "has_options_data": reason.get("data_availability", {}).get("options_data", False),
            "has_news_data": reason.get("data_availability", {}).get("news_data", False),
            "last_analyzed_at": None,
            "technical_hint": (
                "Click Analyze Live for full analysis."
                if tech_confidence == "Not Evaluated"
                else "Live analysis will refresh technicals and options."
            ),
        }

    def _build_payload(
        self,
        rows: list[dict[str, Any]],
        timestamp: datetime | None,
        symbols_scanned: int,
        news_provider_error: bool,
        upstream_warnings: list[str],
    ) -> dict[str, Any]:
        ts_iso = timestamp.isoformat() if timestamp else datetime.now(UTC).isoformat()
        bullish = [r for r in rows if r.get("direction_candidate") == "Bullish"]
        bearish = [r for r in rows if r.get("direction_candidate") == "Bearish"]
        best_bull = max(bullish, key=lambda r: r["market_opportunity_score"], default=None)
        best_bear = max(bearish, key=lambda r: r["market_opportunity_score"], default=None)
        highest_opp = max(rows, key=lambda r: r["market_opportunity_score"], default=None)
        highest_risk = max(rows, key=lambda r: r["risk_score"], default=None)

        qualities = [r.get("data_quality") for r in rows]
        if qualities and all(q == "good" for q in qualities):
            data_quality_label = "Good"
        elif any(q == "good" for q in qualities):
            data_quality_label = "Mixed"
        else:
            data_quality_label = "Partial"

        not_evaluated = sum(1 for r in rows if r.get("technical_confidence") == "Not Evaluated")
        stale_count = sum(1 for r in rows if r.get("technical_confidence") == "Stale")

        freshness_parts = []
        if not_evaluated:
            freshness_parts.append(f"{not_evaluated} not evaluated")
        if stale_count:
            freshness_parts.append(f"{stale_count} stale")
        fresh_count = len(rows) - not_evaluated - stale_count
        if fresh_count:
            freshness_parts.append(f"{fresh_count} fresh")
        data_freshness = "Technical: " + ", ".join(freshness_parts) if freshness_parts else "Current"

        return {
            "timestamp": ts_iso,
            "header": {
                "last_updated": ts_iso,
                "symbols_scanned": symbols_scanned,
                "data_freshness": data_freshness,
                "news_provider_error": news_provider_error,
                "upstream_warnings": upstream_warnings,
            },
            "summary": {
                "best_bullish": best_bull,
                "best_bearish": best_bear,
                "highest_opportunity": highest_opp,
                "highest_risk": highest_risk,
                "symbols_scanned": symbols_scanned,
                "data_quality": data_quality_label,
                "bullish_count": len(bullish),
                "bearish_count": len(bearish),
                "neutral_count": len(rows) - len(bullish) - len(bearish),
            },
            "results": rows,
            "disclaimer": (
                "Direction Candidate only — not a final trade recommendation. "
                "Use Analyze Live to open Options Spread Strategy; Trade Decision Engine produces final decisions."
            ),
        }

    @staticmethod
    def _empty_payload(message: str) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        return {
            "timestamp": now,
            "header": {"last_updated": now, "symbols_scanned": 0, "data_freshness": "—", "upstream_warnings": []},
            "summary": {
                "best_bullish": None,
                "best_bearish": None,
                "highest_opportunity": None,
                "highest_risk": None,
                "symbols_scanned": 0,
                "data_quality": "—",
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": 0,
            },
            "results": [],
            "empty_message": message,
            "disclaimer": "Direction Candidate only — not a final trade recommendation.",
        }
