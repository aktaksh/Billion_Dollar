# Stock Tiger Architecture

## Purpose

This document is the implementation guide for Stock Tiger.
It separates design decisions from schema details (see `Event-Log-Schema.md`).

- Recommendation engine only; final order placement is human-approved.
- Risk-first controls are mandatory.
- Broker truth is authoritative after any mismatch or reconnect.
- Canonical event/payload field names are defined in `Event-Log-Schema.md`; aliases should not be introduced in implementation.
- Universe tickers are bulk-imported by the user via JSON upload; the uploaded universe is treated as a versioned input.
- UI guides a human through: Universe → Watchlist → Trade Card → Structure Builder → Risk/Costs → Approval → Blotter → Reconcile → Review.

## Design Principles

- This system is a decision layer, not a broker UI replacement.
- Execution is intentionally boring: human-approved, idempotent, reconciled, and auditable.
- Market data and corporate actions are treated as versioned inputs; every decision must be reproducible.
- Any uncertainty (stale quotes, missing costs, rate-limited data, partial broker truth) degrades confidence or blocks entries.
- Post-trade learning is mandatory: the system improves only if outcomes are captured and reviewed.
- The UI is the product: every recommendation must be explainable (why now, why this structure, what breaks it, costs, and expected edge after costs).

---

## Scope and Non-Goals

In scope:

- 2-6 week call-focused options recommendations (defined-risk first)
- ETF monitoring and options strategies (liquid index/sector ETFs) using the same bull call spread workflow.
- stock recommendations only when they support an options plan (trend/strength filters)
- strategy-first outputs: entry, invalidation, target, exit rules, and an options structure (legs)
- human approval workflow
- risk constraints, order lifecycle, reconciliation
- local MacBook first, AWS later

Non-goals:

- fully autonomous trading
- ultra-low-latency market making

---

## Universe Import (Ticker JSON)

The trade universe is provided by the trader via a JSON upload. The backend stores the upload as a versioned input and projects the active universe for ingestion/signal cycles. For now, the default operating universe is the Top 20 S&P names supplied via JSON.

JSON format (example Top 20 S&P universe):

```json
{
  "universe_id": "sp500_top20",
  "as_of": "2026-02-21",
  "tickers": [
    "AAPL",
    "MSFT",
    "AMZN",
    "NVDA",
    "GOOGL",
    "GOOG",
    "META",
    "BRK.B",
    "TSLA",
    "JPM",
    "JNJ",
    "V",
    "PG",
    "XOM",
    "MA",
    "UNH",
    "HD",
    "AVGO",
    "COST",
    "PEP"
  ],
  "notes": "Initial Top 20 S&P universe used for monitoring and bull call spread setups"
}
```

Rules:
- Tickers must be uppercase, unique, and validated via IBKR secdef search before activation.
- Uploads emit `UniverseUploaded` and activation emits `UniverseActivated` events; the active universe is derived by projection.
- Universe changes are auditable and replayable; every recommendation must reference the universe version used.

Implementation notes (Codex targets)
- Universe upload is a multipart JSON file upload. The API must return a universe_version_id and per-ticker validation results.
- Ticker validation must call IBKR secdef search; ambiguous matches must be surfaced to UI for selection or treated as hard-fail (policy-controlled).
- Activation must be explicit (separate API call) and must emit UniverseActivated referencing the uploaded version.
- Signal cycles and idea generation must default to the active universe; direct ad-hoc ticker lists are allowed only via an explicit UI query path.
- Upload contract: multipart/form-data with field name `file` containing the universe JSON.
- Limits (MVP defaults): max_tickers=200, max_file_size_bytes=1048576.
- Ambiguous secdef default (MVP): hard-fail upload; validation_results must include ambiguous candidates for UI review.
- Activation policy (MVP): no partial activation; activation requires all tickers validated.

## High-Level Architecture Layers

1. Data Source Adapters and Normalization Layer
2. Data Quality Gate Layer
3. Market Data Cache and Snapshot Layer
4. Feature Engine Layer
5. Context Engine Layer (events, sentiment, fundamentals, analyst signals)
6. Strategy and Signal Layer (setup detection + strategy selection)
7. Options Strategy Builder Layer (structure + legs + pricing sanity)
8. Edge Validation and Calibration Layer
9. Portfolio Risk Layer
10. Approval Layer
11. Execution Layer
12. Reconciliation Layer
13. Storage and Read Models Layer
14. Backtest and Replay Layer

### Edge Validation and Calibration Layer

Responsibilities:
- weekly calibration of confidence score vs realized outcomes (PnL, win rate, payoff ratio, MAE/MFE, time-to-target)
- regime tagging (`trend`, `chop`, `high-vol`, `risk-off`) and regime-based enable/disable rules per sleeve
- cost-aware expectancy tracking; expectancy after costs must remain positive for a sleeve to stay enabled
- emits `TradingHaltEvent` when sleeve expectancy breaks thresholds or slippage deviates materially from model

---

## System Components

