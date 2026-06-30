

# Billion Dollar — Market Risk & Crash Detection Enhancement

## Goal

Build a **Market Risk Engine** for Billion Dollar so the app can detect market-wide risk-off conditions before recommending options trades.

The engine must answer these questions before any trade recommendation is shown:

1. Is the current market regime bullish, cautious, choppy, risk-off, crash-warning, or panic?
2. Are naked long calls allowed today?
3. Are bullish spreads allowed today?
4. Should the app prefer bearish strategies such as put debit spreads or bear call spreads?
5. Are existing positions still safe to hold, reduce, roll, or close?
6. Why is a long call losing while a bull spread is profitable?

The final output must be clean and useful for a trader, not raw technical garbage.

---

## Why This Enhancement Is Needed

The app currently evaluates stocks and options mostly from the perspective of individual ticker movement.

That is not enough.

A stock can look technically strong, but if QQQ, SPY, SMH, VIX, mega-cap breadth, and macro catalysts are all flashing risk-off, then bullish calls should be blocked or heavily reduced.

The engine must act as a **strategy gatekeeper** before option recommendations are generated.

Example:

```text
Market Regime: RISK_OFF
Crash Risk Score: 74/100
AMD Relative Strength: Positive
Long Calls: BLOCKED
Allowed Strategy: Small call debit spread only if AMD holds VWAP
Preferred Strategies: Bear call spread, put debit spread after failed bounce
Reason: QQQ below VWAP, VIX rising, breadth weak, tech sector selling
```

---

## Core Concept

Every options recommendation must be filtered through this order:

```text
Market Data Collection
        ↓
Feature Calculation
        ↓
Crash Risk Score
        ↓
Market Regime Classification
        ↓
Strategy Permission Check
        ↓
Position Risk Review
        ↓
Trade Card / Dashboard Output
```

The app must never directly recommend calls, puts, or spreads without first checking market regime.

---

## New Module Structure

Create this module structure:

```text
app/
  market_risk/
    __init__.py
    schemas.py
    collectors.py
    features.py
    crash_score.py
    regime.py
    strategy_gatekeeper.py
    position_risk.py
    news_catalyst.py
    macro_calendar.py
    service.py
    explanations.py
    storage.py
    README.md
```

If the project has a different root structure, adapt paths but keep the same module boundaries.

---

## Required Market Instruments

The engine must track these instruments at minimum:

```text
SPY  - S&P 500 ETF
QQQ  - Nasdaq 100 ETF
IWM  - Russell 2000 ETF
DIA  - Dow Jones ETF
SMH  - Semiconductor ETF
XLK  - Technology ETF
VIX  - Volatility index or VIX proxy
TNX  - 10-year yield proxy, if available
DXY  - Dollar index proxy, if available
```

If VIX, TNX, or DXY are unavailable through IBKR, design the collector with an external adapter interface.

Do not hard-fail if one optional symbol is unavailable. Instead, mark it as missing and reduce confidence.

---

## Market Regime Enum

Create the following enum in `app/market_risk/regime.py`:

```python
from enum import Enum


class MarketRegime(str, Enum):
    BULL_TREND = "BULL_TREND"
    BULL_CAUTIOUS = "BULL_CAUTIOUS"
    CHOPPY = "CHOPPY"
    RISK_OFF = "RISK_OFF"
    CRASH_WARNING = "CRASH_WARNING"
    PANIC = "PANIC"
```

Regime meaning:

| Regime | Meaning | Trading Behavior |
|---|---|---|
| BULL_TREND | Strong uptrend, low fear | Calls and bullish spreads allowed |
| BULL_CAUTIOUS | Uptrend but some warning signs | Prefer spreads over naked calls |
| CHOPPY | Mixed signals, poor directional edge | Avoid naked calls, allow defined-risk spreads |
| RISK_OFF | Broad market weakness | Block new bullish trades, prefer bearish spreads |
| CRASH_WARNING | Fast selloff / high fear | Defensive only, reduce bullish exposure |
| PANIC | Severe market stress | Block most new trades, focus on exits and hedges |

