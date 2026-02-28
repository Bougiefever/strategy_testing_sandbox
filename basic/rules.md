Here is what I got when I asked you to start a new canvas from an existing canvas. Can we talk about this?

# IV Rich, Sell Defined Risk

## Goal

Build and validate a simple, rule-based options strategy that is:

* Easy to backtest with daily data
* Executable in liquid markets
* Robust to small modeling errors
* Focused on defined-risk premium selling

---

## Core Idea

When implied volatility (IV) is **rich** relative to realized volatility (RV) and/or its own history, sell **defined-risk** premium (credit spreads) with strict risk controls and mechanical exits.

---

## Universe

Choose one (start narrow, expand later):

* **Phase 1 (recommended):** ETFs/indices only (e.g., SPY, QQQ, IWM, DIA, XLF, XLK, XLE)
* **Phase 2:** Highly liquid single names (top option volume / tight spreads)

Liquidity filters (daily):

* 20-day avg option volume ≥ 10,000 contracts (or a threshold you trust)
* Median bid/ask spread (near target delta) ≤ a chosen max (optional)
* Underlying price ≥ $20 (optional)

Earnings filter:

* **Skip single names** with earnings between entry and expiration
* ETFs: ignore earnings filter

---

## Volatility Signals

Define at least one “IV rich” trigger.

### Option A: IV / RV ratio (simple)

* Compute **RV20**: 20-day realized volatility from daily returns
* Compute **IV30** (or closest) from options (ATM or 30D interpolated)
* Trigger when: **IV30 / RV20 ≥ X** (start with X = 1.25 or 1.5)

### Option B: IV Rank (robust)

* IVRank over lookback L (e.g., 252 trading days)
* Trigger when: **IVRank ≥ Y** (start with Y = 50 or 70)

### Option C: Term structure (optional later)

* Front IV higher than back IV (backwardation) as a “stress” regime marker

---

## Regime Filters

Use one simple regime filter to avoid selling premium into crash conditions.

### Trend filter (classic)

* Trade only if underlying **close > SMA200**

### Alternative: Drawdown filter

* Trade only if underlying is not in the bottom Z% of 1y returns

---

## Trade Structures

Start with **put credit spreads** (defined risk).

### Structure 1: Put Credit Spread (PCS)

* Target DTE: **30–45** (use nearest available)
* Short put delta: **~0.25 to 0.35**
* Long put delta: **~0.10 to 0.15**
* Width: fixed (e.g., $5 for ETFs) or delta-based

Entry pricing (conservative):

* Sell short leg at **bid**
* Buy long leg at **ask**
* Net credit must be > 0 and above a minimum (e.g., $0.25)

---

## Position Sizing

Define sizing on **max loss**.

* Max loss per spread: `(width - credit) * 100`
* Risk per trade: **0.5%–1.0%** of equity
* Portfolio cap: total max loss ≤ **20%–30%** of equity

---

## Exits (Mechanical)

Use one profit target and one risk stop.

### Profit target

* Close at **50% of credit** captured

### Time stop

* Close at **21 DTE** (or **10 DTE**) regardless of PnL

### Loss stop

Choose one:

* Close if spread value reaches **2.0×** entry credit (loss ≈ 1× credit)
* OR close if loss reaches **-1.5×** credit

Assignment/expiry management:

* Do not hold through expiration in backtests (close at EOD of exit rule day)

---

## Backtest Plan

### Phase 1: Edge discovery (fast)

* Universe: SPY/QQQ/IWM only
* Period: 2022–2024 (or any 2–3 year slice)
* Trades: 1 per symbol per day max
* Execution: bid/ask conservative fills
* Costs: commissions + slippage

Metrics:

* CAGR, Sharpe, Max DD
* Profit factor, expectancy per trade
* Win rate, avg win/loss
* Exposure (avg capital at risk)

### Phase 2: Robustness

* Walk-forward by year
* Sensitivity: deltas ±0.05, DTE ±7
* Stress test: widen spreads, increase slippage

---

## Implementation Notes

Data you need per quote date:

* Underlying close (and returns)
* Option chain with bid/ask, delta, expiration, strike
* An IV proxy (ATM or 30D interpolated)
* Earnings dates (for single names)

Key functions to build:

1. `realized_vol(prices, window=20)`
2. `iv_30d(term_structure_or_chain)`
3. `iv_rank(iv_series, lookback=252)`
4. `select_spread(chain, dte_range, short_delta_range, long_delta_range)`
5. `price_spread_bid_ask(short_leg, long_leg)`
6. `position_sizing(equity, risk_pct, width, credit)`
7. `exit_rules(position, quote_date)`

---

## Defaults to Start (editable)

* DTE: 30–45
* Signal: IV30/RV20 ≥ 1.5
* Trend filter: close > SMA200
* Short delta: 0.30
* Long delta: 0.15
* TP: 50% credit
* Time exit: 21 DTE
* Stop: 2.0× credit
* Risk per trade: 0.75%
* Portfolio cap: 25% max loss

---

## Next Steps

1. Pick universe (SPY/QQQ/IWM?)
2. Choose IV signal (ratio vs IVRank)
3. Confirm spread selection rules and exits
4. Write a minimal backtest loop