flowchart TD
  UI[Trader UI] --> API[FastAPI Orchestrator]
  API --> Q[Durable Job Queue]

  Q --> DI[Data Ingestion]
  DI --> DQ[Data Quality Gate]
  DQ --> MC[Market Cache / Snapshot Store]

  Q --> FE[Feature Engine]
  Q --> CX[Context Engine]
  Q --> SE[Strategy and Signal Engine]
  Q --> SB[Options Strategy Builder]
  Q --> EC[Edge Validation and Calibration]
  Q --> RE[Risk Engine]

  RE --> AP[Approval Gate]
  AP --> EX[Execution Engine]
  EX --> BR[Broker Adapter IBKR]
  EX --> RC[Reconciliation Service]

  DI --> EL[(Event Log)]
  DQ --> EL
  MC --> EL
  FE --> EL
  CX --> EL
  SE --> EL
  SB --> EL
  EC --> EL
  RE --> EL
  AP --> EL
  EX --> EL
  RC --> EL

  EL --> RM[(Read Models / Views)]
  RM --> UI
  EL --> AL[Alerts]
  AL --> UI

  EL --> RP[Backtest / Replay]
  RP --> EL

---

## End-to-End Workflow

sequenceDiagram
  participant S as Scheduler
  participant Q as Queue
  participant D as Data Ingestion
  participant QG as Data Quality Gate
  participant M as Market Cache
  participant F as Feature Engine
  participant X as Context Engine
  participant G as Signal Engine
  participant SBE as Options Strategy Builder
  participant V as Edge Validation
  participant R as Risk Engine
  participant P as Approval Gate
  participant E as Execution Engine
  participant B as Broker
  participant C as Reconciliation
  participant DB as Event Log
  participant API as FastAPI Orchestrator
  participant U as Trader UI
  participant UIX as Universe UI

  UIX->>API: upload universe JSON
  API->>DB: UniverseUploaded
  API->>DB: UniverseActivated
  S->>Q: schedule cycles for active universe
  S->>Q: enqueue cycle jobs (active universe)
  Q->>D: ingest market/options/news
  D->>QG: validate freshness, completeness, licensing flags
  QG->>DB: DataHealthEvaluated
  alt Data is acceptable
    QG->>M: write normalized snapshot
    M->>DB: MarketSnapshot
  else Data is stale/bad
    QG->>DB: TradingHaltEvent (data quality)
  end
  Q->>F: compute features
  F->>DB: FeatureSnapshot
  Q->>X: compute context (events/sentiment/fundamentals/analyst)
  X->>DB: NewsSnapshot + CorporateActionSnapshot + AnalystSnapshot (optional)
  Q->>G: detect setups and select strategy sleeve
  G->>DB: CandidateSignal
  Q->>SBE: build options structure (legs + pricing sanity)
  SBE->>DB: StrategyStructureProposed
  SBE->>R: pre-trade risk request

  alt Risk approved
    R->>P: create ApprovalRequest
    P->>U: render checklist and rationale
    alt Human approves
      P->>DB: ApprovalDecision(approved)
      P->>E: create OrderIntent
      E->>DB: OrderIntentCreated
      E->>B: submit (idempotency key)
      B-->>E: ack/reject/partial/fill
      E->>DB: BrokerOrderEvent + FillEvent
      Q->>C: enqueue reconcile job
      C->>B: fetch broker truth
      C->>DB: ReconcileSnapshot
    else Human rejects
      P->>DB: ApprovalDecision(rejected)
    end
  else Risk rejected
    R->>DB: RiskDecision(rejected)
  end

---

## Module Contracts

### Data Ingestion

Inputs:
- source adapters (IBKR for execution-context pricing + options chain + portfolio truth)
- research/context adapters (Yahoo Finance for earnings calendar and basic fundamentals where available)

Outputs:
- raw pulls + normalized snapshots (market, options chain, news)
- data-health metadata (freshness, latency, gaps, and licensing flags)

Rules:
- timezone/calendar normalization
- ingestion never directly enables signals; it only produces inputs and health signals
- delayed/stale quotes must be flagged and routed to the Data Quality Gate for block/degrade decisions
- corporate actions and adjustment policy must be explicit and versioned (split/dividend handling)
- Ingestion scope is the active universe projection; tickers not in the active universe are not polled unless explicitly requested by a UI query.

### Data Quality Gate

Inputs:
- raw pulls, normalized snapshots, and data-health metadata

Outputs:
- allow/degrade/block decisions for downstream computation and explicit `DataHealthEvaluated` events

Rules:
- enforce market calendar and timezone normalization before any downstream compute
- enforce staleness thresholds per data type (quotes, bars, options chain, news)
- enforce completeness thresholds (required fields and minimum liquidity metadata)
- tag all snapshots with `is_delayed`, `source`, `source_ts`, and `ingest_ts`
- if quality is insufficient, emit `TradingHaltEvent` scoped to affected tickers or sleeves

### Market Data Cache and Snapshot Store

Inputs:
- quality-approved normalized snapshots

Outputs:
- latest snapshot views for compute, plus immutable snapshot references written to the event log