---

## Data Schemas

Create `app/market_risk/schemas.py`.

Add these dataclasses or Pydantic models depending on current project style.

Use Pydantic if the project already uses it. Otherwise use dataclasses.

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class InstrumentSnapshot:
    symbol: str
    captured_at: datetime
    last_price: Optional[float] = None
    previous_close: Optional[float] = None
    open_price: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None
    vwap: Optional[float] = None
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    change_pct: Optional[float] = None
    gap_pct: Optional[float] = None
    volume_ratio: Optional[float] = None
    source: str = "unknown"
    data_type: str = "unknown"  # live, delayed, frozen, external, derived
    missing_fields: List[str] = field(default_factory=list)


@dataclass
class MarketFeatures:
    captured_at: datetime
    index_trend_score: int
    volatility_score: int
    breadth_score: int
    macro_score: int
    news_score: int
    mega_cap_score: int
    reasons: List[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class MarketRegimeSnapshot:
    captured_at: datetime
    crash_score: int
    regime: str
    allowed_strategies: Dict[str, str]
    blocked_strategies: Dict[str, str]
    reasons: List[str]
    confidence: float


@dataclass
class OptionPositionSnapshot:
    symbol: str
    strategy_type: str
    underlying_price: float
    pnl_pct: Optional[float] = None
    short_strike: Optional[float] = None
    long_strike: Optional[float] = None
    breakeven: Optional[float] = None
    expiry: Optional[str] = None
    delta: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None
    quantity: int = 1


@dataclass
class PositionRiskResult:
    symbol: str
    strategy_type: str
    risk_status: str
    recommended_action: str
    reasons: List[str]
    distance_to_short_strike_pct: Optional[float] = None
```

Supported strategy types:

```text
LONG_CALL
LONG_PUT
CALL_DEBIT_SPREAD
PUT_DEBIT_SPREAD
BULL_PUT_SPREAD
BEAR_CALL_SPREAD
COVERED_CALL
CASH_SECURED_PUT
STOCK_LONG
STOCK_SHORT
UNKNOWN
```

---

## Feature Calculation Requirements

Create `app/market_risk/features.py`.

For each tracked instrument calculate:

```text
price_vs_vwap
price_vs_20ema
price_vs_50ema
intraday_change_pct
gap_pct
volume_ratio_vs_20d_average
previous_day_low_break
opening_range_breakdown
```

Implement utility functions:

```python
def pct_change(current: float, previous: float) -> float:
    if previous is None or previous == 0 or current is None:
        return 0.0
    return ((current - previous) / previous) * 100


def is_below(value: float | None, reference: float | None) -> bool:
    if value is None or reference is None:
        return False
    return value < reference


def clamp_score(score: float) -> int:
    return round(max(0, min(100, score)))
```

Add feature scoring functions:

```python
def calculate_index_trend_score(snapshots: dict[str, InstrumentSnapshot]) -> tuple[int, list[str]]:
    """Score market trend weakness from SPY, QQQ, IWM, DIA, SMH, and XLK."""


def calculate_volatility_score(snapshots: dict[str, InstrumentSnapshot]) -> tuple[int, list[str]]:
    """Score fear using VIX or a volatility proxy."""


def calculate_breadth_score(breadth_data: dict | None) -> tuple[int, list[str]]:
    """Score breadth weakness using advancers/decliners and percentage of stocks above VWAP/EMA."""


def calculate_macro_score(macro_events: list[dict] | None) -> tuple[int, list[str]]:
    """Score high-impact macro event risk."""


def calculate_news_score(news_items: list[dict] | None) -> tuple[int, list[str]]:
    """Score news shock risk from headlines."""


def calculate_mega_cap_score(snapshots: dict[str, InstrumentSnapshot]) -> tuple[int, list[str]]:
    """Score weakness in AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA if available."""
```

---

## Crash Score Formula

Create `app/market_risk/crash_score.py`.

Use weighted scoring:

```python
def calculate_crash_score(
    trend_score: int,
    volatility_score: int,
    breadth_score: int,
    macro_score: int,
    news_score: int,
    mega_cap_score: int,
) -> int:
    score = (
        trend_score * 0.25
        + volatility_score * 0.20
        + breadth_score * 0.20
        + macro_score * 0.10
        + news_score * 0.15
        + mega_cap_score * 0.10
    )
    return round(max(0, min(100, score)))
```

Weights:

| Component | Weight |
|---|---:|
| Index trend | 25% |
| VIX / volatility | 20% |
| Breadth | 20% |
| News | 15% |
| Macro | 10% |
| Mega-cap drag | 10% |

---

## Regime Classification

In `app/market_risk/regime.py`, add:

```python
def classify_market_regime(crash_score: int) -> MarketRegime:
    if crash_score < 25:
        return MarketRegime.BULL_TREND
    if crash_score < 45:
        return MarketRegime.BULL_CAUTIOUS
    if crash_score < 60:
        return MarketRegime.CHOPPY
    if crash_score < 75:
        return MarketRegime.RISK_OFF
    if crash_score < 90:
        return MarketRegime.CRASH_WARNING
    return MarketRegime.PANIC
```

---

## Strategy Gatekeeper

Create `app/market_risk/strategy_gatekeeper.py`.

This file must decide which strategies are allowed or blocked based on current market regime.

Implement:

```python
def strategy_permissions(regime: MarketRegime, crash_score: int) -> dict[str, str]:
    """
    Return strategy permission map.
    Values should be one of:
    - ALLOWED
    - CONDITIONAL
    - BLOCKED
    - REDUCED_SIZE_ONLY
    - HOLD_ONLY
    """
```

Required behavior:

```text
BULL_TREND:
- LONG_CALL = ALLOWED
- CALL_DEBIT_SPREAD = ALLOWED
- BULL_PUT_SPREAD = ALLOWED
- PUT_DEBIT_SPREAD = BLOCKED
- BEAR_CALL_SPREAD = BLOCKED

BULL_CAUTIOUS:
- LONG_CALL = CONDITIONAL
- CALL_DEBIT_SPREAD = ALLOWED
- BULL_PUT_SPREAD = ALLOWED
- PUT_DEBIT_SPREAD = BLOCKED
- BEAR_CALL_SPREAD = CONDITIONAL

CHOPPY:
- LONG_CALL = BLOCKED
- CALL_DEBIT_SPREAD = CONDITIONAL
- BULL_PUT_SPREAD = CONDITIONAL
- PUT_DEBIT_SPREAD = CONDITIONAL
- BEAR_CALL_SPREAD = CONDITIONAL

RISK_OFF:
- LONG_CALL = BLOCKED
- CALL_DEBIT_SPREAD = BLOCKED
- BULL_PUT_SPREAD = BLOCKED for new trades
- PUT_DEBIT_SPREAD = ALLOWED
- BEAR_CALL_SPREAD = ALLOWED

CRASH_WARNING:
- LONG_CALL = BLOCKED
- CALL_DEBIT_SPREAD = BLOCKED
- BULL_PUT_SPREAD = BLOCKED for new trades
- PUT_DEBIT_SPREAD = CONDITIONAL after failed bounce
- BEAR_CALL_SPREAD = ALLOWED
- All trades = REDUCED_SIZE_ONLY

PANIC:
- New trades = BLOCKED except defensive hedges
- Existing positions must be reviewed for close, reduce, or hedge
```

Add validation function:

```python
def validate_trade_against_market_regime(
    strategy_type: str,
    regime: MarketRegime,
    crash_score: int,
    has_relative_strength: bool = False,
    above_vwap: bool = False,
) -> dict:
    """Return whether trade is allowed and explain why."""
```

Required examples:

```text
If crash_score >= 55 and strategy_type == LONG_CALL:
- allowed = False
- reason = Risk-off/choppy regime blocks naked long calls.

If crash_score >= 70 and strategy_type == BULL_PUT_SPREAD:
- allowed = False for new trade
- reason = Crash risk too high for new bullish credit spread.

If strategy_type == CALL_DEBIT_SPREAD and regime == BULL_CAUTIOUS:
- allowed = True only if above_vwap and has_relative_strength are True.
```

---

## Position Risk Analyzer

Create `app/market_risk/position_risk.py`.

This is required because long calls and bull spreads behave differently.

Implement:

```python
def analyze_position_risk(
    position: OptionPositionSnapshot,
    regime: MarketRegime,
    crash_score: int,
    underlying_below_vwap: bool = False,
    underlying_below_ema20: bool = False,
) -> PositionRiskResult:
    """Analyze existing position and return action."""
```

### Long Call Logic

```text
If market regime is RISK_OFF, CRASH_WARNING, or PANIC:
- Do not add to long calls
- If PnL <= -30%, recommend REDUCE_OR_EXIT
- If underlying below VWAP and below EMA20, recommend EXIT_OR_HEDGE

If regime is CHOPPY:
- Recommend HOLD_ONLY or CONVERT_TO_SPREAD

If regime is BULL_TREND:
- Allow hold if underlying remains above VWAP and EMA20
```

### Bull Put Spread Logic

For bull put spreads, calculate distance from current price to short put strike:

```python
distance_to_short_put_pct = ((underlying_price - short_put_strike) / underlying_price) * 100
```

Rules:

```text
If distance > 5% and regime is not PANIC:
- risk_status = OK
- action = HOLD_WITH_ALERT

If distance <= 3%:
- risk_status = WARNING
- action = CLOSE_OR_ROLL

If underlying_price <= short_put_strike:
- risk_status = DANGER
- action = EXIT_OR_DEFEND

If regime is CRASH_WARNING and distance <= 5%:
- action = REDUCE_OR_CLOSE
```

### Call Debit Spread Logic

```text
If underlying below long call strike:
- risk_status = HIGH_RISK
- action = HOLD_ONLY_OR_EXIT

If underlying between long and short strikes:
- risk_status = ACTIVE
- action = HOLD_WITH_TARGET

If underlying above short strike:
- risk_status = PROFIT_ZONE
- action = TAKE_PROFIT_OR_HOLD_TO_PLAN
```

### Bear Call Spread Logic

```text
If underlying remains below short call strike:
- risk_status = OK
- action = HOLD_WITH_ALERT

If underlying approaches short call strike within 3%:
- risk_status = WARNING
- action = CLOSE_OR_ROLL

If underlying crosses short call strike:
- risk_status = DANGER
- action = EXIT_OR_DEFEND
```

---

## Explanation Engine

Create `app/market_risk/explanations.py`.

The goal is to produce human-readable explanations for dashboard and trade cards.

Implement:

```python
def explain_market_regime(snapshot: MarketRegimeSnapshot) -> str:
    """Return concise explanation of current market regime."""


def explain_strategy_permission(strategy_type: str, permission_result: dict) -> str:
    """Explain why a strategy is allowed, conditional, or blocked."""


def explain_position_risk(result: PositionRiskResult) -> str:
    """Explain why the position is safe, warning, or danger."""
```

Required explanation example for long call:

```text
Your long call is losing because the market regime is RISK_OFF, the underlying is below VWAP, and time decay is hurting the premium. Do not average down until the stock reclaims VWAP and the market regime improves.
```

Required explanation example for bull put spread:

```text
Your bull put spread is still profitable because the underlying remains far above the short put strike. Time decay is helping the credit spread. Keep alerts near the short strike and do not open new bullish credit spreads while crash risk remains high.
```

---

## News Catalyst Engine

Create `app/market_risk/news_catalyst.py`.

The engine must parse headlines and score risk.

Keyword weights:

```python
NEWS_KEYWORD_WEIGHTS = {
    "fed hike": 20,
    "inflation hotter": 20,
    "higher rates": 15,
    "hawkish fed": 20,
    "guidance cut": 25,
    "earnings warning": 25,
    "tariff": 15,
    "export restriction": 20,
    "ai spending concern": 20,
    "debt concern": 20,
    "war": 30,
    "oil spike": 15,
    "credit downgrade": 25,
    "default risk": 30,
    "bank stress": 25,
    "sec probe": 15,
    "doj probe": 15,
}
```

Implement:

```python
def score_news_headlines(headlines: list[str]) -> tuple[int, list[str]]:
    """Return news risk score and reasons."""
```

Rules:

```text
- Match keywords case-insensitively.
- Multiple matching headlines increase score.
- Cap final news score at 100.
- Return top reasons, not all noisy matches.
```

---

## Macro Calendar Engine

Create `app/market_risk/macro_calendar.py`.

Track high-impact events:

```python
HIGH_IMPACT_EVENTS = [
    "CPI",
    "PCE",
    "FOMC",
    "Nonfarm Payrolls",
    "Unemployment Rate",
    "Retail Sales",
    "PMI",
    "Fed Chair Speech",
    "Fed Speaker",
]
```

Implement:

```python
def score_macro_events(events: list[dict]) -> tuple[int, list[str]]:
    """Return macro risk score and human-readable reasons."""
```

Rules:

```text
If high-impact event is within next 24 hours:
- Add 20 risk points
- Mark recommendations as event-sensitive

If high-impact event is within next 4 hours:
- Add 35 risk points
- Block aggressive naked long options before release

If event has just released and market volatility is high:
- Add 25 risk points
```

---

## Collector Design

Create `app/market_risk/collectors.py`.

Collectors must be adapter-based.

Use this design:

```python
class MarketDataCollector:
    def collect_core_snapshots(self) -> dict[str, InstrumentSnapshot]:
        raise NotImplementedError


class IBKRMarketDataCollector(MarketDataCollector):
    def __init__(self, ibkr_client):
        self.ibkr_client = ibkr_client

    def collect_core_snapshots(self) -> dict[str, InstrumentSnapshot]:
        """Collect SPY, QQQ, IWM, DIA, SMH, XLK, VIX/TNX/DXY if available."""
        raise NotImplementedError


class ExternalMarketDataCollector(MarketDataCollector):
    def collect_core_snapshots(self) -> dict[str, InstrumentSnapshot]:
        """Fallback collector for VIX, yields, DXY, breadth, or macro data."""
        raise NotImplementedError
```

Important:

```text
- Do not fake unavailable data.
- Mark missing data explicitly.
- Every snapshot must include source and data_type.
- If data is delayed, dashboard must show delayed data warning.
```

---

## Storage Requirements

Create `app/market_risk/storage.py`.

Support writing these snapshots:

```text
market_snapshots
market_regime_snapshots
strategy_permissions
position_risk_snapshots
```

If the project already has an event store, integrate with it instead of creating a duplicate storage system.

Schema suggestion:

```sql
CREATE TABLE market_snapshots (
    id UUID PRIMARY KEY,
    captured_at TIMESTAMP NOT NULL,
    symbol TEXT NOT NULL,
    last_price NUMERIC,
    change_pct NUMERIC,
    vwap NUMERIC,
    ema_20 NUMERIC,
    ema_50 NUMERIC,
    volume NUMERIC,
    volume_ratio NUMERIC,
    source TEXT,
    data_type TEXT,
    missing_fields JSONB
);

CREATE TABLE market_regime_snapshots (
    id UUID PRIMARY KEY,
    captured_at TIMESTAMP NOT NULL,
    crash_score INT NOT NULL,
    regime TEXT NOT NULL,
    trend_score INT,
    volatility_score INT,
    breadth_score INT,
    news_score INT,
    macro_score INT,
    mega_cap_score INT,
    reason_json JSONB,
    confidence NUMERIC
);

CREATE TABLE strategy_permissions (
    id UUID PRIMARY KEY,
    captured_at TIMESTAMP NOT NULL,
    regime TEXT NOT NULL,
    crash_score INT NOT NULL,
    strategy TEXT NOT NULL,
    permission TEXT NOT NULL,
    reason TEXT
);

CREATE TABLE position_risk_snapshots (
    id UUID PRIMARY KEY,
    captured_at TIMESTAMP NOT NULL,
    symbol TEXT NOT NULL,
    strategy_type TEXT NOT NULL,
    pnl_pct NUMERIC,
    risk_status TEXT,
    recommended_action TEXT,
    distance_to_short_strike_pct NUMERIC,
    reason_json JSONB
);
```

---

## Service Orchestration

Create `app/market_risk/service.py`.

Implement:

```python
class MarketRiskService:
    def __init__(
        self,
        market_collector,
        news_provider=None,
        macro_provider=None,
        breadth_provider=None,
        storage=None,
    ):
        self.market_collector = market_collector
        self.news_provider = news_provider
        self.macro_provider = macro_provider
        self.breadth_provider = breadth_provider
        self.storage = storage

    def build_market_regime_snapshot(self) -> MarketRegimeSnapshot:
        """
        Collect data, calculate features, calculate crash score,
        classify regime, generate strategy permissions, and return snapshot.
        """

    def validate_new_trade(self, strategy_type: str, symbol: str, trade_context: dict) -> dict:
        """Validate new trade against current market regime."""

    def analyze_existing_positions(self, positions: list[OptionPositionSnapshot]) -> list[PositionRiskResult]:
        """Analyze all open positions against current market regime."""
```

Service flow:

```text
1. Collect core instrument snapshots
2. Collect breadth data if available
3. Collect macro events if available
4. Collect news if available
5. Calculate feature scores
6. Calculate crash score
7. Classify regime
8. Generate strategy permissions
9. Save snapshot
10. Return dashboard-ready result
```

---

## Dashboard Requirements

Add a Market Regime panel to the UI.

Panel must show:

```text
Market Regime
Crash Risk Score
Trend Score
Volatility Score
Breadth Score
News Score
Macro Score
Mega-cap Score
Allowed Strategies
Blocked Strategies
Top 3 Reasons
Data Quality / Missing Data Warning
```

Example output:

```text
BILLION DOLLAR MARKET REGIME

Status: RISK_OFF
Crash Risk Score: 74/100
Trend: Bearish
Volatility: Rising
Breadth: Weak
News Shock: AI spending concern + Fed rate pressure
Macro Risk: PMI/Fed event sensitive

Allowed:
✅ Bear call spreads
✅ Put debit spreads after failed bounce
⚠️ Existing bull put spreads only if far OTM

Blocked:
❌ New naked calls
❌ Aggressive call buying
❌ New bull put spreads

Reason:
QQQ is below VWAP and 20 EMA, SMH is weak, VIX is rising, and mega-cap tech is dragging the index.
```

---

## Trade Card Requirements

Every trade card must show market-regime compatibility.

For each recommended trade show:

```text
Strategy Permission: ALLOWED / CONDITIONAL / BLOCKED
Market Regime: RISK_OFF
Crash Score: 74/100
Reason: Long calls are blocked because QQQ is below VWAP and VIX is rising.
Alternative: Use bear call spread or wait for reclaim of VWAP.
```

For existing positions show:

```text
Position Risk: WARNING
Recommended Action: HOLD_WITH_ALERT
Reason: Underlying is still 7.2% above short put strike, so the bull put spread is not in danger yet. However, new bullish credit spreads are blocked because crash risk is high.
```

---

## Special Explanation Requirement

The app must explain this specific case clearly:

```text
Why are my long calls losing but my bull spread is profitable?
```

Required explanation logic:

```text
Long calls lose when the stock does not rise fast enough, because they are hurt by delta, theta decay, IV drop, and bid/ask spread.

Bull put spreads can remain profitable even when the market falls slightly, as long as the underlying stays far above the short put strike. The short put loses value over time, so theta helps the spread.

Call debit spreads can also lose less than naked calls because the short call offsets some premium decay and IV contraction.
```

Add this helper in `explanations.py`:

```python
def explain_long_call_vs_bull_spread() -> str:
    return (
        "Long calls need the stock to move up strongly and quickly. "
        "They can lose money from time decay, IV drop, and weak directional movement. "
        "A bull put spread can still be profitable if the stock remains far above the short put strike, "
        "because time decay helps the short option. A call debit spread can also lose less than a naked call "
        "because the short call offsets part of the premium decay."
    )
```

---

## Alert Rules

Add alert rules:

```text
Crash Risk Score >= 55:
- Warn: Choppy/risk-off conditions. Avoid naked long calls.

Crash Risk Score >= 70:
- Alert: Risk-off market. Block new bullish trades.

Crash Risk Score >= 85:
- Alert: Crash warning. Review all bullish positions.

VIX up > 10% intraday:
- Alert: Volatility shock.

QQQ below VWAP and below 20 EMA:
- Warning: Nasdaq trend weak.

SMH down > 2%:
- Warning: Semiconductor sector pressure.

More than 60% of watchlist red:
- Warning: Watchlist breadth weak.

Mega-cap drag high:
- Warning: Index downside may continue.
```

---

## Test Requirements

Add unit tests for:

```text
1. Crash score calculation
2. Regime classification
3. Strategy permission mapping
4. Long call risk logic
5. Bull put spread risk logic
6. Call debit spread risk logic
7. News keyword scoring
8. Macro event scoring
9. Explanation output
10. Missing data handling
```

Example tests:

```python
def test_crash_score_blocks_long_calls_when_score_above_55():
    result = validate_trade_against_market_regime(
        strategy_type="LONG_CALL",
        regime=MarketRegime.RISK_OFF,
        crash_score=65,
    )
    assert result["allowed"] is False
    assert "blocks naked long calls" in result["reason"].lower()


def test_bull_put_spread_hold_when_far_above_short_strike():
    position = OptionPositionSnapshot(
        symbol="QQQ",
        strategy_type="BULL_PUT_SPREAD",
        underlying_price=738,
        short_strike=678,
        long_strike=668,
        pnl_pct=10,
    )
    result = analyze_position_risk(
        position=position,
        regime=MarketRegime.RISK_OFF,
        crash_score=70,
    )
    assert result.recommended_action == "HOLD_WITH_ALERT"
    assert result.distance_to_short_strike_pct > 5
```

---

## Implementation Phases

### Phase 1 — Core Risk Engine

Deliver:

```text
schemas.py
regime.py
crash_score.py
strategy_gatekeeper.py
position_risk.py
explanations.py
unit tests
```

Do not integrate live IBKR yet.

Use mock snapshots and mock positions.

### Phase 2 — Market Data Integration

Deliver:

```text
collectors.py
IBKR collector adapter
fallback external collector interface
snapshot normalization
missing data handling
```

### Phase 3 — News & Macro Risk

Deliver:

```text
news_catalyst.py
macro_calendar.py
news scoring
macro event scoring
headline explanation
```

### Phase 4 — Dashboard & Trade Cards

Deliver:

```text
Market Regime panel
Strategy permission badges
Position risk cards
Crash alerts
Data quality warning
```

### Phase 5 — Recommendation Gatekeeper Integration

Deliver:

```text
Before any option recommendation, call MarketRiskService.validate_new_trade()
Block or downgrade strategy based on market regime
Show exact reason in trade card
```

---

## Acceptance Criteria

The implementation is complete only when:

```text
1. The app calculates crash score from 0 to 100.
2. The app classifies market regime correctly.
3. The app blocks naked calls when crash risk is high.
4. The app blocks new bull put spreads during crash-warning conditions.
5. The app allows bearish strategies in risk-off markets.
6. Existing bull put spreads are evaluated based on distance to short strike.
7. Existing long calls show reduce/exit warnings when market regime turns risk-off.
8. Every blocked trade has a clear human-readable explanation.
9. Dashboard shows Market Regime, Crash Score, Allowed Strategies, Blocked Strategies, and Reasons.
10. Unit tests cover core scoring and strategy gating logic.
```

---

## Cursor Implementation Instructions

Use these exact instructions in Cursor:

```text
Implement the Billion Dollar Market Risk & Crash Detection Enhancement described in this document.

Start with Phase 1 only unless existing project structure makes a small supporting change necessary.

Create the module app/market_risk/ with:
- __init__.py
- schemas.py
- regime.py
- crash_score.py
- strategy_gatekeeper.py
- position_risk.py
- explanations.py

Use existing project style where possible. If the project uses Pydantic models, use Pydantic. Otherwise use dataclasses.

Do not wire live IBKR or external APIs in Phase 1.

Implement pure functions first:
- calculate_crash_score
- classify_market_regime
- strategy_permissions
- validate_trade_against_market_regime
- analyze_position_risk
- explain_market_regime
- explain_strategy_permission
- explain_position_risk
- explain_long_call_vs_bull_spread

Add unit tests for all Phase 1 functions.

Ensure strategy gating behavior:
- crash_score >= 55 blocks LONG_CALL
- crash_score >= 70 blocks new BULL_PUT_SPREAD
- RISK_OFF allows PUT_DEBIT_SPREAD and BEAR_CALL_SPREAD
- CRASH_WARNING and PANIC block aggressive bullish trades
- BULL_CAUTIOUS allows CALL_DEBIT_SPREAD only when above VWAP and relative strength are true

Ensure position risk behavior:
- LONG_CALL in RISK_OFF with pnl <= -30 returns REDUCE_OR_EXIT
- LONG_CALL below VWAP and EMA20 returns EXIT_OR_HEDGE
- BULL_PUT_SPREAD more than 5% above short put returns HOLD_WITH_ALERT
- BULL_PUT_SPREAD within 3% of short put returns CLOSE_OR_ROLL
- BULL_PUT_SPREAD below short put returns EXIT_OR_DEFEND

Keep output clean, typed, and testable.

Do not add noisy UI or raw data tables in Phase 1.
Do not duplicate existing broker or event-store code.
Do not rename existing app modules unless required.
```

---

## Future Improvement Ideas

Later enhancements:

```text
1. Add real-time alert streaming from IBKR.
2. Add pre-market and post-market regime calculation.
3. Add earnings calendar risk.
4. Add options IV percentile and IV rank.
5. Add sector rotation detection.
6. Add watchlist breadth heatmap.
7. Add position-level stress test.
8. Add auto-comparison of app recommendation vs actual outcome.
9. Add paper-trading validation loop.
10. Add model-generated explanation only after deterministic rules produce the result.
```

Important principle:

```text
Rules first. LLM explanation second. Never let the LLM invent risk decisions.
```

---

## Final Product Behavior

The app should not say:

```text
AMD looks bullish. Buy calls.
```

It should say:

```text
Market Regime: RISK_OFF
Crash Risk Score: 74/100
AMD Relative Strength: Positive
Naked Long Calls: BLOCKED
Allowed Strategy: Small call debit spread only above VWAP
Preferred Strategy: Bear call spread or put debit spread after failed bounce
Reason: QQQ is below VWAP, VIX is rising, breadth is weak, and tech sector pressure is high.
```

That is the behavior required for Billion Dollar.