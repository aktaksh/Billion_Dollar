"""Optional OpenAI cluster-summary layer (Part 8).

Only called after Parts 4-7 filtering already happened. This module applies one
more filter on top of that: it never sends every clustered event to OpenAI —
only the top 5-10 Critical/High-importance, primary_ticker_score >= 70 clusters
per symbol. If OPENAI_API_KEY is missing, or the request fails for any reason,
callers get a deterministic rule-based summary instead — this layer must never
break the news pipeline.

Caching: the summary is only regenerated when the qualifying event set for a
symbol actually changes (new/removed cluster, or a cluster's impact score
moved), tracked via a stable fingerprint hash (`llm_cluster_hash`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import httpx

from news_intelligence.news_categories import importance_label

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
MIN_PRIMARY_TICKER_SCORE = 70.0
MAX_EVENTS = 10
REQUEST_TIMEOUT_SECONDS = 20.0

SUMMARY_KEYS = (
    "ticker_summary",
    "bullish_factors",
    "bearish_factors",
    "key_catalyst",
    "key_risk",
    "sentiment_label",
    "confidence",
    "one_sentence_trade_context",
)


def select_events_for_llm(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Part 8 filtering — never send every article to the LLM.

    Only Critical/High importance clusters with primary_ticker_score >= 70
    qualify; of those, only the top 5-10 (ranked by importance, then by
    |impact_score|) are actually sent.
    """
    qualifying = [
        e
        for e in events
        if float(e.get("primary_ticker_score") or 0) >= MIN_PRIMARY_TICKER_SCORE
        and importance_label(float(e.get("importance_score") or 0)) in ("Critical", "High")
    ]
    qualifying.sort(
        key=lambda e: (float(e.get("importance_score") or 0), abs(float(e.get("impact_score") or 0))),
        reverse=True,
    )
    return qualifying[:MAX_EVENTS]


def cluster_fingerprint(events: list[dict[str, Any]]) -> str:
    """Stable hash of the qualifying event set for a symbol.

    The summary is only regenerated when this changes — never on every
    pipeline run just because the same clusters were re-fetched.
    """
    parts = sorted(
        f"{e.get('cluster_id') or e.get('id')}:{round(float(e.get('impact_score') or 0), 2)}"
        for e in events
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _rule_based_summary(symbol: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic fallback used when OPENAI_API_KEY is missing or the API
    call fails — matches the OpenAI output shape so callers never branch on it."""
    bullish = [e for e in events if float(e.get("impact_score") or 0) > 0]
    bearish = [e for e in events if float(e.get("impact_score") or 0) < 0]
    top_catalyst = max(bullish, key=lambda e: float(e["impact_score"]), default=None)
    top_risk = min(bearish, key=lambda e: float(e["impact_score"]), default=None)
    net = sum(float(e.get("impact_score") or 0) for e in events)

    if not events:
        sentiment_label = "Neutral"
        ticker_summary = f"No qualifying high-confidence catalysts for {symbol} right now."
    elif net > 15:
        sentiment_label = "Bullish"
        ticker_summary = f"{len(bullish)} bullish catalyst(s) outweigh {len(bearish)} risk event(s) for {symbol}."
    elif net < -15:
        sentiment_label = "Bearish"
        ticker_summary = f"{len(bearish)} risk event(s) outweigh {len(bullish)} bullish catalyst(s) for {symbol}."
    else:
        sentiment_label = "Mixed" if bullish and bearish else "Neutral"
        ticker_summary = f"Mixed/limited signal from {len(events)} qualifying event(s) for {symbol}."

    return {
        "ticker_summary": ticker_summary,
        "bullish_factors": [e.get("title") for e in bullish[:5] if e.get("title")],
        "bearish_factors": [e.get("title") for e in bearish[:5] if e.get("title")],
        "key_catalyst": top_catalyst.get("title") if top_catalyst else None,
        "key_risk": top_risk.get("title") if top_risk else None,
        "sentiment_label": sentiment_label,
        "confidence": "Medium" if len(events) >= 3 else "Low",
        "one_sentence_trade_context": ticker_summary,
        "source": "rule_based",
    }


def _call_openai(symbol: str, events: list[dict[str, Any]], *, api_key: str, model: str) -> dict[str, Any] | None:
    event_lines = [
        {
            "title": e.get("title"),
            "category": e.get("primary_category"),
            "sentiment_score": e.get("sentiment_score"),
            "impact_score": e.get("impact_score"),
            "sources": e.get("sources_json"),
            "latest_time": str(e.get("latest_time")) if e.get("latest_time") else None,
        }
        for e in events
    ]

    system_prompt = (
        "You are a markets news analyst. You will be given a filtered list of the most "
        "important, ticker-specific clustered news events for one stock symbol. Produce a "
        "concise, factual JSON summary. Do not invent facts not present in the events. "
        "Output strictly valid JSON with these exact keys: ticker_summary (string), "
        "bullish_factors (array of short strings), bearish_factors (array of short strings), "
        "key_catalyst (string or null), key_risk (string or null), sentiment_label (one of "
        "Bullish, Bearish, Neutral, Mixed), confidence (one of High, Medium, Low), and "
        "one_sentence_trade_context (a single plain-English sentence). This is informational "
        "only, not a trade recommendation."
    )
    user_prompt = json.dumps({"symbol": symbol, "events": event_lines}, default=str)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = client.post(OPENAI_CHAT_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except Exception as exc:
        logger.warning("OpenAI ticker summary call failed for %s: %s", symbol, exc)
        return None

    if not isinstance(parsed, dict) or not all(k in parsed for k in SUMMARY_KEYS):
        logger.warning("OpenAI ticker summary for %s missing expected keys", symbol)
        return None
    parsed["source"] = "openai"
    return parsed


def build_llm_ticker_summary(
    symbol: str,
    events: list[dict[str, Any]],
    *,
    cached_hash: str | None = None,
    cached_summary: dict[str, Any] | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Build (or reuse a cached) structured ticker summary.

    Returns `(summary_or_none, fingerprint)`. `summary` is `None` when there are
    no qualifying events at all — callers should leave the existing rule-based
    `ticker_news_signals.llm_summary` sentence untouched in that case rather
    than overwrite it with a "nothing to report" message. `summary["source"]`
    is one of "openai", "rule_based", or "cached".
    """
    qualifying = select_events_for_llm(events)
    fingerprint = cluster_fingerprint(qualifying)

    if not qualifying:
        return None, fingerprint

    if cached_summary and cached_hash and cached_hash == fingerprint:
        cached = dict(cached_summary)
        cached["source"] = "cached"
        return cached, fingerprint

    key = (api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")).strip()
    if not key:
        return _rule_based_summary(symbol, qualifying), fingerprint

    resolved_model = model or os.environ.get("OPENAI_MODEL", "").strip() or DEFAULT_MODEL
    result = _call_openai(symbol, qualifying, api_key=key, model=resolved_model)
    if result is None:
        return _rule_based_summary(symbol, qualifying), fingerprint
    return result, fingerprint
