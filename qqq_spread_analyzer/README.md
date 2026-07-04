# QQQ Spread Analyzer

Research-only CLI for QQQ 2–4 week bull/bear debit spread analysis. **IB Gateway supplies raw data only** — all indicators, scoring, and spread math run locally in Python. **No orders are placed.**

Lives inside the Billion Dollar repo at `Billion_Dollar/qqq_spread_analyzer/`. Reuses Billion Dollar's proven option-chain parsing from `backend/app/services/broker/option_chain_ibkr.py`.

## Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/)
- IB Gateway running with **Read-Only API** enabled
- Market data subscriptions for QQQ stock + options

Indicators (EMA, RSI, MACD, ATR, Bollinger) are computed with **pandas/numpy only** — no pandas-ta/numba dependency.

## IB Gateway setup

| Setting | Recommended |
|---------|-------------|
| Host | `127.0.0.1` |
| Port | `4001` (IB Gateway paper/live) |
| Client ID | `12` (analyzer — separate from paper-trading sync client ID **13** in `backend/config.yaml`) |
| Read-only | **Yes** |

Copy env file:

```bash
cd qqq_spread_analyzer
cp .env.example .env
```

## Install (Poetry)

Poetry is at `/opt/homebrew/bin/poetry`. The project requires **Python 3.11–3.12** (not 3.14).

```bash
cd Billion_Dollar/qqq_spread_analyzer
cp .env.example .env

# Pin Python 3.12 if your shell default is 3.14
poetry env use python3.12

poetry install
poetry run python -m pytest -q          # verify: 16 passed
```

## Commands

All commands use the Poetry virtualenv (`poetry run ...`):

```bash
# Full analysis report (bars + indicators + scoring + spread candidates)
poetry run python -m src.main --symbol QQQ --mode analyze

# Bar-based signal backtest (proxy P&L — see limitations)
poetry run python -m src.main --symbol QQQ --mode backtest

# Store today's option chain + Greeks for forward backtesting
poetry run python -m src.main --symbol QQQ --mode snapshot

# Force refresh bars from IB (skip DuckDB cache)
poetry run python -m src.main --symbol QQQ --mode analyze --no-cache
```

Optional: activate the venv once, then run without `poetry run`:

```bash
poetry shell
python -m src.main --symbol QQQ --mode analyze
```

## Output sections

1. Timestamp & underlying price  
2. Market bias (Bullish / Bearish / Neutral)  
3. Confidence (High / Medium / Low)  
4. Daily indicator summary  
5. 2H/4H timing summary  
6. Support / resistance levels  
7. Suggested action (bull call / bear put / no trade)  
8. Candidate spreads table (**max loss always shown**)  
9. Risk notes (read-only positions/orders, liquidity warnings)

## Scoring rules (summary)

- **Bullish setup:** bullish score ≥ 7, bearish ≤ 3, intraday timing ≥ 3 → bull call spread  
- **Bearish setup:** bearish score ≥ 6, bullish ≤ 4, intraday timing ≥ 3 → bear put spread  
- Otherwise → **No trade / wait**

## Spread filters

- DTE 21–45  
- Bull call: buy δ 0.35–0.45, sell δ 0.20–0.30  
- Bear put: buy δ −0.35 to −0.45, sell δ −0.20 to −0.30  
- Reject if bid/ask spread > 15% of mid  
- Prefer OI > 500, volume > 100 when available  

## Backtest limitations

IB Gateway does **not** provide historical option Greeks. The `backtest` mode uses **daily bar proxy P&L** for signal timing research. Run `snapshot` daily during live sessions to build a DuckDB dataset for future option-level backtests.

## Tests

```bash
poetry run pytest
```

## Relationship to Billion Dollar app

This CLI is the analysis engine behind the **QQQ Spread Analyzer** and **Options Spread Strategy** web pages. See the parent [README.md](../README.md) for the full app.

| Component | Relationship |
|-----------|--------------|
| Web UI | FastAPI spawns this CLI via `POST /api/qqq-spread-analyzer/run`; frontend reads `latest_analysis_{SYMBOL}.json` |
| QQQ page embeds | Market Regime Phase 1 (`frontend/lib/marketRegime.ts`) + Trade Decision Engine on top of analysis JSON |
| IB client ID | Analyzer uses **12** (`qqq_spread_analyzer/.env`); Paper Trading Lab IBKR sync uses **13** (`backend/config.yaml`) |
| Option secdef parsing | Imports `option_chain_ibkr` from `backend/app/services/broker/` |
| DuckDB cache | Local to this package (`data/analyzer.duckdb`) |
| News Intelligence | Separate CLI module in `backend/news_intelligence/` — not invoked by analyzer runs |

Start the full app from repo root: `./run_local.sh`
