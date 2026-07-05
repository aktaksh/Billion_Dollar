"""Market Intelligence Center orchestration."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import desc, func, select
from sqlalchemy.engine import Engine

from app.db import news_items
from app.repositories.watchlist_repository import WatchlistRepository
from app.services.market_intelligence.api_budget_manager import ApiBudgetManager
from app.services.market_intelligence.news_event_cluster import NewsEventCluster
from app.services.market_intelligence.news_query_planner import NewsQueryPlanner
from app.services.market_intelligence.news_signal_service import NewsSignalService
from app.services.market_intelligence.watchlist_service import WatchlistService
from app.services.market_regime.catalyst_calendar_service import CatalystCalendarService
from app.services.market_regime.market_regime_service import MarketRegimeService
from app.services.news_intelligence_api_service import (
    _count_by_importance,
    _importance,
    _item_to_event,
    _label_display,
    _provider_status,
    _score_0_to_100,
)
from news_intelligence.news_config import ETF_SYMBOLS, load_config
from news_intelligence.news_models import FetchLog
from news_intelligence.news_orchestrator import get_news_signal, run_news_pipeline
from news_intelligence.news_repository import NewsRepository, get_repository

SEC_FORMS = frozenset({"8-K", "10-Q", "10-K", "4", "S-1", "S-3"})


class MarketIntelligenceService:
    def __init__(
        self,
        engine: Engine,
        *,
        market_regime_service: MarketRegimeService | None = None,
        repo_factory: Callable[[], NewsRepository] | None = None,
        ibkr_news_client: Any | None = None,
    ) -> None:
        self.engine = engine
        self._mr = market_regime_service
        self._repo_factory = repo_factory or get_repository
        self._planner = NewsQueryPlanner()
        self._budget = ApiBudgetManager(engine)
        self._cluster = NewsEventCluster()
        self._catalysts = CatalystCalendarService()
        self._ibkr_news = ibkr_news_client
        self._last_refresh_at: str | None = None
        self._last_plan: dict[str, Any] | None = None
        self._last_ibkr_status: dict[str, Any] | None = None

    def _repo(self) -> NewsRepository:
        return self._repo_factory()

    def _watchlist(self) -> WatchlistService:
        return WatchlistService(self.engine, self._repo())

    def _signals(self) -> NewsSignalService:
        return NewsSignalService(self._repo())

    def _recent_items(self, since_days: int = 7) -> list:
        return self._repo().find_recent_items(datetime.now(UTC) - timedelta(days=since_days))

    def _ibkr_provider_status(self) -> dict[str, Any]:
        """Non-blocking status for dashboard reads — never opens a TWS connection."""
        if self._ibkr_news is None:
            return {"available": False, "message": "IBKR News not configured"}
        try:
            providers = list(getattr(self._ibkr_news, "_available_providers", []) or [])
            connected = bool(getattr(self._ibkr_news, "_connected", False))
            cache = getattr(self._ibkr_news, "cache_stats", {}) or {}
            last_fetch = self._last_ibkr_status.get("last_fetch") if self._last_ibkr_status else None
            errors = list(self._last_ibkr_status.get("errors", [])) if self._last_ibkr_status else []

            if self._last_ibkr_status:
                message = f"Last IBKR news fetch: {last_fetch or '—'}"
                if errors:
                    message = f"{message} ({errors[0]})"
            elif connected:
                message = f"IBKR News session active on {getattr(self._ibkr_news, '_host', 'TWS')}"
            else:
                message = "IBKR News idle — run refresh to fetch headlines"

            return {
                "available": connected or (bool(last_fetch) and not errors),
                "message": message,
                "providers_detected": providers,
                "cache_status": cache,
                "last_fetch": last_fetch,
                "errors": errors,
            }
        except Exception as exc:
            return {"available": False, "message": f"IBKR status check failed: {exc}"}

    def _regime_context(self) -> dict[str, Any]:
        if not self._mr:
            return {
                "available": False,
                "message": "Market Regime service unavailable.",
            }
        try:
            dash = self._mr.get_cached_dashboard()
            if not dash:
                return {
                    "available": False,
                    "message": "Regime data not loaded yet — open Market Regime or run refresh.",
                }
            summary = dash.get("summary") or {}
            vol = dash.get("volatility") or {}
            catalysts = dash.get("catalysts") or []
            next_cat = catalysts[0] if catalysts else None
            return {
                "available": True,
                "current_regime": summary.get("regime_name"),
                "regime_score": summary.get("regime_score"),
                "risk_level": summary.get("risk_level"),
                "preferred_strategy": summary.get("preferred_strategy"),
                "next_major_catalyst": next_cat.get("event") if next_cat else None,
                "next_catalyst_countdown_days": next_cat.get("countdown_days") if next_cat else None,
                "volatility_regime": vol.get("volatility_regime"),
            }
        except Exception as exc:
            return {"available": False, "message": str(exc)}

    def _critical_events(self, items: list, *, min_importance: str = "High") -> list[dict[str, Any]]:
        allowed = {"Critical", "High"} if min_importance == "High" else {min_importance}
        filtered = [i for i in items if _importance(i) in allowed]
        filtered.sort(key=lambda x: abs(x.impact_score), reverse=True)
        return self._cluster.attach_related(filtered[:50])

    def _sec_filings(self, items: list) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in items:
            if item.provider != "SEC_EDGAR":
                continue
            form = (item.raw_json or {}).get("form_type", "")
            if form and form not in SEC_FORMS:
                continue
            out.append({
                "symbol": item.symbol,
                "form": form or "—",
                "filed_date": item.published_at.isoformat() if item.published_at else None,
                "description": item.summary or item.headline,
                "importance": _importance(item),
                "link": item.url,
                "impact_score": round(item.impact_score, 4),
            })
        return out[:50]

    def _catalyst_calendar(self, items: list) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for ev in self._catalysts.upcoming():
            sym = "MARKET"
            name = ev.get("event", "")
            for token in ("NVDA", "AAPL", "QQQ", "SPY"):
                if token in name.upper():
                    sym = token
                    break
            rows.append({
                "event": ev.get("event"),
                "symbol": sym,
                "date": ev.get("date"),
                "time": ev.get("time"),
                "expected_impact": ev.get("expected_impact"),
                "risk_level": ev.get("risk_level"),
                "countdown_days": ev.get("countdown_days"),
                "source": "CatalystCalendarService",
            })
        for item in items:
            if item.event_type != "earnings":
                continue
            rows.append({
                "event": "Earnings headline",
                "symbol": item.symbol,
                "date": item.published_at.date().isoformat() if item.published_at else None,
                "time": "—",
                "expected_impact": "High",
                "risk_level": "Medium",
                "countdown_days": None,
                "source": item.source or item.provider,
            })
        return rows[:40]

    def _sentiment_analytics(self, since_days: int = 7) -> dict[str, Any]:
        items = self._recent_items(since_days)
        bull = bear = neutral = 0
        by_symbol: dict[str, list[float]] = {}
        by_day: dict[str, dict[str, int]] = {}

        for item in items:
            lab = (item.sentiment_label or "neutral").lower()
            if lab == "bullish":
                bull += 1
            elif lab == "bearish":
                bear += 1
            else:
                neutral += 1
            sym = item.symbol if item.symbol != "MARKET" else "MARKET"
            by_symbol.setdefault(sym, []).append(item.sentiment_score)
            day = (item.published_at or item.created_at).strftime("%Y-%m-%d") if (item.published_at or item.created_at) else "unknown"
            by_day.setdefault(day, {"bullish": 0, "bearish": 0, "neutral": 0})
            by_day[day][lab if lab in ("bullish", "bearish") else "neutral"] += 1

        def avg_score(scores: list[float]) -> float:
            return round(sum(scores) / len(scores), 4) if scores else 0.0

        symbol_avgs = [(s, avg_score(v)) for s, v in by_symbol.items() if s != "MARKET"]
        most_positive = sorted(symbol_avgs, key=lambda x: x[1], reverse=True)[:5]
        most_negative = sorted(symbol_avgs, key=lambda x: x[1])[:5]

        trend = [
            {"date": d, **counts}
            for d, counts in sorted(by_day.items())
        ][-14:]

        return {
            "split": {"bullish": bull, "bearish": bear, "neutral": neutral},
            "trend": trend,
            "most_positive": [{"symbol": s, "avg_sentiment": sc} for s, sc in most_positive],
            "most_negative": [{"symbol": s, "avg_sentiment": sc} for s, sc in most_negative],
        }

    def _summary(self, items: list) -> dict[str, Any]:
        critical, high = _count_by_importance(items)
        earnings_count = sum(1 for i in items if i.event_type == "earnings")
        try:
            cfg = load_config(require_finnhub=False, require_sec=False)
            has_finnhub = bool(cfg.finnhub_api_key)
            errors: list[str] = []
        except ValueError:
            has_finnhub = False
            errors = ["API keys not configured"]

        sig = get_news_signal("QQQ", since_days=7, repo=self._repo())
        label = _label_display(sig.news_sentiment_label)
        score = _score_0_to_100(sig.news_sentiment_score, sig.news_sentiment_label)
        api_status = _provider_status(errors, has_finnhub)

        return {
            "overall_sentiment": label,
            "news_score_0_to_100": score,
            "critical_events_count": critical,
            "high_impact_events_count": high,
            "upcoming_earnings_count": earnings_count,
            "api_health": api_status,
            "bullish_count": sig.bullish_count,
            "bearish_count": sig.bearish_count,
            "neutral_count": sig.neutral_count,
        }

    def _header(self) -> dict[str, Any]:
        return {
            "last_updated": self._last_refresh_at,
            "api_status": self._summary(self._recent_items()).get("api_health", "Unknown"),
        }

    def _news_signal_output(self, symbols: list[str]) -> dict[str, Any]:
        signals = self._signals().signals_for_watchlist(symbols)
        primary = signals[0] if signals else self._signals().signal_for_symbol("QQQ")
        return {
            "primary": primary,
            "watchlist_signals": signals,
            "consumers": [
                "Trade Decision Engine",
                "Market Regime",
                "QQQ Spread Analyzer",
                "Paper Trading Lab",
            ],
        }

    def build_dashboard(self) -> dict[str, Any]:
        wl = self._watchlist()
        wl.ensure_seeded()
        items = self._recent_items(7)
        enabled = wl.enabled_symbols()
        plan = self._last_plan or self._planner.plan("standard", enabled).__dict__

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "header": self._header(),
            "summary": self._summary(items),
            "regime_context": self._regime_context(),
            "watchlist": wl.list_with_signals(),
            "critical_events": self._critical_events(items),
            "catalyst_calendar": self._catalyst_calendar(items),
            "sec_filings": self._sec_filings(items),
            "sentiment_analytics": self._sentiment_analytics(),
            "api_budget": self._budget.snapshot(
                planned=plan.get("planned_calls", 0),
                skipped=plan.get("skipped_calls", 0),
                skip_reasons=plan.get("skip_reasons", []),
            ),
            "ibkr_news_status": self._ibkr_provider_status(),
            "activity_log": self._budget.activity_log(),
            "news_signal_output": self._news_signal_output(enabled),
            "comments": self._empty_comments(items),
        }

    def _empty_comments(self, items: list) -> list[str]:
        comments: list[str] = []
        if not items:
            comments.append("No news items in database. Run a refresh to fetch headlines.")
        if not any(_importance(i) in ("Critical", "High") for i in items):
            comments.append("No new high-impact news found.")
        return comments

    def refresh(self, mode: str = "standard") -> dict[str, Any]:
        wl = self._watchlist()
        enabled = wl.enabled_symbols()
        plan = self._planner.plan(mode, enabled)
        self._last_plan = {
            "planned_calls": plan.planned_calls,
            "skipped_calls": plan.skipped_calls,
            "skip_reasons": plan.skip_reasons,
            "mode": plan.mode,
            "symbols": plan.symbols,
        }

        started = datetime.now(UTC)
        provider_errors: list[str] = []

        from app.config import settings as app_settings
        max_ibkr = app_settings.ibkr_news_max_symbols_refresh

        try:
            summary = run_news_pipeline(
                symbols=plan.symbols,
                from_date=plan.from_date,
                to_date=plan.to_date,
                repo=self._repo(),
                ibkr_news_client=self._ibkr_news if app_settings.ibkr_news_enabled else None,
                max_ibkr_symbols=max_ibkr,
            )
            provider_errors = summary.provider_errors
        except ValueError as exc:
            provider_errors.append(str(exc))
            summary = None

        completed = datetime.now(UTC)
        self._last_refresh_at = completed.isoformat()

        # Track IBKR status for dashboard
        ibkr_errors = [e for e in provider_errors if e.startswith("IBKR")]
        self._last_ibkr_status = {
            "last_fetch": completed.isoformat(),
            "errors": ibkr_errors,
        }

        repo = self._repo()
        repo.insert_fetch_log(FetchLog(
            provider="PIPELINE",
            status="ok" if not provider_errors else "partial",
            request_type=f"market_intelligence_{mode}",
            symbols_requested=plan.symbols,
            items_fetched=summary.total_fetched if summary else 0,
            items_saved=summary.total_saved if summary else 0,
            duplicates_removed=summary.duplicates_removed if summary else 0,
            error_message="; ".join(provider_errors) if provider_errors else None,
            refresh_mode=mode,
        ))

        dash = self.build_dashboard()
        dash["refresh_result"] = {
            "status": "ok" if summary and not provider_errors else ("partial" if summary else "error"),
            "refresh_mode": mode,
            "started_at": started.isoformat(),
            "completed_at": completed.isoformat(),
            "planned_calls": plan.planned_calls,
            "executed_calls": max(0, plan.planned_calls - plan.skipped_calls - len(provider_errors)),
            "skipped_calls": plan.skipped_calls,
            "total_fetched": summary.total_fetched if summary else 0,
            "total_saved": summary.total_saved if summary else 0,
            "duplicates_removed": summary.duplicates_removed if summary else 0,
            "provider_errors": provider_errors,
            "comments": plan.skip_reasons + (["Fetched articles existed already and were removed as duplicates."] if summary and summary.total_saved == 0 and summary.duplicates_removed else []),
        }
        return dash

    def export_json(self) -> str:
        return json.dumps(self.build_dashboard(), indent=2, default=str)

    def quick_refresh_for_symbol(self, symbol: str = "QQQ") -> dict[str, Any]:
        """Backward-compatible shape for QQQ embed card."""
        dash = self.refresh("quick")
        rr = dash.get("refresh_result", {})
        sig = dash.get("news_signal_output", {}).get("primary", {})
        items = self._recent_items(1)
        critical, high = _count_by_importance(items)

        return {
            "status": rr.get("status", "ok"),
            "refreshMode": "quick",
            "startedAt": rr.get("started_at"),
            "completedAt": rr.get("completed_at"),
            "plannedCalls": rr.get("planned_calls", 0),
            "executedCalls": rr.get("executed_calls", 0),
            "skippedCalls": rr.get("skipped_calls", 0),
            "totalFetched": rr.get("total_fetched", 0),
            "totalSaved": rr.get("total_saved", 0),
            "duplicatesRemoved": rr.get("duplicates_removed", 0),
            "lowRelevanceIgnored": 0,
            "eventsCreated": rr.get("total_saved", 0),
            "bullishCount": dash.get("summary", {}).get("bullish_count", 0),
            "bearishCount": dash.get("summary", {}).get("bearish_count", 0),
            "neutralCount": dash.get("summary", {}).get("neutral_count", 0),
            "criticalEventCount": critical,
            "highEventCount": high,
            "topEvents": [_item_to_event(i) for i in items[:15]],
            "providerErrors": rr.get("provider_errors", []),
            "comments": rr.get("comments", []) + dash.get("comments", []),
            "newsSignal": {
                "symbol": symbol,
                "label": sig.get("label", "Unavailable"),
                "news_score_0_to_100": sig.get("news_score_0_to_100", 0),
                "sentiment_score": sig.get("sentiment_score", 0),
                "impact_score": sig.get("impact_score", 0),
                "confidence": sig.get("confidence", "Low"),
                "top_catalyst": sig.get("top_catalyst"),
                "last_updated": sig.get("last_updated"),
                "data_freshness_minutes": sig.get("data_freshness_minutes"),
                "provider_status": dash.get("summary", {}).get("api_health", "Error"),
                "bullish_count": sig.get("bullish_count", 0),
                "bearish_count": sig.get("bearish_count", 0),
                "neutral_count": sig.get("neutral_count", 0),
            },
        }

    def list_ticker_signals(self) -> list[dict[str, Any]]:
        """All persisted ticker_news_signals rows (Part 2/11) — ticker-level
        intelligence for the deferred UI redesign to consume directly."""
        from app.repositories.news_events_repository import NewsEventsRepository

        rows = NewsEventsRepository(self.engine).list_ticker_signals()
        out: list[dict[str, Any]] = []
        for row in rows:
            last_updated = row.get("last_updated")
            out.append({
                "symbol": row["symbol"],
                "news_bias": row.get("news_bias", "Neutral"),
                "news_quality_score": row.get("news_quality_score", 0.0),
                "catalyst_strength_score": row.get("catalyst_strength_score", 0.0),
                "net_impact_score": row.get("net_impact_score", 0.0),
                "bullish_count": row.get("bullish_count", 0),
                "bearish_count": row.get("bearish_count", 0),
                "neutral_count": row.get("neutral_count", 0),
                "top_catalyst": row.get("top_catalyst"),
                "top_risk": row.get("top_risk"),
                "llm_summary": row.get("llm_summary"),
                "confidence": row.get("confidence", "Low"),
                "last_updated": last_updated.isoformat() if hasattr(last_updated, "isoformat") else last_updated,
            })
        return out

    def get_latest_signal(self, symbol: str) -> dict[str, Any]:
        sig = self._signals().signal_for_symbol(symbol)
        items = self._recent_items(7)
        critical, high = _count_by_importance(items)
        return {
            "status": "ok",
            "refreshMode": "cached",
            "bullishCount": sig.get("bullish_count", 0),
            "bearishCount": sig.get("bearish_count", 0),
            "neutralCount": sig.get("neutral_count", 0),
            "criticalEventCount": critical,
            "highEventCount": high,
            "topEvents": self._critical_events(items)[:10],
            "providerErrors": [],
            "comments": self._empty_comments(items),
            "newsSignal": {
                **sig,
                "provider_status": self._summary(items).get("api_health", "Unknown"),
            },
        }
