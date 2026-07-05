# Billion Dollar — Options Alpha Research Platform

Research-only options spread analysis for **QQQ** and any ticker. Paper trading and IBKR position sync are supported. **No live order placement.**

## Features

| Page | Route | Description |
|------|-------|-------------|
| QQQ Spread Analyzer | `/qqq-spread-analyzer` | Full QQQ analysis, Market Regime summary, Trade Decision Engine |
| Options Spread Strategy | `/options-spread-strategy` | Same dashboard for any symbol (e.g. SPY, NVDA) — the single live analysis engine |
| Paper Trading Lab | `/paper-trading-lab` | Paper trades, IBKR sync, mark-to-market, analytics |
| Market Regime | `/market-regime` | Multi-instrument regime dashboard with history |
| Market Intelligence | `/market-intelligence` | News, filings, catalysts, sentiment, watchlist |
| Opportunity Scanner | `/opportunity-scanner` | Rank watchlist symbols by Market Opportunity Score + Technical Confidence |

## Recommended Workflow

**Full UI SOP** (every button, table, when/why): [Architecture Reference §15](Billion-Dollar-Architecture-Reference.md#15-ui-user-guide-sop).

```
1. Market Open Refresh     → lightweight: news + regime + ranking (no IBKR)
2. Review Opportunity Scanner → pick a symbol
3. Analyze Live (auto-runs) → full IBKR analysis + TDE on Options Spread Strategy
4. Review TDE recommendation
5. Save to Paper Trading (if acceptable)
```

## Start the app

```bash
cd Billion_Dollar
chmod +x run_local.sh
./run_local.sh
```

- Frontend: http://localhost:3000 (redirects `/` → QQQ Spread Analyzer)
- Backend API: http://localhost:8000
- Health: `GET /health`

## Run analysis (IB required)

1. Start **IB Gateway** or **TWS** and log in (API enabled, default port **4001**).
2. The spread analyzer uses **client ID 12** (`qqq_spread_analyzer/.env`) — separate from paper-trading IBKR sync.
3. Click **Run analysis** on either spread page (~1–2 min), or use **Analyze Live** from Opportunity Scanner.
4. **Refresh** reloads the saved JSON snapshot only (no new IB fetch).

Failed runs log to `qqq_spread_analyzer/data/analyzer_last_run.log` (wiped each run).

### IB client IDs

| Use | Client ID | Config |
|-----|-----------|--------|
| Spread analyzer (CLI + API subprocess) | **12** | `qqq_spread_analyzer/.env` → `IB_CLIENT_ID=12` |
| Paper Trading Lab IBKR sync | **13** | `backend/config.yaml` → `tws_client_id: 13` |
| IBKR News (Market Intelligence) | **23** | `backend/app/config.py` → `ibkr_news_client_id: 23` |

Use different client IDs so analyzer runs, paper sync, and news fetch can coexist without IB error 326.

## API

### Health

| Method | Path |
|--------|------|
| GET | `/health` |

### Global Refresh (`/api/global`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/global/market-open-refresh` | Lightweight: MI → MR → OS (no IBKR) |
| GET | `/api/global/market-open-refresh/status` | Last refresh timestamps + module status |
| POST | `/api/global/analyze-top-n` | Sequential IBKR analysis for top N symbols |
| GET | `/api/global/analyze-top-n/status` | Analyze Top N job progress |

### Spread analyzer

| Method | Path |
|--------|------|
| GET | `/api/qqq-spread-analyzer/latest?symbol=QQQ` |
| POST | `/api/qqq-spread-analyzer/run` |
| GET | `/api/qqq-spread-analyzer/run/{job_id}` |
| GET | `/api/options-spread-strategy/latest?symbol=SPY` |
| POST | `/api/options-spread-strategy/run` |
| GET | `/api/options-spread-strategy/run/{job_id}` |

### Market regime (`/api/market-regime`)

| Method | Path |
|--------|------|
| GET | `/api/market-regime/latest` |
| POST | `/api/market-regime/refresh` |
| POST | `/api/market-regime/refresh-all` |
| POST | `/api/market-regime/save-snapshot` |
| GET | `/api/market-regime/history?days=30` |
| GET | `/api/market-regime/export` |

### Trade decision (`/api/trade-decision`)

| Method | Path |
|--------|------|
| POST | `/api/trade-decision/record` |
| GET | `/api/trade-decision/recent/{symbol}` |

Trade decision **scoring runs in the browser**; the API persists audit rows only.

### Paper trading (`/api/paper-trading`)

| Method | Path |
|--------|------|
| POST | `/api/paper-trading/trades` |
| POST | `/api/paper-trading/trades/bulk` |
| GET | `/api/paper-trading/trades` |
| GET | `/api/paper-trading/trades/{trade_id}` |
| PATCH | `/api/paper-trading/trades/{trade_id}` |
| POST | `/api/paper-trading/trades/{trade_id}/close` |
| GET | `/api/paper-trading/summary` |
| GET | `/api/paper-trading/analytics` |
| GET | `/api/paper-trading/export` |
| POST | `/api/paper-trading/ibkr/fetch-positions` |
| POST | `/api/paper-trading/ibkr/refresh-prices` |
| POST | `/api/paper-trading/ibkr/recalculate` |
| POST | `/api/paper-trading/ibkr/sync` |
| GET | `/api/paper-trading/ibkr/status` |
| POST | `/api/paper-trading/ibkr/auto-sync` |
| POST | `/api/paper-trading/mark/{symbol}` |

### Market Intelligence (`/api/market-intelligence`)

| Method | Path |
|--------|------|
| GET | `/api/market-intelligence/dashboard` |
| POST | `/api/market-intelligence/refresh` |
| GET | `/api/market-intelligence/export` |
| GET | `/api/market-intelligence/watchlist` |
| PATCH | `/api/market-intelligence/watchlist/{symbol}` |
| POST | `/api/market-intelligence/watchlist/reset` |
| GET | `/api/market-intelligence/signal/{symbol}` |
| GET | `/api/market-intelligence/ticker-signals` |

Refresh modes: `quick` (24h, top watchlist), `standard` (7d, all enabled), `deep` (7d + full SEC sweep).

`ticker-signals` returns one consolidated row per symbol (bias, quality, top catalyst/risk) instead of raw article rows — see "Ticker-level news intelligence" below.

### Opportunity Scanner (`/api/opportunity-scanner`)

| Method | Path |
|--------|------|
| GET | `/api/opportunity-scanner/latest` |
| POST | `/api/opportunity-scanner/refresh` |
| GET | `/api/opportunity-scanner/export` |
| GET | `/api/opportunity-scanner/symbol/{symbol}` |

Ranks watchlist by **Market Opportunity Score** — Catalyst Strength 30% + Relative Strength/Momentum 25% + Market Regime Fit 20% + News Quality 15% + Earnings/Event Timing 5% + Paper Trading Feedback 5% (news/regime/strength only — no stale technicals). Direction Bias (Bullish/Bearish/Neutral/Mixed) and Trade Readiness (Ready/Needs Analyze Live/Blocked) are separate columns. Does not output final strategy — use Analyze Live → Options Spread Strategy → Trade Decision Engine.

### AI Report (`/api/ai-report`)

| Method | Path |
|--------|------|
| POST | `/api/ai-report/generate` |
| GET | `/api/ai-report/latest` |
| GET | `/api/ai-report/download/{format}` |

### News Intelligence (QQQ embed + legacy routes)

| Method | Path |
|--------|------|
| POST | `/api/news-intelligence/quick-refresh` |
| GET | `/api/news-intelligence/signal/{symbol}` |

Delegates to Market Intelligence service. Configure keys in `backend/.env`.

## News Intelligence CLI (optional)

```bash
cd backend
PYTHONPATH=. poetry run python -m news_intelligence.test_news_fetch
```

Providers: Finnhub (market + company news), Alpha Vantage (sentiment), SEC EDGAR (filings), IBKR News (optional — Dow Jones, Briefing.com via IB Gateway). Results persist to `news_items` and `news_fetch_log` in SQLite.

### IBKR News (optional)

When IB Gateway is running on port 4001, IBKR News provides high-quality Dow Jones and Briefing.com headlines. If unavailable, the app falls back to Finnhub/Alpha Vantage/SEC EDGAR seamlessly.

Provider priority: **IBKR News** (primary) > **SEC EDGAR** (official filings) > **Alpha Vantage** (earnings calendar/sentiment fallback) > **Finnhub** (general fallback only — its per-symbol company-news fetch is skipped whenever IBKR already covered that symbol this run).

Available IBKR news providers:
- DJ-N (Dow Jones Global Equity Trader)
- DJ-RT (Dow Jones Trader News)
- DJNL (Dow Jones Newsletters)
- BRFUPDN (Briefing.com Analyst Actions)
- BRFG (Briefing.com General Market Columns)

Limits: max 5 symbols during Market Open Refresh, 30-minute cache TTL, 10-day lookback, 20 headlines per symbol.

**Implementation:** Native `ibapi` (not `ib_insync`) — callback + thread pattern matching `PlayRough/news.py`. Default providers per request: `BRFG+BRFUPDN+DJ-N`. Waits 8s after `reqHistoricalNews` for HMDS/news farm. Empty results are not cached; pipeline falls back to Finnhub/AV/SEC.

**Manual smoke test (requires IB Gateway on 4001):**

```bash
cd backend
PYTHONPATH=. ../pyenv_global/bin/python <<'EOF'
from app.services.news_intelligence.ibkr_news_client import IbkrNewsClient
from app.services.news_intelligence.ibkr_news_adapter import normalize_ibkr_result, clean_headline
client = IbkrNewsClient()
print(client.is_available())
result = client.fetch_historical_news("AAPL", lookback_days=10, max_headlines=20)
print(f"headlines={len(result.headlines)} error={result.error}")
for item in normalize_ibkr_result(result)[:5]:
    print(f"  [{item.source}] {clean_headline(item.headline)[:100]}")
client.disconnect()
EOF
```

Backend runs via `run_local.sh` using Poetry + `pyenv_global` (`../pyenv_global`). Dependency: `ibapi` in `backend/pyproject.toml`.

### Ticker-level news intelligence

Raw headlines are noisy — the same story gets repeated across wires, and articles get attached to the wrong symbol. A second stage consolidates deduped headlines into **one row per symbol** (`ticker_news_signals`) instead of scoring every article individually:

1. **Primary ticker detection** — is this headline actually about NVDA, or does it just mention NVDA in passing? Scored 0-100; below 40 the item doesn't count toward any symbol's score at all, below 60 it can't become a top catalyst.
2. **Event classification** — 14 categories (SEC filing, earnings, guidance, analyst action, M&A, insider activity, macro, etc.), checked in priority order.
3. **Clustering** — similar headlines about the same symbol + category get merged into one event instead of showing as repeated rows.
4. **Impact score** — combines sentiment, primary-ticker confidence, event importance, source quality, and recency into one -100..+100 number per event.
5. **Ticker signal** — each symbol's events roll up into a bias (Bullish/Bearish/Mixed/Neutral), a top catalyst, a top risk, and a quality score, served at `GET /api/market-intelligence/ticker-signals`.
6. **Optional OpenAI summary** — for symbols with at least one Critical/High-importance, primary-ticker-score ≥70 cluster (top 10 max, never every article), an LLM produces a structured summary (bullish/bearish factors, key catalyst/risk, sentiment, one-sentence trade context), cached and only regenerated when the qualifying cluster set changes. Falls back to a deterministic rule-based summary if `OPENAI_API_KEY` is unset or the request fails.

This feeds the Trade Decision Engine's news sub-score (neutral 50 if a symbol has no signal yet — never assumes good news). The Market Intelligence dashboard shows this ticker-level table as its default view — raw article rows live in a collapsible "Raw Articles (Diagnostics)" section — and the Opportunity Scanner surfaces the same News Bias/Quality/Top Risk fields per symbol.

## CLI (optional)

```bash
cd qqq_spread_analyzer
poetry run python -m src.main --symbol QQQ --mode analyze
```

See [qqq_spread_analyzer/README.md](qqq_spread_analyzer/README.md) for full CLI options.

## Tests

```bash
cd backend
python -m pytest tests/ -q
```

## Config

`backend/config.yaml`:

```yaml
qqq_analyzer_poetry: /opt/homebrew/bin/poetry
tws_client_id: 13
tws_port: 4001
```

### Stale data thresholds (configurable in `backend/app/config.py`)

| Threshold | Default | Purpose |
|-----------|---------|---------|
| `technical_stale_minutes` | 60 | Analyzer snapshot freshness |
| `news_stale_minutes` | 30 | News data freshness |
| `regime_stale_minutes` | 60 | Market Regime freshness |
| `scanner_stale_minutes` | 60 | Opportunity Scanner freshness |

### IBKR News settings (configurable in `backend/app/config.py`)

| Setting | Default | Purpose |
|---------|---------|---------|
| `ibkr_news_enabled` | true | Enable IBKR News provider |
| `ibkr_news_client_id` | 23 | TWS client ID for news connection |
| `ibkr_news_cache_ttl_seconds` | 1800 | Cache duration (30 min) |
| `ibkr_news_lookback_days` | 10 | Historical news window |
| `ibkr_news_max_headlines` | 20 | Max headlines per symbol |
| `ibkr_news_max_symbols_refresh` | 5 | Max symbols during Market Open Refresh |
| `ibkr_news_request_timeout_seconds` | 30 | Reserved; native ibapi uses fixed wait below |
| `ibkr_news_wait_seconds` | 8 | Seconds to wait after reqHistoricalNews (HMDS farm) |

### Environment overrides

| Variable | Purpose |
|----------|---------|
| `QQQ_ANALYZER_DATA_DIR` | Override analyzer JSON output directory |
| `QQQ_ANALYZER_POETRY` | Path to Poetry binary for subprocess runs |
| `FINNHUB_API_KEY` | News Intelligence — Finnhub |
| `ALPHA_VANTAGE_API_KEY` | News Intelligence — Alpha Vantage (optional) |
| `SEC_USER_AGENT` | SEC EDGAR User-Agent (required format: `AppName email@example.com`) |
| `FINNHUB_DAILY_LIMIT` | API budget display limit (default 1000) |
| `ALPHA_VANTAGE_DAILY_LIMIT` | API budget display limit (default 25) |
| `SEC_DAILY_LIMIT` | API budget display limit (default 10000) |
| `OPENAI_API_KEY` | Optional — enables the ticker-level LLM summary layer; unset = deterministic rule-based summary instead |
| `OPENAI_MODEL` | Optional — defaults to `gpt-4o-mini` |

## Documentation

| File | Purpose |
|------|---------|
| [Billion-Dollar-Architecture-Reference.md](Billion-Dollar-Architecture-Reference.md) | Canonical architecture + **§15 UI user SOP** (every button/table) |
| [PSEUDOCODE.md](PSEUDOCODE.md) | Algorithms, logic flows, and step-by-step pseudocode |