Rules:
- cache must be rate-limit aware and de-duplicate identical pulls
- every downstream job reads through the cache to avoid inconsistent point-in-time data
- snapshots must support replay by timestamp for backtests and post-incident investigations

### Feature Engine

Inputs:
- latest quality-approved snapshots from the Market Cache

Outputs:
- deterministic features keyed by `ticker + ts + feature_version`

Rules:
- deterministic computation
- explicit feature versioning

### Context Engine

Inputs:
- quality-approved snapshots from the Market Cache

Outputs:
- context snapshots used for scoring and strategy filters

Rules:
- compute event proximity (earnings, dividends, major scheduled events)
- earnings calendar source: Yahoo Finance (best-effort; missing/uncertain dates must downgrade confidence)
- news source: IBKR news providers (headline + metadata; article text if entitled)
- sentiment: run OpenAI sentiment extraction on IBKR headlines/articles and store results in `NewsSnapshot`
- compute corporate action inputs and store as `CorporateActionSnapshot`
- context is non-authoritative; it can only increase/decrease confidence or apply strategy filters

### Strategy and Signal Engine

Inputs:
- feature vectors + regime + context snapshots (events, sentiment, fundamentals, analyst signals)

Outputs:
- candidate setup + selected strategy sleeve + confidence score and decomposition

Rules:
- must include thesis, entry zone, invalidation, target, hold period
- must include the exact snapshot references used (quote/bar/options snapshot ids)
- must include a determinism key so the same inputs reproduce the same candidate
- must choose a strategy sleeve from the approved catalog and justify why that sleeve fits (IV, event proximity, liquidity)
- must emit a `StrategySleeveSelected` rationale in the candidate payload (simple fields, no narrative walls)

### Options Strategy Builder

Inputs:
- candidate signal with selected strategy sleeve
- latest options chain snapshot (by reference)
- pricing inputs (underlying bid/ask/last, option bid/ask/mid)

Outputs:
- `StrategyStructureProposed` with concrete legs and pricing sanity checks

Rules:
- build defined-risk structures first; do not propose naked long calls when IV is high or event risk is near
- enforce liquidity checks per leg (spread, volume, open interest) and for the full structure
- enforce pricing sanity: debit cannot exceed max payoff, and credit structures must have bounded loss
- propose expiry aligned to hold period (default 14-35 DTE) and avoid pin-risk windows by policy
- output must include a structure label, legs, max loss, max gain, breakeven, and the snapshot refs used

### Edge Validation and Calibration

Inputs:
- `PositionClosed` events (primary realized outcome source), execution-quality events, and optional `PortfolioValuationSnapshot` events

Outputs:
- calibration updates, regime labels, sleeve enable/disable flags

Rules:
- weekly calibration against realized outcomes
- emit `TradingHaltEvent` when post-cost expectancy degrades beyond threshold

### Risk Engine

Inputs:
- proposed strategy structure + candidate signal + portfolio state + risk config

Outputs:
- approve/reject + reasons + budget impact

Hard rules:
- drawdown ladder: `-8%`, `-12%`, `-15%`
- per ticker <= `8%`, per sector <= `20%`
- no-trade on stale/bad data or liquidity failures
- enforce `beta_to_spy` cap (absolute beta exposure below configured threshold)
- enforce `net_delta` cap for option-heavy portfolios
- enforce cluster exposure caps for top factor clusters
- risk approval must compute `expected_total_cost_usd` and `expected_edge_after_cost_usd`
- `RiskDecision must be computed without assuming any future human override.`
- `If `expected_edge_after_cost_usd <= 0`, or cost inputs are missing, or input data health is not OK, RiskDecision must return `status=override_required` (not approved) with explicit rule codes and numeric values.`
- `If `worst_case_stress_loss_usd` exceeds configured NAV thresholds, RiskDecision must return `status=override_required` unless the rule is configured as non-overrideable.`
- `ApprovalDecision may record an override only for rule codes explicitly marked overrideable in risk config, and must include a typed override reason.`
- `Execution Gate must require either (a) RiskDecision.status=approved, or (b) RiskDecision.status=override_required AND ApprovalDecision.override=true, and then a final risk re-check is executed with the override flag applied before creating OrderIntent.`

Outputs (minimum):
- `RiskDecision.status: approved | rejected | override_required`
- `RiskDecision.rule_reasons: list of {rule_code, message, observed_value, threshold_value}`
- `RiskDecision.overrideable_rule_codes: list`

### Approval Gate

Inputs:
- risk-approved candidate

Outputs:
- `ApprovalDecision` (approved/rejected + reason)

Rules:
- no execution without explicit human decision
- checklist must be complete before approved

### Execution Engine

Inputs:
- approved order intent

Outputs:
- order lifecycle events, fill events, execution metrics

