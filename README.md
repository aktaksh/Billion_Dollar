# Billion Dollar — Spread Analyzer

Research-only options spread analysis for **QQQ** and any ticker. No live order placement.

## Features

| Page | Route | Description |
|------|-------|-------------|
| QQQ Spread Analyzer | `/qqq-spread-analyzer` | Full spread analysis for QQQ |
| Options Spread Strategy | `/options-spread-strategy` | Same dashboard for any symbol (e.g. SPY) |

Both pages share the same panels: bias, indicators, key levels, spread candidates, option chain, diagnostics, and backtest summary.

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
2. Analyzer uses **client ID 12** (`qqq_spread_analyzer/.env`) — separate from any other IB connections.
3. Click **Run analysis** on either page (~1–2 min).
4. **Refresh** reloads the saved JSON snapshot only (no new IB fetch).

Failed runs log to `qqq_spread_analyzer/data/analyzer_last_run.log` (wiped each run).

## API

| Method | Path |
|--------|------|
| GET | `/api/qqq-spread-analyzer/latest?symbol=QQQ` |
| POST | `/api/qqq-spread-analyzer/run` |
| GET | `/api/qqq-spread-analyzer/run/{job_id}` |
| GET | `/api/options-spread-strategy/latest?symbol=SPY` |
| POST | `/api/options-spread-strategy/run` |
| GET | `/api/options-spread-strategy/run/{job_id}` |

## CLI (optional)

```bash
cd qqq_spread_analyzer
poetry run python -m src.main --symbol QQQ --mode analyze
```

## Tests

```bash
cd backend
python -m pytest tests/ -q
```

## Config

`backend/config.yaml`:

```yaml
qqq_analyzer_poetry: /opt/homebrew/bin/poetry
```

Override data dir: `QQQ_ANALYZER_DATA_DIR` env var.
