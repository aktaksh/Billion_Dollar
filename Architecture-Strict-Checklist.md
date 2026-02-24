# Stock Tiger Strict Architecture Checklist

This checklist tracks implementation status against `Architecture.md`.

Legend:
- `[x]` Implemented in codebase
- `[~]` Partial / scaffolding only
- `[ ]` Not yet implemented

## 1) Purpose / Design Principles / Scope

- `[x]` Decision-layer, human approval, audit/event-log oriented flow exists.
- `[x]` Universe-scoped workflow implemented (`/api/universe/*`, `/api/watchlist`).
- `[~]` Full "risk-first always blocks uncertain inputs" behavior is partial.

## 2) Universe Import (Ticker JSON)

- `[x]` `POST /api/universe/upload` multipart field `file`
- `[x]` IBKR secdef validation with hard-fail on ambiguity
- `[x]` `UniverseUploaded` event persisted
- `[x]` `POST /api/universe/activate` + `UniverseActivated`
- `[x]` `GET /api/universe/active`
- `[x]` `GET /api/universe/versions`

## 3) High-Level Layers and Module Contracts

### Data Ingestion
- `[~]` IBKR read adapter and generation flow exist.
- `[ ]` Dedicated ingestion scheduler/worker pipeline for active universe.

### Data Quality Gate
- `[~]` `DataHealthEvaluated` event write endpoint exists.
- `[ ]` Automatic staleness/completeness enforcement pipeline.

### Market Cache / Snapshot Store
- `[ ]` No dedicated cache de-dup/rate-limit replay store yet.

### Feature Engine
- `[ ]` No deterministic feature compute module pipeline.

### Context Engine
- `[ ]` No full earnings/news/fundamental context engine with OpenAI sentiment extraction.

### Strategy and Signal Engine
- `[~]` CandidateSignal generation exists with deterministic key.
- `[ ]` Full strategy sleeve rationale and broad catalog selection logic.

### Options Strategy Builder
- `[~]` `StrategyStructureProposed` event writer added.
- `[ ]` Real structure optimization using options chain and policy constraints.

### Edge Validation and Calibration
- `[ ]` No weekly calibration job / sleeve auto-enable-disable yet.

### Risk Engine
- `[~]` `RiskDecision.status` supports `override_required`.
- `[~]` Order intent gate enforces risk+approval dependencies.
- `[~]` `rule_reasons` and `overrideable_rule_codes` now persist; full hard-rule matrix is still incomplete.

### Approval Gate
- `[x]` Approval endpoints and override reason path exist.
- `[~]` Checklist key enforcement exists; full policy completeness is still partial.

### Execution Engine
- `[x]` `OrderIntentCreated` event endpoint and idempotency key.
- `[~]` Broker lifecycle writers (`BrokerRequestResponseRecorded`, `BrokerOrderEvent`, `FillEvent`) and state-transition checks exist; chase policy/cancel-rate controls remain pending.

### Reconciliation Service
- `[~]` `ReconcileSnapshot`/`MismatchDetected` writers and mismatch read model.
- `[ ]` Automated periodic reconcile/reconnect flow and persistence policy.

## 4) Data Source Policy

- `[~]` IBKR is used for execution-context API paths.
- `[ ]` Full fallback policy automation and confidence downgrade rules for source outages.

## 5) Strategy Catalog and Low-Risk Defaults

- `[ ]` Catalog for bull call/diagonal/calendar is not yet implemented as enforceable selection engine.

## 6) Observability and Operations

- `[ ]` No full metrics/tracing/alerting/runbook automation in code.

## 7) Read Models for UI (Minimum contracts)

- `[x]` `vw_universe_active` equivalent (`/api/universe/active`)
- `[x]` `vw_universe_versions` equivalent (`/api/universe/versions`)
- `[x]` `vw_watchlist_opportunities` equivalent (`/api/watchlist`)
- `[x]` trade card endpoint (`/api/tickers/{ticker}/trade-card`)
- `[x]` positions endpoint (`/api/positions`)
- `[x]` blotter endpoint (`/api/blotter`)
- `[x]` reconcile mismatch endpoint (`/api/reconcile/mismatches`)
- `[~]` Some fields are placeholders (`last_price`, complete `position_summary`, richer warnings).

## 8) Performance Circuit Breakers

- `[~]` Manual evaluation endpoint emits halts for expectancy and stale reconcile mismatch; continuous scheduled automation and slippage sequence checks remain pending.

## 9) Operational Modes

- `[~]` Trading mode exists in payloads.
- `[~]` Config change events (`RiskConfigChanged`, `TradingModeChanged`) can now be written; runtime projection application is still pending.

## 10) Backtest and Replay

- `[ ]` Replay/backtest pipeline not implemented.

## 11) Deployment Path

- `[ ]` Infra phases are documentation only (no ECS/compose deployment scaffolding in repo).

## 12) UI Workflow / UX Target

- `[x]` Added target navigation and pages: `Universe`, `Watchlist`, `Positions`, `Blotter`, `Reconcile`, `Review`.
- `[x]` Added ticker Trade Card page.
- `[x]` Added global status/reconcile-block indicator in top layout.
- `[~]` No right-side drawer trade-card UX yet (currently dedicated route).
- `[~]` No strategy builder UI yet.
- `[~]` No advanced filter bar / keyboard-first UX yet.

## 13) Codex Upgrade Plan (must-implement list)

- `[x]` Universe events/endpoints implemented
- `[x]` Active-universe default for idea generation
- `[x]` Watchlist/trade-card/positions/blotter/reconcile pages + endpoints
- `[~]` Holding alerts partially implemented (DTE/data/reconcile/invalidation checks from available payloads)
- `[~]` Execution lifecycle event writers now added; parity validation/replay checks remain pending.

---

## Next Strict Milestones

1. Implement full `RiskDecision.rule_reasons` and overrideable-rule behavior.
2. Implement execution lifecycle writers (`BrokerOrderEvent`, `FillEvent`, `BrokerRequestResponseRecorded`) with state-machine validation.
3. Build strategy builder backend logic + UI (`StrategyStructureProposed` real chain calculations).
4. Add periodic reconcile worker and auto halt-on-persistent-mismatch.
5. Add advanced watchlist filters and Trade Card drawer UX parity.
