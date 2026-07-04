"""Consolidated AI Report — aggregates all module state for LLM/agent ingestion."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.engine import Engine

from app.services.market_intelligence.market_intelligence_service import MarketIntelligenceService
from app.services.market_regime.data_adapters import MarketDataAdapters
from app.services.market_regime.market_regime_service import MarketRegimeService
from app.services.opportunity_scanner.opportunity_scanner_service import OpportunityScannerService
from app.services.paper_trade_service import PaperTradeService
from app.services.trade_decision.trade_decision_engine import TradeDecisionEngine
from app.services.ibkr.ibkr_sync_service import IBKRSyncService

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
JSON_FILENAME = "billion_dollar_ai_report_latest.json"
MD_FILENAME = "billion_dollar_ai_report_latest.md"


def _stale_minutes(ts_str: str | None) -> int | None:
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=UTC)
        return max(0, int((datetime.now(UTC) - dt).total_seconds() // 60))
    except (ValueError, TypeError):
        return None


def _freshness_status(stale_min: int | None) -> str:
    if stale_min is None:
        return "unavailable"
    if stale_min <= 30:
        return "fresh"
    if stale_min <= 1440:
        return "stale"
    return "very_stale"


class AiReportService:
    def __init__(
        self,
        engine: Engine,
        *,
        analysis_dir_fn: Callable[[str], Path],
        market_regime_service: MarketRegimeService,
        market_intelligence_service: MarketIntelligenceService,
        opportunity_scanner_service: OpportunityScannerService,
        paper_trade_service: PaperTradeService,
        trade_decision_engine: TradeDecisionEngine,
        ibkr_sync_service: IBKRSyncService,
    ) -> None:
        self._engine = engine
        self._adapters = MarketDataAdapters(analysis_dir_fn)
        self._regime = market_regime_service
        self._mi = market_intelligence_service
        self._scanner = opportunity_scanner_service
        self._paper = paper_trade_service
        self._tde = trade_decision_engine
        self._ibkr = ibkr_sync_service

    def generate(self, *, symbol: str | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        warnings: list[str] = []
        errors: list[str] = []

        qqq_snap = self._load_analyzer("QQQ", warnings)
        extra_symbol = (symbol or "").strip().upper() if symbol else None
        extra_snap = self._load_analyzer(extra_symbol, warnings) if extra_symbol and extra_symbol != "QQQ" else None

        regime = self._safe_call("market_regime", self._regime.get_cached_or_build, errors)
        mi_dash = self._safe_call("market_intelligence", self._mi.build_dashboard, errors)
        scanner = self._safe_call("opportunity_scanner", self._scanner.get_latest, errors)
        paper_summary = self._safe_call("paper_trading", self._paper.get_summary, errors)
        paper_analytics = self._safe_call("paper_trading_analytics", self._paper.get_analytics, errors)
        ibkr = self._safe_call("ibkr_status", self._ibkr.get_sync_status, errors)

        open_trades = []
        try:
            open_trades = self._paper.list_trades(status="OPEN")
        except Exception as exc:
            errors.append(f"paper_trades_open: {exc}")

        tde_qqq = self._evaluate_tde("QQQ", qqq_snap, regime, warnings)
        tde_extra = self._evaluate_tde(extra_symbol, extra_snap, regime, warnings) if extra_snap else None

        recent_decisions_qqq = self._safe_call("trade_decisions_qqq", lambda: self._tde.list_recent("QQQ", limit=5), errors)
        recent_decisions_extra = (
            self._safe_call("trade_decisions_extra", lambda: self._tde.list_recent(extra_symbol, limit=5), errors)
            if extra_symbol else None
        )

        module_freshness = self._build_freshness(qqq_snap, extra_snap, extra_symbol, regime, mi_dash, scanner)
        data_status = self._overall_status(module_freshness)
        conflicts = self._detect_conflicts(tde_qqq, scanner, regime, warnings)

        report: dict[str, Any] = {
            "report_meta": {
                "generated_at": now.isoformat(),
                "app": "Billion Dollar",
                "version": "1.0.0",
                "mode": "research_only",
                "data_status": data_status,
            },
            "module_freshness": module_freshness,
            "final_decision_context": {
                "single_authority": "Trade Decision Engine",
                "note": "Only TDE produces final strategy recommendations. All other modules provide inputs/context.",
                "current_decision_qqq": tde_qqq,
                "current_decision_extra": tde_extra,
                "recent_decisions_qqq": recent_decisions_qqq,
                "recent_decisions_extra": recent_decisions_extra,
                "conflicts_detected": conflicts,
                "blocking_conditions": self._blocking_conditions(qqq_snap, tde_qqq),
            },
            "qqq_spread_analyzer": self._format_analyzer("QQQ", qqq_snap),
            "options_spread_strategy": self._format_analyzer(extra_symbol or "—", extra_snap) if extra_symbol else "no_symbol_specified",
            "market_regime": self._format_regime(regime),
            "market_intelligence": self._format_mi(mi_dash),
            "opportunity_scanner": self._format_scanner(scanner),
            "paper_trading": {
                "summary": paper_summary or "data_unavailable",
                "analytics": paper_analytics or "data_unavailable",
                "open_positions": [self._compact_trade(t) for t in open_trades[:20]],
                "open_count": len(open_trades),
            },
            "ibkr_status": ibkr or "data_unavailable",
            "warnings": warnings,
            "errors": errors,
        }
        return report

    def write_files(self, report: dict[str, Any]) -> tuple[Path, Path]:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        json_path = REPORTS_DIR / JSON_FILENAME
        md_path = REPORTS_DIR / MD_FILENAME
        json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        md_path.write_text(self._render_markdown(report), encoding="utf-8")
        return json_path, md_path

    def _load_analyzer(self, symbol: str | None, warnings: list[str]) -> dict[str, Any] | None:
        if not symbol:
            return None
        snap = self._adapters.load_analyzer_snapshot(symbol)
        if not snap:
            warnings.append(f"Analyzer snapshot unavailable for {symbol}. Run analysis to generate.")
        return snap

    def _safe_call(self, label: str, fn, errors: list[str]) -> Any:
        try:
            return fn()
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            return None

    def _evaluate_tde(
        self, symbol: str | None, analysis: dict[str, Any] | None,
        regime: dict[str, Any] | None, warnings: list[str],
    ) -> dict[str, Any] | None:
        if not symbol or not analysis:
            return None
        try:
            summary = (regime or {}).get("summary", {})
            regime_label = summary.get("regime_name", "Sideways")
            strategy_filter = summary.get("preferred_strategy", "WAIT")
            scores = (regime or {}).get("score_breakdown", {})
            result = self._tde.evaluate_from_analysis(
                analysis,
                regime_label=regime_label,
                regime_scores=scores,
                strategy_filter=strategy_filter,
            )
            return result
        except Exception as exc:
            warnings.append(f"TDE evaluation failed for {symbol}: {exc}")
            return None

    def _build_freshness(
        self,
        qqq_snap: dict | None,
        extra_snap: dict | None,
        extra_symbol: str | None,
        regime: dict | None,
        mi_dash: dict | None,
        scanner: dict | None,
    ) -> dict[str, Any]:
        qqq_ts = (qqq_snap or {}).get("timestamp")
        extra_ts = (extra_snap or {}).get("timestamp") if extra_snap else None
        regime_ts = (regime or {}).get("summary", {}).get("timestamp") or ((regime or {}).get("instruments", [{}])[0].get("timestamp") if regime else None)
        mi_ts = (mi_dash or {}).get("timestamp")
        scanner_ts = (scanner or {}).get("timestamp")

        def entry(ts):
            sm = _stale_minutes(ts)
            return {"last_updated": ts, "stale_minutes": sm, "status": _freshness_status(sm)}

        freshness = {
            "qqq_spread_analyzer": entry(qqq_ts),
            "market_regime": entry(regime_ts),
            "market_intelligence": entry(mi_ts),
            "opportunity_scanner": entry(scanner_ts),
            "paper_trading": {"status": "available"},
        }
        if extra_symbol:
            freshness["options_spread_strategy"] = {"symbol": extra_symbol, **entry(extra_ts)}
        return freshness

    @staticmethod
    def _overall_status(freshness: dict[str, Any]) -> str:
        statuses = [v.get("status") for v in freshness.values() if isinstance(v, dict)]
        if all(s == "fresh" for s in statuses if s):
            return "fresh"
        if any(s == "unavailable" for s in statuses):
            return "partial"
        if any(s in ("stale", "very_stale") for s in statuses):
            return "stale"
        return "fresh"

    def _detect_conflicts(
        self, tde: dict | None, scanner: dict | None, regime: dict | None, warnings: list[str],
    ) -> list[str]:
        conflicts: list[str] = []
        if not tde or not scanner:
            return conflicts
        tde_decision = (tde.get("decision") or tde.get("final_decision") or "WAIT").upper()
        scanner_results = (scanner or {}).get("results") or []
        qqq_scan = next((r for r in scanner_results if r.get("symbol") == "QQQ"), None)
        if qqq_scan:
            direction = (qqq_scan.get("direction_candidate") or "Neutral").lower()
            if "bull" in direction and "BEAR" in tde_decision:
                conflicts.append("Scanner says QQQ Bullish but TDE recommends Bear strategy")
            elif "bear" in direction and "BULL" in tde_decision:
                conflicts.append("Scanner says QQQ Bearish but TDE recommends Bull strategy")

        regime_pref = ((regime or {}).get("summary", {}).get("preferred_strategy") or "").upper()
        if "WAIT" in regime_pref and tde_decision != "WAIT":
            conflicts.append(f"Market Regime prefers WAIT but TDE says {tde_decision}")

        if conflicts:
            for c in conflicts:
                warnings.append(f"Conflict: {c}")
        return conflicts

    @staticmethod
    def _blocking_conditions(analysis: dict | None, tde: dict | None) -> list[str]:
        blockers: list[str] = []
        if not analysis:
            blockers.append("No analyzer snapshot — cannot evaluate spreads")
        elif not (analysis.get("spread_candidates") or []):
            blockers.append("No spread candidates passed filters")
        if tde and (tde.get("decision") or tde.get("final_decision") or "").upper() == "WAIT":
            blockers.append("TDE recommends WAIT — no actionable trade")
        return blockers

    def _format_analyzer(self, symbol: str, snap: dict | None) -> dict[str, Any]:
        if not snap:
            return {"data_unavailable": True, "reason": f"No analyzer snapshot for {symbol}. Run analysis."}
        candidates = snap.get("spread_candidates") or []
        accepted = [c for c in candidates if c.get("status") == "Accepted"]
        expiry_search = snap.get("expiry_search") or {}
        return {
            "symbol": snap.get("symbol", symbol),
            "timestamp": snap.get("timestamp"),
            "stale_minutes": _stale_minutes(snap.get("timestamp")),
            "underlying_price": snap.get("underlying_price"),
            "bias": snap.get("bias"),
            "confidence": snap.get("confidence"),
            "suggested_action": snap.get("suggested_action"),
            "bullish_score": snap.get("bullish_score"),
            "bearish_score": snap.get("bearish_score"),
            "reason_summary": snap.get("reason_summary"),
            "daily_indicators_summary": self._compact_indicators(snap.get("daily_indicators")),
            "support_count": len(snap.get("support_levels") or []),
            "resistance_count": len(snap.get("resistance_levels") or []),
            "spread_candidates_total": len(candidates),
            "spread_candidates_accepted": len(accepted),
            "best_spread": accepted[0] if accepted else None,
            "risk_notes": snap.get("risk_notes") or [],
            "liquid_options_count": len(snap.get("liquid_options") or []),
            "expiry_search": {
                "buckets_scanned": expiry_search.get("buckets_scanned", []),
                "expiries_scanned": expiry_search.get("expiries_scanned", 0),
                "best_expiry": expiry_search.get("best_expiry"),
                "best_bucket": expiry_search.get("best_bucket"),
                "valid_spreads_count": expiry_search.get("valid_spreads_count", 0),
                "force_wait": expiry_search.get("force_wait", False),
                "wait_reason": expiry_search.get("wait_reason"),
                "expiry_rankings": expiry_search.get("expiry_rankings", [])[:5],
                "rejected_expiries": expiry_search.get("rejected_expiries", [])[:5],
                "top_spreads": expiry_search.get("top_spreads", [])[:3],
                "no_candidate_reasons": expiry_search.get("no_candidate_reasons", []),
            },
        }

    @staticmethod
    def _compact_indicators(indicators: dict | None) -> dict[str, Any] | None:
        if not indicators:
            return None
        keys = ("close", "ema20", "ema50", "sma200", "rsi14", "macd_line", "macd_signal", "atr14", "bb_upper", "bb_lower")
        return {k: indicators.get(k) for k in keys if indicators.get(k) is not None}

    @staticmethod
    def _format_regime(regime: dict | None) -> dict[str, Any]:
        if not regime:
            return {"data_unavailable": True, "reason": "Market Regime service returned no data"}
        summary = regime.get("summary", {})
        return {
            "regime_name": summary.get("regime_name"),
            "regime_score": summary.get("regime_score"),
            "confidence": summary.get("confidence"),
            "risk_level": summary.get("risk_level"),
            "preferred_strategy": summary.get("preferred_strategy"),
            "trend_score": regime.get("score_breakdown", {}).get("trend_score"),
            "momentum_score": regime.get("score_breakdown", {}).get("momentum_score"),
            "volatility_score": regime.get("score_breakdown", {}).get("volatility_score"),
            "instruments_available": len(regime.get("instruments", [])),
        }

    @staticmethod
    def _format_mi(mi: dict | None) -> dict[str, Any]:
        if not mi:
            return {"data_unavailable": True, "reason": "Market Intelligence unavailable"}
        summary = mi.get("summary", {})
        return {
            "timestamp": mi.get("timestamp"),
            "overall_sentiment": summary.get("overall_sentiment"),
            "news_score": summary.get("news_score_0_to_100"),
            "critical_events_count": summary.get("critical_events_count", 0),
            "upcoming_earnings_count": summary.get("upcoming_earnings_count", 0),
            "watchlist_count": len(mi.get("watchlist") or []),
            "api_status": mi.get("header", {}).get("api_status"),
            "comments": mi.get("comments", []),
        }

    @staticmethod
    def _format_scanner(scanner: dict | None) -> dict[str, Any]:
        if not scanner:
            return {"data_unavailable": True, "reason": "Opportunity Scanner has no results"}
        results = scanner.get("results") or []
        return {
            "timestamp": scanner.get("timestamp"),
            "symbols_scanned": scanner.get("header", {}).get("symbols_scanned", 0),
            "data_freshness": scanner.get("header", {}).get("data_freshness"),
            "bullish_count": scanner.get("summary", {}).get("bullish_count", 0),
            "bearish_count": scanner.get("summary", {}).get("bearish_count", 0),
            "neutral_count": scanner.get("summary", {}).get("neutral_count", 0),
            "top_5_opportunities": [
                {
                    "rank": r.get("rank"),
                    "symbol": r.get("symbol"),
                    "direction_candidate": r.get("direction_candidate"),
                    "opportunity_score": r.get("opportunity_score"),
                    "bull_score": r.get("bull_score"),
                    "bear_score": r.get("bear_score"),
                    "risk_score": r.get("risk_score"),
                    "reason": r.get("reason"),
                }
                for r in results[:5]
            ],
        }

    @staticmethod
    def _compact_trade(t: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": t.get("id"),
            "symbol": t.get("symbol"),
            "strategy_type": t.get("strategy_type"),
            "expiry_date": t.get("expiry_date"),
            "entry_debit": t.get("entry_debit"),
            "max_profit": t.get("max_profit"),
            "max_loss": t.get("max_loss"),
            "unrealized_pnl": t.get("unrealized_pnl"),
            "status": t.get("status"),
        }

    def _render_markdown(self, report: dict[str, Any]) -> str:
        meta = report.get("report_meta", {})
        lines = [
            "# Billion Dollar — AI Report",
            "",
            f"**Generated:** {meta.get('generated_at', '—')}",
            f"**Mode:** {meta.get('mode', '—')}",
            f"**Data Status:** {meta.get('data_status', '—')}",
            "",
            "---",
            "",
            "## Module Freshness",
            "",
            "| Module | Status | Stale (min) |",
            "|--------|--------|-------------|",
        ]
        for mod, info in report.get("module_freshness", {}).items():
            if isinstance(info, dict):
                lines.append(f"| {mod} | {info.get('status', '—')} | {info.get('stale_minutes', '—')} |")
        lines += ["", "---", ""]

        ctx = report.get("final_decision_context", {})
        tde_qqq = ctx.get("current_decision_qqq") or {}
        lines += [
            "## Trade Decision (Final Authority)",
            "",
            f"**Single Authority:** {ctx.get('single_authority', 'Trade Decision Engine')}",
            "",
            f"- QQQ Decision: **{tde_qqq.get('decision') or tde_qqq.get('final_decision', 'N/A')}**",
            f"- Trade Score: {tde_qqq.get('trade_score', '—')}",
            f"- Confidence: {tde_qqq.get('confidence', '—')}",
            f"- Risk Level: {tde_qqq.get('risk_level', '—')}",
            "",
        ]
        conflicts = ctx.get("conflicts_detected") or []
        if conflicts:
            lines += ["### Conflicts", ""]
            for c in conflicts:
                lines.append(f"- {c}")
            lines.append("")
        blockers = ctx.get("blocking_conditions") or []
        if blockers:
            lines += ["### Blocking Conditions", ""]
            for b in blockers:
                lines.append(f"- {b}")
            lines.append("")

        lines += ["---", ""]

        qqq = report.get("qqq_spread_analyzer", {})
        if not qqq.get("data_unavailable"):
            lines += [
                "## QQQ Spread Analyzer",
                "",
                f"- Price: {qqq.get('underlying_price', '—')}",
                f"- Bias: {qqq.get('bias', '—')} ({qqq.get('confidence', '—')})",
                f"- Bull/Bear: {qqq.get('bullish_score', '—')}/{qqq.get('bearish_score', '—')}",
                f"- Accepted Spreads: {qqq.get('spread_candidates_accepted', 0)}/{qqq.get('spread_candidates_total', 0)}",
                f"- Stale: {qqq.get('stale_minutes', '—')} min",
                "",
            ]
        else:
            lines += ["## QQQ Spread Analyzer", "", f"_{qqq.get('reason', 'unavailable')}_", ""]

        regime = report.get("market_regime", {})
        if not regime.get("data_unavailable"):
            lines += [
                "## Market Regime",
                "",
                f"- Regime: {regime.get('regime_name', '—')}",
                f"- Score: {regime.get('regime_score', '—')}",
                f"- Risk Level: {regime.get('risk_level', '—')}",
                f"- Preferred Strategy: {regime.get('preferred_strategy', '—')}",
                "",
            ]

        mi = report.get("market_intelligence", {})
        if not mi.get("data_unavailable"):
            lines += [
                "## Market Intelligence",
                "",
                f"- Sentiment: {mi.get('overall_sentiment', '—')}",
                f"- News Score: {mi.get('news_score', '—')}",
                f"- Critical Events: {mi.get('critical_events_count', 0)}",
                f"- Watchlist Symbols: {mi.get('watchlist_count', 0)}",
                "",
            ]

        scanner_data = report.get("opportunity_scanner", {})
        if not scanner_data.get("data_unavailable"):
            lines += [
                "## Opportunity Scanner",
                "",
                f"- Scanned: {scanner_data.get('symbols_scanned', 0)} symbols",
                f"- Bullish: {scanner_data.get('bullish_count', 0)} | Bearish: {scanner_data.get('bearish_count', 0)} | Neutral: {scanner_data.get('neutral_count', 0)}",
                "",
                "### Top Opportunities",
                "",
                "| Rank | Symbol | Direction | Score |",
                "|------|--------|-----------|-------|",
            ]
            for opp in scanner_data.get("top_5_opportunities", []):
                lines.append(f"| {opp.get('rank', '—')} | {opp.get('symbol', '—')} | {opp.get('direction_candidate', '—')} | {opp.get('opportunity_score', '—')} |")
            lines.append("")

        pt = report.get("paper_trading", {})
        pt_sum = pt.get("summary") if isinstance(pt.get("summary"), dict) else {}
        lines += [
            "## Paper Trading",
            "",
            f"- Open: {pt_sum.get('open_count', pt.get('open_count', '—'))}",
            f"- Win Rate: {pt_sum.get('win_rate', '—')}%",
            f"- Total PnL: {pt_sum.get('total_realized_pnl', '—')}",
            "",
        ]

        if report.get("warnings"):
            lines += ["---", "", "## Warnings", ""]
            for w in report["warnings"]:
                lines.append(f"- {w}")
            lines.append("")
        if report.get("errors"):
            lines += ["---", "", "## Errors", ""]
            for e in report["errors"]:
                lines.append(f"- {e}")
            lines.append("")

        lines += ["---", "", "*Generated by Billion Dollar AI Report Service*", ""]
        return "\n".join(lines)
