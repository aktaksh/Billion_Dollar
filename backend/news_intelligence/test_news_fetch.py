#!/usr/bin/env python3
"""Manual integration test for News Intelligence pipeline.

Run from backend/:
  export FINNHUB_API_KEY=...
  export SEC_USER_AGENT="BillionDollarApp you@example.com"
  export ALPHA_VANTAGE_API_KEY=...  # optional
  PYTHONPATH=. python -m news_intelligence.test_news_fetch
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from news_intelligence.news_config import load_config, mask_secret
from news_intelligence.news_orchestrator import get_news_signal, run_news_pipeline
from news_intelligence.sec_edgar_client import SecEdgarClient


def main() -> int:
    print("=" * 60)
    print("News Intelligence — fetch test")
    print("=" * 60)

    try:
        cfg = load_config()
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        print("\nRequired environment variables:")
        print("  FINNHUB_API_KEY")
        print("  SEC_USER_AGENT=BillionDollarApp your-email@example.com")
        print("Optional:")
        print("  ALPHA_VANTAGE_API_KEY")
        return 1

    print(f"Finnhub key: {mask_secret(cfg.finnhub_api_key)}")
    print(f"Alpha Vantage: {'configured' if cfg.has_alpha_vantage else 'skipped'}")
    print(f"SEC User-Agent: {cfg.sec_user_agent[:40]}...")
    print()

    symbols = ["NVDA"]
    to_date = datetime.now(UTC)
    from_date = to_date - timedelta(days=7)

    print(f"Pipeline symbols: {', '.join(symbols)} (single-symbol smoke test)")
    print(f"Date range: {from_date.date()} to {to_date.date()}")
    print()

    summary = run_news_pipeline(
        symbols=symbols,
        from_date=from_date,
        to_date=to_date,
        config=cfg,
    )

    print("--- Pipeline Summary ---")
    print(f"Total fetched:       {summary.total_fetched}")
    print(f"Total saved:         {summary.total_saved}")
    print(f"Duplicates removed:  {summary.duplicates_removed}")
    print(f"Bullish:             {summary.bullish_count}")
    print(f"Bearish:             {summary.bearish_count}")
    print(f"Neutral:             {summary.neutral_count}")
    print()

    if summary.provider_errors:
        print("--- Provider Errors ---")
        for err in summary.provider_errors:
            print(f"  - {err}")
        print()

    print("--- Top 10 Headlines (by pipeline) ---")
    headlines: list[str] = []
    headlines.extend(summary.top_positive_items)
    headlines.extend(summary.top_negative_items)
    for i, h in enumerate(headlines[:10], 1):
        print(f"  {i}. {h}")
    if not headlines:
        print("  (no headlines in summary — check provider errors or API keys)")
    print()

    print("--- get_news_signal('NVDA') ---")
    signal = get_news_signal("NVDA")
    print(f"  Label:    {signal.news_sentiment_label}")
    print(f"  Score:    {signal.news_sentiment_score}")
    print(f"  Impact:   {signal.news_impact_score}")
    print(f"  Bull/Bear/Neutral: {signal.bullish_count}/{signal.bearish_count}/{signal.neutral_count}")
    print(f"  Top +:    {signal.top_positive_headline or '—'}")
    print(f"  Top -:    {signal.top_negative_headline or '—'}")
    if signal.major_risk_events:
        print(f"  Risks:    {signal.major_risk_events}")
    print()

    print("--- SEC filings spot-check (NVDA) ---")
    sec = SecEdgarClient(cfg)
    try:
        filings = sec.fetch_recent_filings("NVDA", max_filings=5)
        print(f"  NVDA: {len(filings)} recent filings")
        for f in filings[:3]:
            print(f"    - {f['form_type']} {f['filing_date']}")
    except Exception as exc:
        print(f"  SEC error: {exc}")
    finally:
        sec.close()

    print()
    print("Done.")
    return 0 if summary.total_saved > 0 or summary.total_fetched > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
