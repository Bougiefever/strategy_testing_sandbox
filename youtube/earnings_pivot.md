# Episodic Pivot: Earnings Opening Range Breakout Strategy

## Executive Summary

**Episodic Pivot** is a systematic intraday breakout strategy that capitalizes on momentum following earnings announcements. The strategy identifies high-probability setups using fundamental earnings data (EPS surprise, revenue surprise, earnings gap) combined with technical filters (100-day SMA trend strength), then enters on opening range breakouts with sophisticated multi-layered risk management.

**Core Edge**: The strategy exploits the tendency for stocks with strong positive earnings surprises to continue trending in the direction of the initial gap, while managing risk through tight initial stops and adaptive position sizing.

---

## Table of Contents

1. [Strategy Philosophy](#strategy-philosophy)
2. [Pre-Market Stock Selection](#pre-market-stock-selection)
3. [Entry Mechanics](#entry-mechanics)
4. [Position Sizing](#position-sizing)
5. [Exit Strategy](#exit-strategy)
6. [Risk Management](#risk-management)
7. [Complete Trade Lifecycle](#complete-trade-lifecycle)
8. [Live Trading Implementation](#live-trading-implementation)
9. [Performance Expectations](#performance-expectations)
10. [Key Considerations](#key-considerations)

---

## Strategy Philosophy

### Why Earnings Events?

Earnings announcements create **episodic volatility** - discrete events that reset market expectations and often trigger sustained directional moves. The strategy targets stocks where:

1. **Fundamental surprise is significant** (large EPS/revenue beats)
2. **Market reaction is immediate** (gap up/down ≥10%)
3. **Underlying trend is healthy** (100-day SMA not declining severely)
4. **Liquidity confirms conviction** (high relative volume)

### The "Episodic Pivot" Concept

An **episodic pivot** occurs when an earnings event causes a stock to "pivot" from its prior trading range into a new directional trend. The strategy aims to:
- **Identify** these pivots using quantitative filters
- **Enter** on confirmation of the new trend (ORB breakout)
- **Manage** the trade with adaptive exits that capture the move while protecting capital

---

## Pre-Market Stock Selection

The strategy screens for stocks **BEFORE market open** (9:25 AM ET) on the day after an earnings announcement. Only stocks that pass ALL filters are eligible for trading.

### Timing Filter: Earnings Window

**Eligible Earnings Times:**
- **Today Pre-Market** (before 9:30 AM ET)
- **Yesterday After-Market** (after 4:00 PM ET)

**Why This Window?**
- Allows the market to digest earnings overnight
- Ensures gap is established before market open
- Filters out mid-day or stale earnings events

**Example:**
- ✅ AAPL reports Wednesday 4:30 PM → Trade Thursday
- ✅ NVDA reports Thursday 7:00 AM → Trade Thursday
- ❌ TSLA reports Wednesday 2:00 PM → Skip (intraday, not after-hours)

---

### Long Side Filters (ALL must be true)

The strategy uses a **funnel approach**: start with earnings events, then progressively filter for high-probability setups.

#### Filter 1: 100-Day SMA Rate of Change (Trend Strength)

**Metric**: `ROC_100D_SMA`

**Calculation**:
```
ROC_100D_SMA = ((Current 100-day SMA - 100-day SMA from 100 days ago) / 100-day SMA from 100 days ago) × 100
```

**Filter Requirement (Long)**:
```
ROC_100D_SMA >= -10%
```

**What This Means**:
- The stock's 100-day moving average cannot be declining more than 10%
- Ensures we're not buying into a deteriorating long-term trend
- Allows for mild downtrends (up to -10%) as long as earnings are strong

**Example**:
- Stock's 100-day SMA was $50 three months ago, now it's $47
- ROC = (($47 - $50) / $50) × 100 = -6%
- ✅ **PASS** (-6% is >= -10%)

**Rationale**: Even strong earnings can fail to reverse a broken long-term trend. This filter avoids "catching falling knives."

---

#### Filter 2: Earnings Gap (Market Reaction Magnitude)

**Metric**: `Earnings_Gap_Pct`

**Calculation**:
```
Earnings_Gap_Pct = ((Pre-Market Price - Previous Close) / Previous Close) × 100
```

**Filter Requirement (Long)**:
```
Earnings_Gap_Pct >= 10%
```

**What This Means**:
- Stock must gap up at least 10% on earnings
- This is the **primary event filter** - we need a significant market reaction
- Gaps under 10% lack sufficient momentum potential

**Example**:
- Stock closed at $100 yesterday
- Pre-market (9:25 AM) price is $112
- Gap = (($112 - $100) / $100) × 100 = 12%
- ✅ **PASS** (12% >= 10%)

**Rationale**: Large gaps indicate strong institutional interest and often precede multi-day trends. Small gaps (<10%) tend to fade.

---

#### Filters 3 & 4: Earnings Surprises (Fundamental Quality)

**Metrics**:
- `Earnings_Surprise_Pct` (EPS surprise)
- `Revenue_Surprise_Pct` (revenue surprise)

**Calculation**:
```
Earnings_Surprise_Pct = ((Actual EPS - Estimated EPS) / |Estimated EPS|) × 100
Revenue_Surprise_Pct = ((Actual Revenue - Estimated Revenue) / Estimated Revenue) × 100
```

**Filter Requirement (Long)** - Complex Nested Logic:
```
((Earnings_Surprise_Pct >= 100%) OR (Revenue_Surprise_Pct >= 20%))
OR
((Earnings_Surprise_Pct >= 50%) AND (Revenue_Surprise_Pct >= 5%))
```

**Breaking This Down**:

The filter accepts stocks that meet **EITHER** of these conditions:

**Condition A**: Massive single surprise
- EPS surprise ≥ 100% (earnings doubled expectations), **OR**
- Revenue surprise ≥ 20% (revenue beat by 20%+)

**Condition B**: Strong dual surprise
- EPS surprise ≥ 50% (earnings beat by 50%+), **AND**
- Revenue surprise ≥ 5% (revenue beat by 5%+)

**Examples**:

| EPS Surprise | Revenue Surprise | Result | Reason |
|--------------|------------------|--------|--------|
| 120% | 2% | ✅ **PASS** | Condition A: EPS >= 100% |
| 40% | 25% | ✅ **PASS** | Condition A: Revenue >= 20% |
| 60% | 8% | ✅ **PASS** | Condition B: EPS >= 50% AND Rev >= 5% |
| 80% | 3% | ❌ **FAIL** | Neither condition met |
| 40% | 15% | ❌ **FAIL** | Neither condition met |

**Rationale**: We want either a **massive single beat** (one metric dominates) or a **strong balanced beat** (both metrics solid). This filters out marginal earnings beats that lack conviction.

---

#### Filter 5: Volume Confirmation (Filters Out Fake Moves)

**Metric**: First 5-minute bar volume vs. 30-day Average Daily Volume

**Calculation**:
```
Volume_Ratio = (First 5-min bar volume) / (30-day ADV × 0.10)
```

**Filter Requirement**:
```
First 5-min bar volume >= 10% of 30-day ADV
```

**What This Means**:
- The first 5 minutes of trading must show significant volume
- If a stock's average daily volume is 10M shares, the first 5 minutes must have at least 1.0M shares
- Filters out low-conviction moves that lack follow-through

**Example**:
- Stock's 30-day average daily volume: 8,000,000 shares
- First 5-min bar volume: 1,000,000 shares
- Required volume: 8,000,000 × 0.10 = 800,000 shares
- ✅ **PASS** (1.0M >= 800K)

**Rationale**: High opening volume confirms genuine market interest and filters out fake moves. Low volume gaps often lack conviction and reverse quickly, indicating the move wasn't real.

---

### Short Side Filters (ALL must be true)

The short side uses more conservative filters due to the structural headwinds of shorting (uptick rule, hard-to-borrow, etc.).

#### Complete Short Filter Logic:

```
ROC_100D_SMA <= 0%  (not a stock with strong momentum prior to earnings)
AND
Earnings_Gap_Pct <= -5%  (gap down at least 5%)
AND
Earnings_Surprise_Pct <= -20%  (massive EPS miss)
AND
Revenue_Surprise_Pct <= -5%  (revenue miss)
```

**Key Differences from Long Side**:
- **Smaller gap requirement**: -5% vs +10% (shorts are harder to execute)
- **Requires BOTH EPS and Revenue misses**: More conservative, no "OR" logic
- **Larger EPS miss required**: -20% vs the long side's 50%/100% flexibility

**Rationale**: Shorting is riskier due to unlimited upside risk, so we demand higher conviction (both metrics must miss, not just one).

---

## Entry Mechanics

### Entry Timing

**Entry Day**: First trading day AFTER earnings announcement

**Entry Type**: Intraday breakout (NOT market-on-open)

**Why Not Enter at the Open?**
- Opening prices are often erratic and subject to manipulation
- ORB (Opening Range Breakout) confirms the trend is continuing
- Avoids "gap and trap" scenarios where the gap fades immediately

---

### Primary Entry: 5-Minute Opening Range Breakout (ORB)

**Step 1: Define the Opening Range (9:30-9:35 AM ET)**

**For LONG Positions**:
- ORB Level = **High** of first 5-minute bar
- Initial Stop = **Low** of first 5-minute bar

**For SHORT Positions**:
- ORB Level = **Low** of first 5-minute bar
- Initial Stop = **High** of first 5-minute bar

**Step 2: Wait for Breakout**

Monitor price starting at 9:35 AM (when first bar closes).

**For LONG Positions**:
- Enter when price breaks **ABOVE** the 5-min high
- Entry price: ORB high + 0.25% slippage (simulates market order execution)

**For SHORT Positions**:
- Enter when price breaks **BELOW** the 5-min low
- Entry price: ORB low - 0.25% slippage

**Step 3: Place Stop-Loss Order**

Immediately upon entry, place a DAY stop-loss order:
- **Long**: Stop at the low of the first 5-minute bar
- **Short**: Stop at the high of the first 5-minute bar

**Example (Long Entry)**:
```
9:30-9:35 AM: First 5-min bar
  - High: $105.50
  - Low: $104.20

9:42 AM: Price breaks above $105.50
  - Enter LONG at $105.76 (105.50 × 1.0025 for slippage)
  - Place stop-loss at $104.20
  - Risk per share: $105.76 - $104.20 = $1.56
```

---

### Secondary Entry: 60-Minute ORB Re-Entry (After Stop-Out)

If the initial 5-minute ORB entry gets stopped out, the strategy allows **ONE re-entry** using a wider 60-minute opening range.

**Eligibility**: Only if stopped out on the primary entry (not applicable if you were never entered)

**Step 1: Calculate 60-Minute ORB (9:30-10:30 AM ET)**

At 10:30 AM, calculate the high/low of the first 60 minutes (twelve 5-minute bars).

**For LONG Positions**:
- 60-min ORB Level = **Highest high** of all bars from 9:30-10:30
- New Stop = **Lowest low** of all bars from 9:30-10:30

**For SHORT Positions**:
- 60-min ORB Level = **Lowest low** of all bars from 9:30-10:30
- New Stop = **Highest high** of all bars from 9:30-10:30

**Step 2: Wait for Breakout**

Monitor price throughout the day (up to 3:55 PM).

**For LONG Positions**:
- Enter when price breaks **ABOVE** the 60-min high
- Entry price: 60-min high + 0.25% slippage

**For SHORT Positions**:
- Enter when price breaks **BELOW** the 60-min low
- Entry price: 60-min low - 0.25% slippage

**Step 3: Place New Stop-Loss**

Upon re-entry, place new DAY stop-loss:
- **Long**: Stop at the 60-min low
- **Short**: Stop at the 60-min high

**Re-Entry Rules**:
- ✅ Only ONE re-entry allowed per stock per day
- ✅ Re-entry only after initial stop-out (not if limit order never filled)
- ❌ If stopped out TWICE in same day, no further entries
- ❌ If 60-min ORB doesn't break by 3:55 PM, cancel and move on

**Example (Long Re-Entry)**:
```
First Entry:
  9:42 AM: Entered at $105.76, stopped out at $104.20

60-Min ORB Calculation (10:30 AM):
  - High of 9:30-10:30: $106.80
  - Low of 9:30-10:30: $103.50

11:15 AM: Price breaks above $106.80
  - Re-enter LONG at $107.07 (106.80 × 1.0025)
  - Place new stop at $103.50
  - New risk per share: $107.07 - $103.50 = $3.57
```

---

## Position Sizing

### Risk-Based Position Sizing (1% Portfolio Risk)

Every trade risks **exactly 1% of portfolio value**, regardless of stop distance.

**Formula**:
```
Shares = (Portfolio Value × 0.01) / (Entry Price - Stop Loss)
```

**For SHORT positions**:
```
Shares = (Portfolio Value × 0.01) / (Stop Loss - Entry Price)
```

**Example**:
```
Portfolio Value: $100,000
Entry Price: $105.76 (long)
Stop Loss: $104.20
Risk Per Share: $105.76 - $104.20 = $1.56

Shares = ($100,000 × 0.01) / $1.56
Shares = $1,000 / $1.56
Shares = 641 shares

Position Size = 641 × $105.76 = $67,792
Risk Amount = 641 × $1.56 = $1,000 (exactly 1% of portfolio)
```

**Key Points**:
- Wider stops = fewer shares (less capital at risk)
- Tighter stops = more shares (more capital at risk)
- Risk amount is ALWAYS $1,000 (1% of $100K portfolio)
- This normalizes risk across all trades regardless of volatility

---

### Maximum Position Risk Cap (2% of Account)

While entries are sized to 1% risk, **price movements can expand risk**. To prevent oversized exposure, the strategy enforces a **2% maximum account risk cap**.

**Risk Calculation**:
```
Account Risk % = (Position Value / Portfolio Value) × (Stop Distance / Current Price)
```

Where:
- **Position Value** = Current shares × Current price
- **Stop Distance** = |Current price - Current stop|

**Example**:
```
Portfolio: $100,000
Position: 641 shares of AAPL at $115 (position value = $73,715)
Current Stop: $110
Stop Distance: $115 - $110 = $5

Account Risk = ($73,715 / $100,000) × ($5 / $115)
Account Risk = 0.737 × 0.0435
Account Risk = 3.2%

This EXCEEDS 2% cap → Position must be trimmed
```

**Trimming Logic**:

If account risk > 2%, automatically trim the position:

```
Target Risk Amount = Portfolio × 0.02
Target Shares = Target Risk Amount / Stop Distance

Shares to Trim = Current Shares - Target Shares
```

**Continuing Example**:
```
Target Risk Amount = $100,000 × 0.02 = $2,000
Target Shares = $2,000 / $5 = 400 shares

Current Shares: 641
Target Shares: 400
Trim: 641 - 400 = 241 shares

Action: Sell 241 shares at market
Remaining: 400 shares
New Account Risk: ($46,000 / $100,000) × ($5 / $115) = 2.0% ✅
```

**When This Happens**:
- Daily at 3:30 PM (Trade Manager checks all positions)
- Automatically trims back to 2% if exceeded
- Recorded as partial exit in trade history

---

## Exit Strategy

The exit strategy uses a **multi-layered approach** that adapts based on how long you've held the position and how it's performing.

---

### Exit Layer 1: Intraday Stop-Loss (Entry Day Only)

**Active**: Only on the day you enter the trade

**Mechanism**:
- **Long**: DAY stop-loss order at the low of the opening range bar
- **Short**: DAY stop-loss order at the high of the opening range bar
- Order automatically cancels at market close (4:00 PM)

**Purpose**:
- Protects against immediate reversals
- Limits loss to 1% of portfolio (by design of position sizing)
- If stopped out, allows for 60-min re-entry attempt

**Important**: This stop does NOT trail intraday. It's fixed at the opening range low/high.

---

### Exit Layer 2: Multi-Day SMA Trailing Stops

Starting on **Day 2** (first day after entry), the strategy uses **dual SMA stops**:
- **10-Day SMA**: Tighter stop, triggers partial exit
- **20-Day SMA**: Wider stop, triggers full exit

**SMA Calculation Timing**:
- SMAs are calculated using **yesterday's close** (not today's intraday price)
- Checked daily at **3:30 PM ET** by the Trade Manager
- Uses **Polygon API** for historical data

---

#### 10-Day SMA Stop → Exit 50% of Position

**Trigger**:
- **Long**: Current price (at 3:30 PM) < 10-day SMA
- **Short**: Current price (at 3:30 PM) > 10-day SMA

**Action**:
1. Exit **50%** of current shares at market
2. Mark `ten_day_stop_triggered = True`
3. **Switch to 20-day SMA** for remaining position

**Example**:
```
Position: 600 shares AAPL long at $110 entry
Day 5:
  - Current price: $118
  - 10-day SMA: $119.50
  - 20-day SMA: $117.00

  Price ($118) < 10-day SMA ($119.50)

  Action: Exit 300 shares at $118
  Remaining: 300 shares
  New stop: 20-day SMA ($117.00)
```

**After 10-Day Stop Triggers**:
- Position now uses **ONLY** the 20-day SMA
- 10-day SMA is no longer monitored
- Remaining shares held until 20-day SMA breaches

---

#### 20-Day SMA Stop → Exit 100% of Position

**Trigger**:
- **Long**: Current price (at 3:30 PM) < 20-day SMA
- **Short**: Current price (at 3:30 PM) > 20-day SMA

**Action**:
1. Exit **100%** of current shares at market
2. Close the position completely
3. Record final P&L

**Example**:
```
Position: 300 shares AAPL long at $110 entry (after 10-day stop exit)
Day 12:
  - Current price: $116
  - 20-day SMA: $116.50

  Price ($116) < 20-day SMA ($116.50)

  Action: Exit all 300 shares at $116
  Position CLOSED
```

**Why Two SMAs?**
- **10-day**: Captures quick profit on partial position
- **20-day**: Lets winners run longer on remaining position
- Balances taking profits vs. riding trends

---

### Exit Layer 3: Early Partial Exit (Two Consecutive Red/Green Days)

**Trigger**: Two consecutive down days (longs) or up days (shorts)

**Calculation** (checked daily at 3:30 PM):

**For LONG Positions** (Two Red Days):
```
IF (2-days-ago close > Yesterday close > Current price)
  THEN Exit 1/3 of position
```

**For SHORT Positions** (Two Green Days):
```
IF (2-days-ago close < Yesterday close < Current price)
  THEN Exit 1/3 of position
```

**Action**:
1. Exit **1/3** of current shares at market
2. Move stop to **breakeven** (entry price) if it tightens risk
3. Mark `early_exit_done = True` (only happens once per trade)

**Breakeven Stop Logic**:

The stop only moves to breakeven if it **improves** the risk profile:

**For LONG**:
```
IF (entry_price > current_stop):
  Move stop to entry_price
ELSE:
  Keep stop at current SMA level
```

**For SHORT**:
```
IF (entry_price < current_stop):
  Move stop to entry_price
ELSE:
  Keep stop at current SMA level
```

**Example (Long)**:
```
Entry: $110
Current shares: 600
Current stop: $108 (10-day SMA)
Entry price: $110

Day 7 (3:30 PM check):
  - 2 days ago close: $120
  - Yesterday close: $118
  - Current price: $117

  Pattern: $120 > $118 > $117 ✅ Two red days

  Action: Exit 200 shares (1/3 of 600) at $117
  Remaining: 400 shares

  Breakeven check:
    Entry price ($110) > Current stop ($108)?
    YES → Move stop to $110 (locks in profit)

  New stop: $110 (breakeven)
```

**Rationale**:
- Two consecutive down days often signal a short-term reversal
- Taking 1/3 off reduces exposure while keeping majority position
- Breakeven stop ensures remaining position is risk-free

---

### Exit Priority Order

When multiple exit conditions trigger simultaneously, the order of priority is:

**Priority 1**: 20-day SMA stop (FULL EXIT)
- If this triggers, exit immediately, skip all other checks

**Priority 2**: 10-day SMA stop (HALF EXIT)
- Only checked if 10-day stop hasn't already been triggered

**Priority 3**: Two consecutive red/green days (1/3 EXIT)
- Only checked if early exit hasn't already been done

**Priority 4**: 2% risk cap trim (PARTIAL TRIM)
- Always checked, regardless of other exits

---