Rules:
- idempotent submit/replace/cancel
- bounded price-chase policy
- circuit breakers (max orders/day, max cancels/min, kill switch)
- record state `SENT` only after broker submit call returns successfully (before ACK is acceptable)
- all broker requests must be logged with request/response metadata (redacted as needed) for forensic replay
- submit must be guarded by `command_lock` using `order_intent_id`-derived idempotency key
- no new option positions within configured `N` trading days of expiry unless strategy explicitly allows it
- flag ex-dividend windows for ITM call assignment risk
- warn or block pin-risk setups near expiry based on policy

### Reconciliation Service

Inputs:
- broker order/position/cash truth

Outputs:
- reconcile snapshots + mismatch alarms

Rules:
- broker is source-of-truth on mismatch
- persistent mismatch blocks new entries
- reconciliation must run on reconnect and periodically during market hours
- if mismatches persist longer than configured `Z` minutes, system enters `no new entries` mode automatically

---

## Data Source Policy

Execution-context sources (authoritative for orders/positions/cash/pricing):
- IBKR (only)

Research/context sources (non-authoritative, used for confidence components only):
- Yahoo Finance (earnings calendar; basic fundamentals where available)
- IBKR News (headlines/articles subject to entitlements)
- OpenAI (sentiment extraction over captured headlines/articles)

Policy:
- all tradeable pricing and options legs must be validated using IBKR-sourced bid/ask (never vendor approximations)
- always persist `source`, `source_ts`, and `ingest_ts` and whether the feed is delayed
- always treat corporate actions and adjusted price policy as versioned inputs
- if Yahoo earnings dates are missing or inconsistent, the system must downgrade confidence and enforce the earnings danger window conservatively
- never rely on research sources for execution truth (fills, positions, cash)

Fallback:
- if IBKR market data is unavailable for required inputs, block new entries for affected tickers
- if IBKR news is unavailable, continue without sentiment (do not block) but downgrade confidence for event-driven sleeves

---

## Strategy Catalog and Low-Risk Defaults

The objective is to generate repeatable profits from call-focused setups while controlling downside. Strategies are selected based on liquidity, implied volatility, and event proximity.

Approved low-risk call-focused strategies (default top 3):

1. Bull Call Spread (debit call spread)
   - Use when trend is up and IV is not cheap enough to justify naked calls.
   - Defined max loss (debit paid) and controlled exposure around earnings.

