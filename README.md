# Billion Dollar

Billion Dollar is an **options decision-review workstation**.

It helps you review trade ideas, save decisions, run simulated paper trades, and later judge whether each decision was good, bad, or lucky.

It is **not** a live-trading robot.

## Index

1. [What This App Does](#what-this-app-does)
2. [Main Rule](#main-rule)
3. [Start the App](#start-the-app)
4. [Optional: Connect TWS Paper Data](#optional-connect-tws-paper-data)
5. [Daily Workflow](#daily-workflow)
6. [Pages Explained](#pages-explained)
7. [Important Terms](#important-terms)
8. [How to Know If It Is Improving](#how-to-know-if-it-is-improving)
9. [Troubleshooting](#troubleshooting)
10. [Developer Commands](#developer-commands)
11. [Reference Doc](#reference-doc)

## What This App Does

Most trading dashboards stop at: "Here is a signal."

Billion Dollar is meant to go further:

```text
candidate signal
-> ranked recommendation
-> saved decision
-> replay
-> paper trade
-> blotter
-> position
-> review
-> outcome
-> dashboard learning metrics
```

The app helps you answer:

- Why did this ticker appear?
- What exact trade structure is being reviewed?
- Did I save the recommendation as a decision?
- Did that decision become a paper trade?
- Did the trade follow the original plan?
- Was the decision correct, partially correct, wrong, or invalid?
- Which strategies are improving or failing over time?

## Main Rule

Use this app in this order:

```text
Read -> Save Decision -> Replay -> Paper -> Review -> Learn
```

Do **not** run normal paper trades without a saved `decision_id`.

The only exception is **Quick Paper Test**, which exists for developer testing.

Safety reminders:

- Do not use this as live trading automation.
- If risk says `reject`, do not paper trade it.
- If data or reconcile is blocked, pause new entries.
- Always read the Trade Card before saving or paper trading.

## Start the App

### Easy Start

From the project root:

```bash
cd /Users/ankeittaksh/Documents/git_codes/Billion_Dollar
chmod +x run_local.sh
./run_local.sh
```

Open:

```text
http://localhost:3000/dashboard
```

Backend health:

```text
http://localhost:8000/health
```

### Manual Backend Start

```bash
source /Users/ankeittaksh/Documents/git_codes/activate_pyenv.sh
cd /Users/ankeittaksh/Documents/git_codes/Billion_Dollar/backend
poetry run uvicorn app.main:app --reload --port 8000
```

Use Python `3.11`, `3.12`, or `3.13`. Avoid Python `3.14` for now.

### Manual Frontend Start

```bash
cd /Users/ankeittaksh/Documents/git_codes/Billion_Dollar/frontend
npm install
npm run dev
```

## Optional: Connect TWS Paper Data

The app can work without TWS. If TWS is closed, it should still run with mock or disconnected data.

To connect TWS paper data:

1. Open **Trader Workstation Paper** and log in.
2. Go to **Edit -> Global Configuration -> API -> Settings**.
3. Enable:
   - ActiveX and Socket Clients
   - Read-Only API
   - Socket port `7497`
   - Trusted IP `127.0.0.1`
4. In Billion Dollar, open **Settings**.
5. Click **Connect Broker**.

Or call:

```bash
curl -X POST "http://localhost:8000/api/ops/broker/connect?refresh_ingestion=true"
```

Check status:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/ops/broker/status
```

When connected, data status should move toward `live`. The app still does not place real broker orders.

## Daily Workflow

Follow this path when using the app:

1. Open **Dashboard**.
2. Check **Command Center**:
   - Is data healthy?
   - Is broker connected or safely disconnected?
   - Are new entries allowed?
3. Look at **Live Recommendations**.
4. Open the **Trade Card** for one ticker.
5. Read the reason, entry trigger, invalidation, max loss, max profit, and POP.
6. If the idea makes sense, click **Save Decision**.
7. Open **Decision Ledger** and confirm a `decision_id` exists.
8. Run **Replay**.
9. Run **Paper** only after the decision is saved.
10. Check **Blotter** for the paper order.
11. Check **Positions** for the open paper position.
12. When the position closes or expires, open **Review**.
13. Classify the outcome and write a short lesson.
14. Return to **Dashboard** to see learning metrics.

## Pages Explained

### Dashboard

Use Dashboard first.

It answers:

- Is the app healthy?
- What recommendations exist?
- Are past decisions improving?

Key sections:

- **Command Center**: data, broker, reconcile, and runtime safety.
- **Decision Quality**: total decisions, paper trades, win rate, average P/L, drawdown, best/worst strategy, engine accuracy.
- **Live Recommendations**: ranked recommendations with strategy, direction, confidence, edge, max loss, max profit, POP, risk, and decision status.
- **Strategy Health**: which strategies are performing better or worse.

Usual action order:

```text
Card -> Save -> Replay -> Paper
```

### Watchlist

Use Watchlist to scan ticker opportunities.

Look for:

- `Health`: is the data usable?
- `Confidence`: how strong is the setup?
- `Regime`: what market environment is assumed?
- `Suggested Strategy`: what structure is proposed?
- `Max Loss`: planned worst loss.
- `POP`: probability of profit.
- `Liquidity`: whether options are usable.
- `Entry`: what must happen before entry.
- `Invalidation`: what makes the idea wrong.
- `Review Status`: whether it needs review later.

Entry should never say only `auto`. It should show a real trigger or `not_ready`.

### Trade Card

Use the Trade Card before saving a decision.

It should explain:

- Why the trade exists.
- Market regime.
- Technical reason.
- Catalyst reason.
- Options liquidity reason.
- Risk reason.
- Entry trigger.
- Invalidation rule.
- Profit plan.
- Max loss and max profit.
- Probability of profit.
- Option legs.

Simple test:

```text
If I cannot explain this trade in one sentence, I should not save it.
```

### Strategy Builder

Use Strategy Builder to generate ranked option strategy candidates.

Steps:

1. Choose symbol and direction.
2. Set max loss and minimum POP.
3. Click **Run Runtime Flow**.
4. Review the ranked candidate table.
5. Select one candidate.
6. Read rule reasons.
7. Click **Save Decision**.
8. Confirm a `decision_id` is returned.

Rules:

- **Run Paper** stays disabled until a decision is saved.
- Candidates with `risk_status = reject` should not be paper traded.
- Replay can be run before paper trading.

### Decision Ledger

Use Decision Ledger when you want to know where every saved decision stands.

Important fields:

- `decision_id`: unique ID for the saved decision.
- `current_status`: lifecycle status.
- `review_status`: pending, ready for review, or reviewed.
- `final_outcome`: final judgment.
- `paper_pnl`: paper result.
- `max_drawdown`: worst movement against the trade.

If you feel lost, open Decision Ledger.

### Replay

Use Replay before Paper.

Replay asks:

```text
How might this strategy behave under different price scenarios?
```

Replay is a pre-check. It does not replace paper trading or review.

### Paper

Paper has two modes.

#### Decision-Based Paper Trade

This is the normal mode.

Use it only when:

- A saved `decision_id` exists.
- Risk is not rejected.
- New entries are allowed.

Steps:

1. Open **Paper**.
2. Select a saved decision.
3. Review the original trade plan.
4. Check max loss, max profit, and risk status.
5. Click **Run paper trade**.
6. Read the lifecycle events.

Expected lifecycle:

```text
OrderIntentCreated
PaperOrderCreated
FillEvent
PositionOpened
PositionClosed
```

#### Quick Paper Test

Quick Paper Test is for developer testing only. Do not use it as the normal workflow.

### Blotter

Use Blotter to inspect simulated order activity.

It answers:

```text
Did this saved decision create a paper order and fill?
```

Look for:

- `decision_id`
- symbol
- strategy
- direction
- order status
- fill price
- fees
- slippage
- review status

### Positions

Use Positions to monitor open paper trades.

It links each position back to the saved decision and original plan.

Look for:

- `decision_id`
- symbol
- strategy
- direction
- quantity
- average price
- current price
- P/L
- max drawdown
- DTE
- entry trigger
- invalidation rule
- profit plan
- current action

If no positions exist, the page should explain that you need to run a saved decision through Paper Trading.

### Review

Use Review after a paper trade closes or expires.

This is where the app learns.

Compare the original plan with the actual result:

- Was the entry trigger met?
- Was invalidation hit?
- Was profit target hit?
- Did the exit follow the plan?
- What was the P/L?
- What was the max drawdown?

Then classify the outcome:

- `correct`: plan worked and rules were followed.
- `partially_correct`: direction was right, but timing, risk, or exit was weak.
- `wrong`: rules were followed, but thesis failed.
- `invalid_entry`: entry happened before trigger.
- `invalid_exit`: exit ignored the plan.
- `skipped_trigger_not_met`: setup never triggered.

Always write a short lesson.

Example:

```text
Direction was right, but entry was early. Wait for VWAP hold next time.
```

### Explain Feed

Use Explain Feed to understand what the engine is doing.

It should show human-friendly messages, not only raw event names.

Example:

```text
AAPL feature snapshot updated. Confidence 73.8. Regime trend_low_vol. Candidate signal is active.
```

Useful filters:

- Global
- Ticker
- Decision
- Risk
- Broker
- Paper
- Review

### Reconcile

Use Reconcile to check whether app state matches broker state.

Clean state:

```text
No mismatches detected. App state matches TWS broker state.
```

If there is a blocking mismatch, do not open new paper trades until it is resolved.

### Settings

Use Settings to connect broker data and check runtime settings.

## Important Terms

| Term | Simple Meaning |
| --- | --- |
| Candidate Signal | A ticker the engine thinks may be interesting |
| Recommendation | A ranked trade idea with score, edge, risk, and plan |
| Decision | A recommendation you saved for tracking |
| `decision_id` | The ID linking recommendation, paper trade, position, and review |
| Replay | Scenario testing before paper trading |
| Paper Trade | Simulated trade, not real broker execution |
| Blotter | Log of paper orders and fills |
| Position | Open simulated trade |
| Review | Final judgment after the trade result |
| Outcome | Correct, partially correct, wrong, invalid, etc. |
| POP | Probability of profit |
| Max Loss | Worst planned loss |
| Max Profit | Best planned profit |
| Invalidation | Rule that says the trade idea is no longer valid |
| Drawdown | How much the trade went against you before the result |

## How to Know If It Is Improving

Use **Dashboard** and **Review** together.

Good signs:

- More saved decisions become reviewed outcomes.
- Win rate improves.
- Average paper P/L improves.
- Average max drawdown falls.
- Bad strategies are identified.
- Common reject reasons become clear.
- Lessons become specific and actionable.

Bad signs:

- Recommendations are not being saved as decisions.
- Paper trades are not linked to decisions.
- Reviews are skipped.
- Lessons are vague.
- The same strategy keeps losing without being downgraded.

## Troubleshooting

### Dashboard says disconnected

This is okay if TWS is closed. The app can still run with mock or disconnected data.

If you want TWS data, open TWS Paper, confirm API settings, then connect from Settings.

### Paper button is disabled

Usually one of these is true:

- No `decision_id` exists.
- Risk status is `reject`.
- Reconcile is blocking entries.
- The decision already has a linked paper trade.

Fix:

1. Save the candidate first.
2. Confirm it appears in Decision Ledger.
3. Confirm risk is not rejected.
4. Try Paper again.

### Review page is empty

No decisions are ready for review yet.

Normal path:

```text
Save Decision -> Run Paper -> Position closes/expires -> Review
```

### TWS is open but data is not live

Check:

- TWS Paper is logged in.
- API socket is enabled.
- Read-Only API is checked.
- Port is `7497`.
- Trusted IP includes `127.0.0.1`.
- Backend was restarted after changes.

## Developer Commands

Run backend tests:

```bash
cd /Users/ankeittaksh/Documents/git_codes/Billion_Dollar/backend
/Users/ankeittaksh/Documents/git_codes/pyenv_global/bin/python -m pytest tests/ -q
```

Build frontend:

```bash
cd /Users/ankeittaksh/Documents/git_codes/Billion_Dollar/frontend
/opt/homebrew/bin/npm run build
```

Useful backend endpoints:

- `GET /health`
- `GET /api/dashboard/summary`
- `GET /api/dashboard/recommendations`
- `GET /api/watchlist`
- `GET /api/tickers/{ticker}/trade-card`
- `POST /api/decisions/save`
- `GET /api/decisions`
- `GET /api/decisions/{decision_id}`
- `PATCH /api/decisions/{decision_id}`
- `POST /api/strategy-builder/runtime`
- `POST /api/replay/run`
- `POST /api/paper/run`
- `GET /api/blotter`
- `GET /api/positions`
- `GET /api/trade-review`
- `POST /api/trade-review/{decision_id}/classify`
- `POST /api/trade-review/{decision_id}/complete`
- `GET /api/explain-feed`

## Reference Doc

Architecture reference:

- `Billion-Dollar-Architecture-Reference.md`
