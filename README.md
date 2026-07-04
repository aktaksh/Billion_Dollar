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

Use different client IDs so analyzer runs and paper sync can coexist without IB error 326.

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

Refresh modes: `quick` (24h, top watchlist), `standard` (7d, all enabled), `deep` (7d + full SEC sweep).

### Opportunity Scanner (`/api/opportunity-scanner`)

| Method | Path |
|--------|------|
| GET | `/api/opportunity-scanner/latest` |
| POST | `/api/opportunity-scanner/refresh` |
| GET | `/api/opportunity-scanner/export` |
| GET | `/api/opportunity-scanner/symbol/{symbol}` |

Ranks watchlist by **Market Opportunity Score** (news/regime/relative-strength only — no stale technicals). Does not output final strategy — use Analyze Live → Options Spread Strategy → Trade Decision Engine.

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

Provider priority: IBKR News > SEC EDGAR > Finnhub > Alpha Vantage.

Available IBKR news providers:
- DJ-N (Dow Jones Global Equity Trader)
- DJ-RT (Dow Jones Trader News)
- DJNL (Dow Jones Newsletters)
- BRFUPDN (Briefing.com Analyst Actions)
- BRFG (Briefing.com General Market Columns)

Limits: max 5 symbols during Market Open Refresh, 30-minute cache TTL, 10-day lookback, 20 headlines per symbol.

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

## Documentation

| File | Purpose |
|------|---------|
| [Billion-Dollar-Architecture-Reference.md](Billion-Dollar-Architecture-Reference.md) | Canonical architecture |
| [PSEUDOCODE.md](PSEUDOCODE.md) | Algorithms, logic flows, and step-by-step pseudocode |
