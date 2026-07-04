"""Opportunity scoring for watchlist symbols — direction candidates only, not final trade decisions.

Refactored: Technical snapshots are NOT used in Market Opportunity Score calculation.
Score is split into:
  - market_opportunity_score (0-100): news, regime, relative-strength, sector, catalysts, paper
  - technical_confidence: "Fresh" | "Stale" | "Not Evaluated"
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import settings


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, round(v, 1)))


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _snapshot_age_minutes(analysis: dict[str, Any] | None) -> float | None:
    if not analysis:
        return None
    ts = _parse_ts(analysis.get("timestamp"))
    if not ts:
        return None
    return max(0.0, (datetime.now(UTC) - ts).total_seconds() / 60.0)


def _technical_confidence(analysis: dict[str, Any] | None) -> str:
    if not analysis:
        return "Not Evaluated"
    age = _snapshot_age_minutes(analysis)
    if age is None:
        return "Not Evaluated"
    if age <= settings.technical_stale_minutes:
        return "Fresh"
    return "Stale"


class OpportunityScoreCalculator:
    """Compute direction candidates and market opportunity scores per symbol.

    Market Opportunity Score uses ONLY:
      - News Intelligence (25%)
      - Market Regime (20%)
      - Relative Strength (20%)
      - Sector Strength (15%)
      - Catalyst/Earnings proximity (10%)
      - Paper Trading feedback (10%)

    Technical analysis is reported separately as Technical Confidence.
    """

    WEIGHTS = {
        "news": 0.25,
        "regime": 0.20,
        "relative_strength": 0.20,
        "sector": 0.15,
        "catalyst_risk": 0.10,
        "paper_feedback": 0.10,
    }

    def score_symbol(
        self,
        *,
        symbol: str,
        watchlist_row: dict[str, Any],
        analysis: dict[str, Any] | None,
        news_signal: dict[str, Any],
        market_regime: dict[str, Any] | None,
        benchmark_analysis: dict[str, Any] | None,
        paper_trades: list[dict[str, Any]],
        catalyst_events: list[dict[str, Any]],
        news_provider_error: bool = False,
    ) -> dict[str, Any]:
        sym = symbol.strip().upper()
        sector = watchlist_row.get("sector") or "—"
        company = watchlist_row.get("company") or sym

        news = self._news_scores(news_signal, news_provider_error)
        regime = self._regime_context_scores(market_regime)
        rel = self._relative_strength_scores(analysis, benchmark_analysis)
        sector_score = self._sector_strength_score(watchlist_row, market_regime)
        catalyst = self._catalyst_scores(sym, catalyst_events, news_signal)
        paper = self._paper_feedback_scores(sym, paper_trades)

        # Bull/bear scoring uses only lightweight signals
        bull_raw = (
            news["bull"] * self.WEIGHTS["news"]
            + regime["bull"] * self.WEIGHTS["regime"]
            + rel["bull"] * self.WEIGHTS["relative_strength"]
            + sector_score["bull"] * self.WEIGHTS["sector"]
            + (100 - catalyst["risk"]) * self.WEIGHTS["catalyst_risk"]
            + paper["score"] * self.WEIGHTS["paper_feedback"]
        )
        bear_raw = (
            news["bear"] * self.WEIGHTS["news"]
            + regime["bear"] * self.WEIGHTS["regime"]
            + rel["bear"] * self.WEIGHTS["relative_strength"]
            + sector_score["bear"] * self.WEIGHTS["sector"]
            + (100 - catalyst["risk"]) * self.WEIGHTS["catalyst_risk"]
            + (100 - paper["score"]) * self.WEIGHTS["paper_feedback"]
        )

        bull_score = _clamp(bull_raw)
        bear_score = _clamp(bear_raw)
        direction = self._direction(bull_score, bear_score)

        news_score = _clamp(news["score"])
        market_regime_score = _clamp((regime["bull"] + regime["bear"]) / 2)
        relative_strength_score = _clamp((rel["bull"] + rel["bear"]) / 2)
        paper_feedback_score = _clamp(paper["score"])

        risk = self._risk_score(
            news_signal=news_signal,
            catalyst=catalyst,
            bull_score=bull_score,
            bear_score=bear_score,
            news_provider_error=news_provider_error,
        )

        base_opp = max(bull_score, bear_score)
        market_opportunity_score = _clamp(
            base_opp
            - risk * 0.30
            - (10 if news_provider_error else 0)
        )

        confidence = self._confidence(
            news=news,
            bull_score=bull_score,
            bear_score=bear_score,
            market_regime=market_regime,
        )

        tech_confidence = _technical_confidence(analysis)
        snapshot_age = _snapshot_age_minutes(analysis)

        data_quality = self._data_quality(news, news_provider_error, market_regime)
        reason = self._build_reason(
            direction=direction,
            bull_score=bull_score,
            bear_score=bear_score,
            news=news,
            regime=regime,
            rel=rel,
            catalyst=catalyst,
            risk=risk,
            analysis=analysis,
            news_provider_error=news_provider_error,
            sector=sector,
        )

        regime_name = (market_regime or {}).get("summary", {}).get("regime_name", "Unknown")
        market_context = f"{regime_name} · {sector}"

        # Legacy fields preserved for backward compat
        tech_score_legacy = 0.0
        if analysis and tech_confidence == "Fresh":
            tech_score_legacy = self._compute_legacy_technical_score(analysis)

        return {
            "symbol": sym,
            "company": company,
            "sector": sector,
            "priority": watchlist_row.get("priority", 99),
            "direction_candidate": direction,
            "market_opportunity_score": market_opportunity_score,
            "opportunity_score": market_opportunity_score,  # backward compat alias
            "bull_score": bull_score,
            "bear_score": bear_score,
            "confidence_score": confidence,
            "risk_score": risk,
            "news_score": news_score,
            "technical_score": tech_score_legacy,
            "technical_confidence": tech_confidence,
            "liquidity_score": 0.0,  # only available after Analyze Live
            "market_regime_score": market_regime_score,
            "relative_strength_score": relative_strength_score,
            "paper_feedback_score": paper_feedback_score,
            "next_earnings": catalyst.get("next_earnings"),
            "top_catalyst": news_signal.get("top_catalyst") or catalyst.get("top_catalyst"),
            "market_context": market_context,
            "data_quality": data_quality,
            "reason_json": reason,
            "has_analyzer_snapshot": analysis is not None,
            "has_options_data": False,  # only after Analyze Live
            "has_news_data": news["has_data"] and not news_provider_error,
            "snapshot_age_minutes": snapshot_age,
            "last_analyzed_at": analysis.get("timestamp") if analysis else None,
            "technical_hint": (
                "Click Analyze Live for full analysis."
                if tech_confidence == "Not Evaluated"
                else (
                    "Live analysis will refresh technicals and options."
                    if tech_confidence == "Stale"
                    else None
                )
            ),
        }

    @staticmethod
    def _direction(bull: float, bear: float) -> str:
        if bull >= 70 and bull - bear >= 15:
            return "Bullish"
        if bear >= 70 and bear - bull >= 15:
            return "Bearish"
        return "Neutral"

    def _news_scores(self, news_signal: dict[str, Any], provider_error: bool) -> dict[str, Any]:
        if provider_error:
            return {
                "score": 50,
                "bull": 50,
                "bear": 50,
                "has_data": False,
                "summary": "News data unavailable. News not used in score.",
                "sentiment_label": "Unavailable",
            }
        score = float(news_signal.get("news_score_0_to_100") or 50)
        label = (news_signal.get("label") or "Neutral").lower()
        bull = score if "bull" in label else (score * 0.6 if label == "neutral" else max(0, 100 - score))
        bear = score if "bear" in label else (score * 0.6 if label == "neutral" else max(0, 100 - score))
        if label == "neutral":
            bull = bear = 50.0
        has_data = bool(news_signal.get("last_updated"))
        summary_parts = []
        if news_signal.get("top_catalyst"):
            summary_parts.append(str(news_signal["top_catalyst"])[:120])
        if news_signal.get("top_risk_event"):
            summary_parts.append(f"Risk: {str(news_signal['top_risk_event'])[:80]}")
        return {
            "score": score,
            "bull": _clamp(bull),
            "bear": _clamp(bear),
            "has_data": has_data,
            "summary": " · ".join(summary_parts) if summary_parts else ("No recent news" if not has_data else "News cached"),
            "sentiment_label": news_signal.get("label", "Neutral"),
        }

    def _regime_context_scores(self, market_regime: dict[str, Any] | None) -> dict[str, Any]:
        summary = (market_regime or {}).get("summary") or {}
        regime_name = (summary.get("regime_name") or "Unknown").lower()
        risk_level = (summary.get("risk_level") or "Medium").lower()
        bull = 50.0
        bear = 50.0
        context = summary.get("regime_name", "Unknown")

        if "bull" in regime_name:
            bull += 25
            bear += 5
        elif "bear" in regime_name:
            bear += 25
            bull += 5
        elif "sideways" in regime_name or "range" in regime_name:
            bull += 10
            bear += 10

        if risk_level in ("high", "extreme"):
            bull = max(0, bull - 10)
            bear = max(0, bear - 5)

        return {
            "bull": _clamp(bull),
            "bear": _clamp(bear),
            "summary": f"Market regime: {context} ({summary.get('risk_level', '—')} risk)",
            "regime_name": context,
        }

    def _sector_strength_score(
        self, watchlist_row: dict[str, Any], market_regime: dict[str, Any] | None
    ) -> dict[str, Any]:
        sector = (watchlist_row.get("sector") or "").lower()
        bull = 50.0
        bear = 50.0

        regime_summary = (market_regime or {}).get("summary") or {}
        regime_name = (regime_summary.get("regime_name") or "").lower()

        if "tech" in sector:
            if "bull" in regime_name:
                bull += 20
            elif "bear" in regime_name:
                bear += 15
        elif "financ" in sector or "bank" in sector:
            bull += 10
            bear += 10
        elif "health" in sector or "pharma" in sector:
            bull += 12
        elif "energy" in sector:
            if "bear" in regime_name:
                bear += 15
            else:
                bull += 10

        return {"bull": _clamp(bull), "bear": _clamp(bear)}

    def _relative_strength_scores(
        self,
        analysis: dict[str, Any] | None,
        benchmark: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not analysis or not benchmark:
            return {"bull": 50, "bear": 50, "summary": "Relative strength unavailable (run QQQ/SPY analysis)."}
        sym_pct = float(analysis.get("bullish_score") or 0) - float(analysis.get("bearish_score") or 0)
        bench_pct = float(benchmark.get("bullish_score") or 0) - float(benchmark.get("bearish_score") or 0)
        rel = sym_pct - bench_pct
        bull = 50 + min(40, max(-40, rel * 2))
        bear = 50 - min(40, max(-40, rel * 2))
        if rel > 5:
            summary = "Outperforming benchmark"
        elif rel < -5:
            summary = "Underperforming benchmark"
        else:
            summary = "In line with benchmark"
        return {"bull": _clamp(bull), "bear": _clamp(bear), "summary": summary}

    def _catalyst_scores(
        self,
        symbol: str,
        events: list[dict[str, Any]],
        news_signal: dict[str, Any],
    ) -> dict[str, Any]:
        sym = symbol.upper()
        risk = 20.0
        next_earnings = None
        top_catalyst = news_signal.get("top_catalyst")
        for ev in events:
            name = (ev.get("event") or "").upper()
            days = int(ev.get("countdown_days") or 99)
            if sym in name and "EARNINGS" in name:
                next_earnings = ev.get("date")
                if days <= 7:
                    risk += 35
                elif days <= 14:
                    risk += 15
            elif days <= 3 and ev.get("expected_impact") == "High":
                risk += 10
                if not top_catalyst:
                    top_catalyst = ev.get("event")
        return {
            "risk": _clamp(risk),
            "next_earnings": next_earnings,
            "top_catalyst": top_catalyst,
        }

    def _paper_feedback_scores(self, symbol: str, trades: list[dict[str, Any]]) -> dict[str, Any]:
        sym_trades = [t for t in trades if (t.get("symbol") or "").upper() == symbol.upper()]
        closed = [t for t in sym_trades if t.get("status") in ("CLOSED", "EXPIRED")]
        if not closed:
            return {"score": 50, "summary": "No closed paper trades for symbol"}
        wins = sum(1 for t in closed if float(t.get("realized_pnl") or 0) > 0)
        win_rate = wins / len(closed) * 100
        return {"score": _clamp(win_rate), "summary": f"Paper win rate {win_rate:.0f}% ({len(closed)} trades)"}

    def _risk_score(
        self,
        *,
        news_signal: dict[str, Any],
        catalyst: dict[str, Any],
        bull_score: float,
        bear_score: float,
        news_provider_error: bool,
    ) -> float:
        risk = catalyst["risk"] * 0.4
        if news_provider_error:
            risk += 8
        if abs(bull_score - bear_score) < 10 and max(bull_score, bear_score) > 55:
            risk += 12
        vol_regime = (news_signal.get("volatility_regime") or "").lower()
        if "high" in vol_regime:
            risk += 10
        return _clamp(risk)

    def _confidence(
        self,
        *,
        news: dict[str, Any],
        bull_score: float,
        bear_score: float,
        market_regime: dict[str, Any] | None,
    ) -> float:
        parts = 0.0
        if news["has_data"]:
            parts += 35
        if market_regime:
            parts += 30
        spread = abs(bull_score - bear_score)
        parts += min(35, spread * 0.7)
        return _clamp(parts)

    @staticmethod
    def _data_quality(
        news: dict[str, Any],
        news_provider_error: bool,
        market_regime: dict[str, Any] | None,
    ) -> str:
        score = sum([
            1 if news["has_data"] and not news_provider_error else 0,
            1 if market_regime else 0,
        ])
        if score >= 2:
            return "good"
        if score == 1:
            return "partial"
        return "poor"

    def _compute_legacy_technical_score(self, analysis: dict[str, Any]) -> float:
        """Compute a technical indicator score from snapshot (legacy display only)."""
        daily = analysis.get("daily_indicators") or {}
        close = float(analysis.get("underlying_price") or daily.get("close") or 0)
        score = 0.0
        ema20 = daily.get("ema20")
        ema50 = daily.get("ema50")
        if close and ema20 and close > ema20:
            score += 20
        if close and ema50 and close > ema50:
            score += 15
        if ema20 and ema50 and ema20 > ema50:
            score += 15
        rsi = daily.get("rsi14")
        if rsi is not None and rsi > 50:
            score += 15
        macd_line = daily.get("macd_line")
        macd_signal = daily.get("macd_signal")
        if macd_line is not None and macd_signal is not None and macd_line > macd_signal:
            score += 20
        return _clamp(score)

    def _build_reason(
        self,
        *,
        direction: str,
        bull_score: float,
        bear_score: float,
        news: dict[str, Any],
        regime: dict[str, Any],
        rel: dict[str, Any],
        catalyst: dict[str, Any],
        risk: float,
        analysis: dict[str, Any] | None,
        news_provider_error: bool,
        sector: str,
    ) -> dict[str, Any]:
        bullets: list[str] = []
        if direction == "Bullish":
            bullets.append(f"Bull score {bull_score:.0f} leads bear {bear_score:.0f}")
        elif direction == "Bearish":
            bullets.append(f"Bear score {bear_score:.0f} leads bull {bull_score:.0f}")
        else:
            bullets.append(f"Mixed signals (bull {bull_score:.0f}, bear {bear_score:.0f})")

        if news.get("summary") and news["summary"] != "No recent news":
            bullets.append(f"News: {news['summary'][:80]}")
        if regime.get("summary"):
            bullets.append(regime["summary"])

        tech_confidence = _technical_confidence(analysis)
        if tech_confidence == "Not Evaluated":
            bullets.append("Technical data unavailable — click Analyze Live")
        elif tech_confidence == "Stale":
            bullets.append("Technical snapshot is stale — click Analyze Live for fresh data")

        return {
            "summary": bullets[0] if bullets else "Insufficient data",
            "bullets": bullets[:6],
            "bull_evidence": [],
            "bear_evidence": [],
            "risk_factors": list(dict.fromkeys(
                ([f"Earnings within 7 days ({catalyst.get('next_earnings')})"] if catalyst.get("next_earnings") else [])
                + (["News provider error"] if news_provider_error else [])
                + ([f"Conflicting bull/bear scores"] if abs(bull_score - bear_score) < 10 else [])
            )),
            "news_summary": news.get("summary"),
            "technical_summary": (
                f"Technical Confidence: {tech_confidence}"
            ),
            "liquidity_summary": "Options liquidity evaluated on Analyze Live only.",
            "regime_context": regime.get("summary"),
            "relative_strength_summary": rel.get("summary"),
            "data_availability": {
                "analyzer_snapshot": analysis is not None,
                "options_data": False,
                "news_data": news.get("has_data") and not news_provider_error,
            },
            "sector": sector,
            "risk_score": risk,
        }
