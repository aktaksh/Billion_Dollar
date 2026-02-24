# Stock Tiger

Broker-style recommendation system scaffold with:
- FastAPI backend
- Next.js + TypeScript dashboard
- Persistent event log (SQLite via SQLAlchemy in Phase 2)

Python version note:
- Use Python `3.11`, `3.12`, or `3.13` for backend virtualenv.
- Avoid Python `3.14` currently due to native build compatibility (`pydantic-core`/PyO3).

## Start Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Troubleshooting (`ModuleNotFoundError: No module named 'sqlalchemy'`):

```bash
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

## Start Frontend

```bash
cd frontend
npm install
npm run dev
```

## URLs

- Dashboard: `http://localhost:3000`
- API health: `http://localhost:8000/health`

## One-command local run (Mac/Linux)

From project root:

```bash
chmod +x run_local.sh
./run_local.sh
```

Optional:
- skip dependency install if already set up: `SKIP_INSTALL=1 ./run_local.sh`
- custom ports: `BACKEND_PORT=8010 FRONTEND_PORT=3010 ./run_local.sh`

## Phase 2 API Endpoints

Read:
- `GET /api/recommendations`
- `GET /api/risk-status`
- `GET /api/events`
- `GET /api/strategy-health`
- `GET /api/trade-review-queue`
- `GET /api/ibkr/health`
- `GET /api/ibkr/accounts`
- `GET /api/ibkr/secdef/search?symbol=AAPL`
- `GET /api/ibkr/marketdata/snapshot?conids=265598&fields=31,84,86,88`
- `GET /api/ibkr/portfolio/{account_id}/positions/{page_id}`
- `GET /api/ibkr/orders`

Write:
- `POST /api/events/candidate-signal`
- `POST /api/events/candidate-signal/bulk`
- `POST /api/signals/generate-from-ibkr`
- `POST /api/events/risk-decision`
- `POST /api/events/approval-request`
- `POST /api/events/approval-decision`
- `POST /api/events/trading-halt`
- `POST /api/events/position-closed`

The backend seeds one starter `CandidateSignal` + `RiskDecision` into the local DB on first startup.

Bulk candidate-signal example:

```bash
curl -s -X POST http://localhost:8000/api/events/candidate-signal/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "signal_id": "sig_20260220_AAPL_001",
        "ticker": "AAPL",
        "strategy_sleeve": "options_defined_risk",
        "side": "bullish",
        "signal_config_version": "sig_cfg_v1",
        "model_version": "seed_bulk_v1",
        "feature_version": "feat_v3",
        "regime_label": "trend_low_vol",
        "data_sources_used": ["IBKR"],
        "confidence_total": 74.2,
        "thesis": "Seeded candidate for AAPL",
        "entry_zone": "auto",
        "invalidation": "auto",
        "targets": ["t1", "t2"],
        "expected_edge_after_cost_usd": 22.4,
        "quote_type": "real_time",
        "trading_mode": "paper"
      }
    ]
  }' | jq
```

Auto-generate candidates from IBKR quote/news (simple ranking rules):

```bash
curl -s -X POST http://localhost:8000/api/signals/generate-from-ibkr \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["NVDA", "AAPL", "MSFT", "AMZN", "META"],
    "top_n": 3,
    "trading_mode": "paper",
    "strategy_sleeve": "options_defined_risk",
    "include_news": true
  }' | jq
```

## Docs

- `Architecture.md`
- `Event-Log-Schema.md`


# Stock-Tiger