2. Call Diagonal (poor-man's covered call)
   - Use when the underlying is strong but short-dated IV is elevated.
   - Long a deeper-in-the-money call with longer expiry, short a nearer-term call to reduce cost.

3. Call Calendar (time spread)
   - Use when a move is expected later but near-term volatility is overpriced.
   - Buy longer-dated call, sell near-dated call; requires clean liquidity and defined management rules.

Strategy selection filters (hard):
- do not recommend illiquid contracts (wide spreads, low OI, thin volume)
- avoid entering new long-premium positions inside the configured earnings danger window unless the sleeve explicitly allows it
- prefer defined-risk structures when IV rank is elevated or news risk is active

Strategy selection filters (soft):
- favor names with strong earnings momentum proxies and improving fundamentals signals where available (best-effort)
- favor sectors with relative strength and avoid weak regimes (risk-off) unless strategy is explicitly calibrated for it

---

## Observability and Operations

Required telemetry:
- structured logs with correlation ids per cycle and per order intent
- metrics: ingest latency, staleness, queue lag, signal throughput, approval latency, fill latency, reconcile mismatch rate
- tracing across API, workers, broker adapter, and reconciliation

Alerts (actionable only):
- stale/blocked data for watched tickers
- reconcile mismatches
- repeated broker rejects
- expectancy breach and TradingHaltEvent emission

Runbooks:
- reconnect and reconcile procedure
- data provider outage procedure
- kill switch procedure

---

## Read Models for UI

Minimum read views:
- `vw_portfolio_state`
- `vw_open_orders`
- `vw_recommendations`
- `vw_risk_status`
- `vw_reconcile_mismatches`
- `vw_daily_metrics`
- `vw_execution_quality`
- `vw_trading_halts`
- `vw_strategy_structures`
- `vw_strategy_catalog`
- `vw_context_snapshots`
- `vw_strategy_health`
- `vw_trade_review_queue`
- `vw_universe_active`
- `vw_universe_versions`
- `vw_ticker_data_health`
- `vw_watchlist_opportunities`
- `vw_order_blotter`
- `vw_strategy_health` must be segmented by `regime_label` and `trading_mode`

Minimum field contracts (Codex must implement)

vw_watchlist_opportunities (one row per ticker):
- ticker
- state (NoSignal, CandidateSignal, StructureProposed, RiskApproved, AwaitingApproval, OrderIntent, Executed, Reconciled, PositionOpen, PositionClosed, Reviewed)
- data_health (OK, Degraded, Blocked) + data_health_reason
- regime_label
- confidence_total + confidence_components (setup_quality, regime_fit, liquidity, event_risk, data_quality_multiplier, cost_adjustment)
- post_cost_edge_usd + post_cost_edge_pct_of_debit
- entry_zone, invalidation, target, hold_period
- earnings_warning (boolean) + earnings_date (nullable) + earnings_certainty (high/medium/low/unknown)
- last_snapshot_ts (most recent input snapshot timestamp used)
- next_action (view_trade_card, build_structure, run_risk, request_approval, manage_position, blocked)

Trade Card response model (GET /api/tickers/{ticker}/trade-card):
- ticker, state, last_price, snapshot_timestamps
- thesis (setup_name, entry_zone, invalidation, target, hold_period)
- why_now_deltas (list of short strings)
- confidence_total + confidence_components
- warnings (earnings danger, liquidity, data, DTE)
- structure_summary (nullable; bull call spread legs summary, debit, max_loss, max_gain, breakeven)
- risk_summary (nullable; approved/rejected, expected_total_cost_usd, expected_edge_after_cost_usd, worst_case_stress_loss_usd, rule_reasons)
- approval_status (nullable; pending/approved/rejected/override with reason)
- position_summary (nullable; pnl, DTE, exit_triggers)
- recent_events (bounded list; CandidateSignal, StrategyStructureProposed, RiskDecision, ApprovalDecision, FillEvent, ReconcileSnapshot)

vw_order_blotter (one row per order_intent_id):
- order_intent_id, ticker, structure_label, legs_summary
- created_ts, submitted_ts, last_update_ts
- broker_order_ids
- status + status_timeline
- fills (per-leg)
- fees_usd, slippage_vs_expected_usd
- broker_reject_reason (nullable)

Positions response model (GET /api/positions):
- account_id, positions (list)
- per position: ticker, strategy_label (if known), qty, avg_price, last_price, pnl_daily, pnl_total, dte (nullable), breakeven (nullable)
- per position: alerts (list; invalidation_breached, exit_rule_triggered, earnings_danger, dte_threshold, data_degraded, reconcile_block)

---

## Performance Circuit Breakers

- if a sleeve's rolling 20-trade expectancy after costs turns negative, emit `TradingHaltEvent` for that sleeve
- if `slippage_vs_expected_usd` exceeds threshold for `Y` consecutive fills, emit `TradingHaltEvent` for execution scope
- if reconciliation mismatches persist longer than `Z` minutes, halt new entries until cleared

---

## Operational Modes

- `paper`: no live broker execution
- `micro_live`: reduced sizing and stricter caps
- `normal_live`: enabled only after readiness thresholds
- all risk limit and trading mode changes must be emitted as config events (`RiskConfigChanged`, `TradingModeChanged`)
- runtime config is applied from the latest config projection derived from event log (append-only governance)

---

## Backtest and Replay

Goals:
- reproduce any recommendation and decision using the event log as the single source of inputs and outcomes
- validate feature and signal determinism across versions

Rules:
- replay uses the same pipeline code paths as live, driven by timestamped snapshots
- backtest outputs are written as events (separate `mode=backtest`) so they can be compared to live
- any strategy change must be versioned and evaluated against prior regimes before enabling in live sleeves

---

## Deployment Path

Phase 1 (local):
- FastAPI + Next.js (TypeScript) + queue worker + DuckDB/Postgres (choose one as primary early)

Phase 2 (low-cost AWS):
- EC2 t4g small/medium + Docker compose + EBS + S3 backups

Phase 3 (scale):
- ECS + managed Postgres

---

## Implementation Milestones

1. Event log schema, queue tables, and data quality events
2. Broker adapter interface and mock implementation
3. Data Quality Gate + Market Cache + snapshot replay
4. Ingestion and feature pipelines
5. Signal + risk + approval flow
6. Execution state machine and reconcile loop
7. UI read models and dashboards


## Concrete Stack (Implemented Starter)

Backend:
- Python 3.12
- FastAPI (API and service orchestration)
- Pydantic models for API contracts

Frontend:
- Next.js 14
- React 18
- TypeScript (strict)

Storage/eventing target:
- event log + read models in Postgres/DuckDB (next step)

Current code layout:
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/config.py`
- `backend/app/db.py`
- `backend/app/services/event_store.py`
- `backend/app/services/ibkr_gateway.py`
- `frontend/app/*`
- `frontend/lib/api.ts`

## Current Implementation Snapshot (As Built)

Implemented backend behavior (FastAPI):
- append-only local event log stored in SQLite (`backend/stock_tiger.db`)
- read models served from event projections:
  - `/api/recommendations`
  - `/api/risk-status`
  - `/api/events`
  - `/api/strategy-health`
  - `/api/trade-review-queue`
- write endpoints:
  - `/api/events/candidate-signal`
  - `/api/events/candidate-signal/bulk`
  - `/api/events/risk-decision`
  - `/api/events/approval-request`
  - `/api/events/approval-decision`
  - `/api/events/trading-halt`
  - `/api/events/position-closed`

IBKR integration (currently implemented):
- Stock Tiger acts as a thin wrapper over IBKR Client Portal Gateway REST APIs
- gateway base URL is configurable via `ibkr_gateway_base_url` (defaults in config)
- proxy/read endpoints:
  - `/api/ibkr/health` (tickle + auth + accounts)
  - `/api/ibkr/accounts`
  - `/api/ibkr/secdef/search`
  - `/api/ibkr/marketdata/snapshot`
  - `/api/ibkr/portfolio/{account_id}/positions/{page_id}`
  - `/api/ibkr/orders`

Auto-generation flow implemented (v1 rules engine):
- `/api/signals/generate-from-ibkr` fetches IBKR `secdef` + market snapshot and optionally headlines
- ranks by simple deterministic heuristics (quote quality + optional keyword-based news tone)
- writes top `N` generated `CandidateSignal` events
- does not yet implement full options-legs optimization or expiry selection

Frontend behavior (Next.js):
- Ideas page reads `/api/recommendations`
- table currently displays projection fields: `Ticker`, `Sleeve`, `Confidence`, `Regime`, `Quote`, `Post-Cost Edge`, `Entry`, `Invalidation`
- UI includes explicit error and empty-state messaging if recommendations fail or none exist

Universe import (planned UI → API)

- UI uploads a JSON universe file and calls a backend endpoint to validate tickers via IBKR secdef before activation.
- Universe events are stored in the same append-only event log and projected into `vw_universe_active` for cycles.

Known gap vs target architecture:
- data quality gate, feature engine, context engine, and options strategy builder are documented targets, not fully implemented runtime modules yet
- no continuous stream/live push; recommendations are event snapshots generated at request time and then persisted
- AI sentiment is not required in current implementation; news scoring is rules-based only

## UI Options and Workflow (Current App)

Navigation tabs available in UI:
- `Ideas` (`/`) - recommendation list from `GET /api/recommendations`
- `Risk` (`/risk`) - current risk posture from `GET /api/risk-status`
- `Events` (`/events`) - recent event timeline from `GET /api/events`
- `Strategy Health` (`/strategy-health`) - sleeve/regime performance rollups from `GET /api/strategy-health`
- `Trade Review` (`/trade-review`) - review queue and exceptions from `GET /api/trade-review-queue`

Ideas view options (what user can interpret today):
- `Ticker`: underlying symbol for candidate signal
- `Sleeve`: selected strategy family (currently `options_defined_risk` in most generated signals)
- `Confidence`: rule-based score (`0-100`) from generator or manually supplied value
- `Regime`: coarse label such as `trend_low_vol` or `chop`
- `Quote`: quote quality type (`real_time`, `delayed`, `snapshot`)
- `Post-Cost Edge`: estimated edge after transaction-cost assumptions
- `Entry` and `Invalidation`: suggested entry zone and thesis break level

Target end-to-end operator workflow (UI to be built):
0. Upload universe JSON (Top 20 S&P or custom list) and activate it
1. Verify broker connectivity (`/api/ibkr/health`, `/api/ibkr/accounts`)
2. Run idea generation for the active universe (`/api/signals/generate-from-ibkr`)
3. Open `Ideas` to view a watchlist-style opportunity list (actionable candidates first)
4. Drill into a ticker Trade Card to review thesis, entry/invalidation, and confidence decomposition
5. Build a bull call spread structure (expiry/strikes) and run pricing sanity + liquidity checks
6. Review `Risk` for pre-trade approval decision (post-cost edge, budget impact, stress loss)
7. Record `ApprovalDecision` (approved/rejected/override with reason)
8. Track fills and state transitions in a Blotter view (planned) and verify `Reconciliation`
9. Close positions and complete post-trade review in `Trade Review` to calibrate confidence

Current UI limitations (important):
- no direct order placement UI yet
- no full bull-call strategy builder UI (strike/expiry optimization not yet exposed)
- no real-time streaming updates; user refreshes data views
- No universe upload/activation UI yet (planned: JSON import + validation + versioning).
- No broker-style Trade Card view yet (planned: thesis, why-now deltas, confidence component breakdown).
- No Strategy Builder UI yet for bull call spreads (planned: strike/expiry controls, payoff, max loss/gain, breakeven, liquidity).
- No Blotter/Reconcile UI yet (planned: order timeline, per-leg fills, mismatch gating).

Repo hygiene (Codex cleanup):
- Remove frontend build artifacts from source control (for example .next/) and add them to .gitignore.
- Remove OS and interpreter artifacts from source control (for example .DS_Store, __pycache__/).
- Do not commit the local SQLite database file; create it on first run or store it outside the repo.

## Broker-Style UI Workflow (Target)

The UI behaves like a broker decision console: it surfaces only what is actionable, explains the recommendation, enforces risk gates, and records human decisions.

Primary screens:
- Universe: upload/activate JSON, view active universe and versions
- Watchlist: opportunity list with Data Health, Regime, Confidence, Post-Cost Edge, and State
- Trade Card: thesis, why-now deltas, entry zone, invalidation, target, hold period, confidence breakdown
- Strategy Builder: bull call spread legs, net debit, max loss/gain, breakeven, liquidity, realistic fill estimate
- Risk/Costs: expected_total_cost_usd, expected_edge_after_cost_usd, stress loss, exposure caps, approve/reject/override
- Blotter: order intent timeline, per-leg fills, slippage, fees
- Reconcile: mismatch center; blocks new entries until cleared
- Review: post-trade feedback and weekly confidence calibration buckets

State model for each ticker:
- NoSignal → CandidateSignal → StructureProposed → RiskApproved → AwaitingApproval → OrderIntent → Executed → PositionOpen → Reconciled → PositionClosed → Reviewed

Definition: Executed means the broker acknowledged fills; PositionOpen means the system sees an open position (from fills or broker positions); Reconciled means broker truth has been fetched and matched to internal state with no blocking mismatches.

UI rules:
- If data health is Blocked for a ticker, hide trade actions and show the blocking reason.
- Never show a single confidence number without its component breakdown and the post-cost edge.
- Any manual change to strikes/expiry must be recorded as a user override on the structure proposal.
- If reconciliation is mismatched, enforce no-new-entries mode in the UI.

## Trader Queries and Holding Watch (Target)

The UI must support fast broker-style querying and holding surveillance so the trader can react to market changes while positions are open.

Query types:
- Ticker query: show Trade Card, latest recommendation state, and last snapshot timestamps.
- Position query: show open positions, current PnL, days-to-expiry, and exit-rule triggers.
- Order query: show order intent timeline, fills, and broker rejects.
- Event query: show recent events for a ticker (CandidateSignal, StrategyStructureProposed, RiskDecision, ApprovalDecision, FillEvent, ReconcileSnapshot).

Holding watch rules (UI behavior):
- If invalidation is breached or a stop/exit rule triggers, show an actionable alert on the position row.
- If earnings is within the configured danger window for a held name, show an alert and the earnings date source/uncertainty.
- If DTE falls below the configured threshold, show pin-risk/assignment-risk warnings and block new additions unless the sleeve allows it.
- If data health degrades or becomes Blocked, freeze new trade actions but continue holding surveillance using last known broker truth.

Exit-rule triggers (minimum set):
- Invalidation breached (underlying below invalidation level).
- Target reached (underlying at/above target).
- Time stop (hold_period exceeded).
- DTE threshold warning (below configured days-to-expiry).
- Earnings danger window reached while holding (policy decides warn vs force action).

Read models used:
- `vw_portfolio_state`, `vw_open_orders`, `vw_order_blotter`, `vw_recommendations`, `vw_ticker_data_health`, `vw_reconcile_mismatches`, `vw_trade_review_queue`.

Planned API endpoints (UI contracts):
- POST /api/universe/upload (multipart JSON file) → UniverseUploaded
- POST /api/universe/activate (universe_version_id) → UniverseActivated
- GET /api/universe/active
- GET /api/watchlist (active universe opportunities)
- GET /api/tickers/{ticker}/trade-card
- GET /api/blotter
- GET /api/reconcile/mismatches
- GET /api/positions

## Local Run (Starter)

Backend:
- `cd backend`
- `python3 -m venv .venv`
- `source .venv/bin/activate`
- `pip install -r requirements.txt`
- `uvicorn app.main:app --reload --port 8000`

Frontend:
- `cd frontend`
- `npm install`
- `npm run dev`


Open:
- dashboard: `http://localhost:3000`
- api health: `http://localhost:8000/health`

## Broker Web UI UX Design (Target)

### Design goals:
- Clarity over cleverness: every screen answers one question.
- Reduce decision fatigue: show only what matters; hide deep details behind explicit expanders.
- Trust building: always show why now, what breaks it, and costs.
- State-driven UI: ticker rows reflect the state machine, not a dashboard of unrelated metrics.
- Market-speed navigation: keyboard-first, fast search, and quick filters.

### Information architecture:
- Left navigation: Universe, Watchlist, Positions, Blotter, Reconcile, Review, Events (optional), Settings.
- Top bar: global search (ticker/order), account selector, trading mode badge (paper/micro_live/normal_live), global data health, global reconcile status.

### Screen design (target):

**1) Universe**
- Upload JSON file, preview tickers, validate via IBKR secdef, activate universe version.
- Show active universe card: universe_id, version, as_of, ticker count, last validated timestamp, validation status.
- Block activation if any ticker fails validation; show exact failures.

**2) Watchlist (primary home)**
- Filter bar: actionable only, blocked only, earnings risk, confidence range, post-cost edge minimum, regime filter.
- Rows per ticker must include: state badge, data health, regime, confidence + component breakdown (hover), post-cost edge, entry zone, invalidation, next action.
- Row colors are status-severity only: neutral by default; amber for warnings; red for blocked/mismatch; green for approved/live-state indicators.
- Row click opens Trade Card in a right-side drawer for fast navigation.

**3) Trade Card (ticker detail)**
- Header: ticker, last price, state, snapshot timestamps used.
- Thesis: setup name, entry zone, invalidation, target, hold period.
- Why now: short delta list since previous cycle.
- Confidence: total score plus explicit components; highlight post-cost edge.
- Warnings: earnings danger window with date + source certainty; liquidity/data warnings.
- Actions: build structure, run risk, request approval, reject/snooze with reason.

**4) Strategy Builder (Bull Call Spread)**
- Controlled inputs: expiry picker limited by policy; strike steppers; quantity.
- Legs table: buy/sell strikes with bid/ask/mid, OI, volume; show net debit using mid and realistic fill estimate.
- Payoff summary: max loss, max gain, breakeven, reward-to-risk; liquidity score; pricing sanity results.
- Any manual change to expiry/strikes sets an override flag that must be recorded in ApprovalDecision.

**5) Risk/Costs**
- Show Approved/Rejected with numeric rule reasons.
- Show: expected_total_cost_usd, expected_edge_after_cost_usd, worst_case_stress_loss_usd, exposure impacts.
- If expected_edge_after_cost_usd <= 0, label as negative edge after costs and require explicit override path.

**6) Approval**
- Checklist: earnings checked, liquidity acceptable, invalidation defined, exit plan defined, costs acceptable, reconcile clean.
- Actions: approve, reject, override (typed reason required).

**7) Positions (holding surveillance)**
- Table: ticker, strategy, qty, DTE, PnL (daily/total), breakeven, exit triggers status, next action.
- Inline alerts: invalidation breached, earnings within danger window, DTE below threshold (pin risk), data degraded, reconcile mismatch.

**8) Blotter**
- Order intent timeline with per-leg fills, slippage vs expected, fees, broker rejects.

**9) Reconcile**
- Mismatch center with a clear no-new-entries banner when blocking=true.
- Show mismatch age, impacted tickers/orders, and last broker truth timestamp.

**10) Review (confidence calibration)**
- Closed trades queue with structured feedback tags (setup wrong, liquidity, earnings risk, regime mismatch).
- Weekly calibration: confidence buckets vs realized win rate and expectancy after costs.

### Visual style:
- Neutral base theme with high contrast typography and generous whitespace.
- Use a monospace font for prices/strikes/PnL/timestamps so numbers align.
- Avoid heavy shadows; use subtle borders; status color is reserved for severity states.

### MVP build order (UI):
- Universe upload + activate.
- Watchlist using vw_watchlist_opportunities.
- Trade Card drawer using GET /api/tickers/{ticker}/trade-card.
- Positions using GET /api/positions.
- Reconcile banner/list using GET /api/reconcile/mismatches.

## ETF Focus (Initial Universe and Strategy Notes)

ETFs are supported as first-class tickers in the universe and are treated the same as equities for monitoring, signals, structures, risk, approval, and holding surveillance.

Initial ETF set (option-liquidity focused, MVP):
- SPY, QQQ, IWM, DIA
- XLK, XLF, XLE, XLV, XLY, XLI, XLP, XLU
- SMH, SOXX
- TLT, HYG

ETF-specific notes:
- Prefer ETFs for regime and macro sleeves when single-name earnings risk is high.
- Liquidity thresholds (OI/volume/spread) must be stricter for weekly expiries; default to 14-35 DTE.
- Earnings danger window applies only to single-name equities; ETFs use event filters for macro releases instead.

Universe JSON can include ETFs alongside equities; validation uses IBKR secdef the same way.

## Codex Upgrade Plan (From Old Code to Target UI)

Objective: update the existing v0 codebase (recommendations list + manual event writes) into a universe-scoped broker console that supports watchlist, trade card drilldown, holding surveillance, and reconcile gating.

Backend changes (must implement):
- Add new events: UniverseUploaded, UniverseActivated, StrategyStructureProposed (bull call spread), ReconcileSnapshot (if not already persisted), OrderIntentCreated/BrokerOrderEvent/FillEvent as execution scope expands.
- Add new endpoints: POST /api/universe/upload, POST /api/universe/activate, GET /api/universe/active, GET /api/watchlist, GET /api/tickers/{ticker}/trade-card, GET /api/positions, GET /api/blotter, GET /api/reconcile/mismatches.
- Implement projections for: vw_universe_active, vw_universe_versions, vw_ticker_data_health, vw_watchlist_opportunities, vw_order_blotter, and trade-card projection.
- Update idea generation: default to the active universe projection; allow ad-hoc tickers only via explicit UI query path.
- Add holding surveillance: compute and surface position alerts from exit-rule triggers and data/reconcile state.

Frontend changes (must implement):
- Add pages: /universe, /watchlist (home), /positions, /blotter, /reconcile, /review.
- Watchlist row click opens Trade Card drawer (right-side) without losing list context.
- Add global reconcile-block banner; when blocking=true disable build/risk/approval actions.
- Add polling refresh model: watchlist 10-30s, positions 10-30s, blotter 2-5s when orders active, reconcile 10-30s.
- Enforce gating rules: data_health Blocked disables actions for that ticker; negative post-cost edge requires explicit override path with typed reason.

Codex constraints:
- Do not invent schemas. Add explicit Pydantic models for each endpoint and reuse them end-to-end.
- Keep event names and payload fields canonical per Event-Log-Schema.md.
- Implement the minimum field contracts in this document before adding UI cosmetics.
