"""
=================================================================
SETTINGS
=================================================================
MACD settings: 12, 26, 9 (standard)
Crossover distance threshold: 0.5
Candle wait after crossover: 2 x 4H candles
Swing point lookback: 5-10 candles (test multiple)
Divergence recency window: 50 x 4H candles
Risk-reward target: 2R
Position sizing: 50% closed at target, 50% trailed
Timeframes: Daily (bias), 4H (signal), 1H (entry)

=================================================================
SUPPORTING FUNCTIONS
=================================================================
Function FIND_SWING_HIGHS(price, lookback):
  For each candle i:
    If price[i] is highest point within lookback candles
    on both left and right sides:
      → mark as swing high
  Return list of swing highs with price and index

Function FIND_SWING_LOWS(price, lookback):
  Same logic but for lowest points
  Return list of swing lows with price and index

=================================================================
STEP 1 — DAILY BIAS
=================================================================
For each day:
  If Daily MACD line > 0:
    bias = LONG
  If Daily MACD line < 0:
    bias = SHORT
  If Daily MACD line ≈ 0:
    bias = NEUTRAL → skip, no trades today

=================================================================
STEP 2 - 4H SIGNAL (CROSSOVER OR DIVERGENCE)
=================================================================
For each 4H candle:

  ── CROSSOVER SIGNAL ──

  If bias == LONG:
    Look for bullish crossover (MACD line crosses above signal line)
    AND crossover occurs above +0.5
    → crossover_signal = LONG

  If bias == SHORT:
    Look for bearish crossover (MACD line crosses below signal line)
    AND crossover occurs below -0.5
    → crossover_signal = SHORT


  ── DIVERGENCE SIGNAL ──

  Find last 2 swing highs on price (4H)
  Find last 2 swing highs on MACD line (4H)

  BEARISH DIVERGENCE:
    If bias == SHORT:
      If price swing high 2 > price swing high 1 (price making higher high)
      AND MACD swing high 2 < MACD swing high 1 (MACD making lower high)
      AND both swing highs within last 50 candles
      → divergence_signal = SHORT

  Find last 2 swing lows on price (4H)
  Find last 2 swing lows on MACD line (4H)

  BULLISH DIVERGENCE:
    If bias == LONG:
      If price swing low 2 < price swing low 1 (price making lower low)
      AND MACD swing low 2 > MACD swing low 1 (MACD making higher low)
      AND both swing lows within last 50 candles
      → divergence_signal = LONG


  ── COMBINE SIGNALS ──

  If crossover_signal OR divergence_signal is valid:
    → proceed to Step 3
  Else:
    → skip



=================================================================
STEP 3 — VALIDATE CROSSOVER SIGNAL
=================================================================

If signal came from crossover:
  Wait 2 x 4H candles after crossover
  If MACD line has NOT crossed back (signal still valid):
    → proceed to Step 4
  Else:
    → invalidate signal, skip

If signal came from divergence:
  No wait required, proceed directly to Step 4



=================================================================
STEP 4 — 1H ENTRY TRIGGER
=================================================================

After valid 4H signal:
  Monitor 1H histogram

  If signal == LONG:
    Wait for ONE of:
      - Flip: first green bar after consecutive red bars
      - Shrinking Tower: red bars getting smaller → enter on first green bar
      - Zero Bounce: histogram approaches zero from below, turns back green
    → entry trigger confirmed

  If signal == SHORT:
    Wait for ONE of:
      - Flip: first red bar after consecutive green bars
      - Shrinking Tower: green bars getting smaller → enter on first red bar
      - Zero Bounce: histogram approaches zero from above, turns back red
    → entry trigger confirmed

=================================================================
STEP 5 — TRADE EXECUTION
=================================================================

Enter at close of the triggering 1H candle

If LONG:
  Stop loss = lowest low of last N candles (swing low)
  Risk = entry price - stop loss
  Target = entry price + (2 x risk)

If SHORT:
  Stop loss = highest high of last N candles (swing high)
  Risk = stop loss - entry price
  Target = entry price - (2 x risk)

=================================================================
STEP 6 — TRADE MANAGEMENT
=================================================================

If price reaches Target:
  Close 50% of position
  Move stop loss to breakeven on remaining 50%
  Trail remaining position:
    If LONG: exit when MACD line crosses below signal line on 1H
    If SHORT: exit when MACD line crosses above signal line on 1H

If price reaches Stop Loss before Target:
  Close 100% of position → record full loss

=================================================================
STEP 7 — LOGGING
=================================================================

For each trade record:
  Entry price, direction, date/time
  Signal type (crossover or divergence)
  Stop loss level
  Target level
  Exit price and reason (target hit, stop hit, trailing stop)
  Win or loss
  R-multiple achieved

=================================================================
PARAMETERS TO TEST
=================================================================

- Swing point lookback: 5, 10, 20 candles
- Crossover distance threshold: 0.3, 0.5, 0.8
- Divergence recency window: 30, 50, 75 candles
- Stop loss swing lookback: 10, 20 candles
"""