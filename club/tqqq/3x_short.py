import pandas as pd
import numpy as np
from pathlib import Path
import talib
import datetime
from helpers import *

"""
=====================================================
LAMBROS PETROU WEEKLY MACD TQQQ STRATEGY
Complete Pseudocode
=====================================================

OVERVIEW:
  Two data feeds:
    1. QQQ weekly bars — drives entry/exit signals
    2. TQQQ weekly bars — drives execution and P&L

  Two states:
    OUT — in cash, watching for MACD entry
    IN  — holding TQQQ, watching for MACD exit or stop loss

  Two entry signals:
    PRIMARY  — MACD line crosses above zero
    RE-ENTRY — MACD line crosses above Signal line
              (only after a stop loss while MACD still above zero)

  Two exit signals:
    PRIMARY  — MACD line crosses below zero (with buffer)
    STOP LOSS — price falls below active stop level


=====================================================
SECTION 1: CONVERT DAILY DATA TO WEEKLY
=====================================================

If your data is daily, resample to weekly bars:
  weekly_open   = first open of the week
  weekly_high   = max high of the week
  weekly_low    = min low of the week
  weekly_close  = last close of the week (Friday)
  weekly_volume = sum of daily volumes

Do this for BOTH QQQ and TQQQ.


=====================================================
SECTION 2: CALCULATE MACD ON QQQ WEEKLY
=====================================================

CONSTANTS:
  FAST_PERIOD   = 12
  SLOW_PERIOD   = 26
  SIGNAL_PERIOD = 9    (Petrou uses 5 for slight edge, 9 is standard)
  BUFFER_PCT    = 0.02 (2% buffer below zero for exit)

CALCULATIONS:
  ema_fast   = 12-week EMA of QQQ close
  ema_slow   = 26-week EMA of QQQ close
  macd_line  = ema_fast - ema_slow
  signal_line = 9-week EMA of macd_line

  (these are standard MACD calculations,
   talib.MACD will give you all three)

FOR EACH WEEK, RECORD:
  macd_line value
  signal_line value
  macd_above_zero     = macd_line > 0
  macd_cross_up_zero  = macd_line > 0 AND prev macd_line <= 0
  macd_cross_down_zero = macd_line < (0 - BUFFER_PCT) AND prev macd_line >= (0 - BUFFER_PCT)
  macd_cross_up_signal = macd_line > signal_line AND prev macd_line <= prev signal_line


=====================================================
SECTION 3: TRADE SIMULATOR
=====================================================

STATE VARIABLES:
  in_position       = FALSE
  entry_price       = NaN
  peak_high         = NaN
  stopped_out       = FALSE  (TRUE if last exit was a stop loss
                              while MACD was still above zero)
  capital           = 100000
  shares            = 0

CONSTANTS:
  HARD_STOP_PCT     = 0.10   (10% below entry)
  TRAILING_STOP_PCT = 0.30   (30% below peak high)
  TRAILING_BUFFER   = 0.02   (2% extra wiggle room)
  RISK_PER_TRADE    = 0.02   (risk 2% of account)

FOR EACH WEEK:

  ——— IF IN POSITION ———

  IF in_position:

    # Update peak high
    peak_high = max(peak_high, TQQQ this week's high)

    # Calculate active stop
    hard_stop = entry_price * (1 - HARD_STOP_PCT)
    trailing_stop = peak_high * (1 - TRAILING_STOP_PCT) * (1 - TRAILING_BUFFER)
    active_stop = max(hard_stop, trailing_stop)

    # CHECK EXIT: stop loss
    IF TQQQ weekly close < active_stop:
      EXIT at TQQQ weekly close
      in_position = FALSE
      IF macd_above_zero:
        stopped_out = TRUE    (eligible for re-entry)
      ELSE:
        stopped_out = FALSE

    # CHECK EXIT: MACD crosses below zero
    ELIF macd_cross_down_zero:
      EXIT at TQQQ weekly close
      in_position = FALSE
      stopped_out = FALSE

  ——— IF NOT IN POSITION ———

  IF NOT in_position:

    # PRIMARY ENTRY: MACD crosses above zero
    IF macd_cross_up_zero:
      ENTER at TQQQ weekly close
      in_position = TRUE
      stopped_out = FALSE

    # RE-ENTRY: after stop loss, MACD still above zero
    ELIF stopped_out AND macd_cross_up_signal:
      ENTER at TQQQ weekly close
      in_position = TRUE
      stopped_out = FALSE

  ——— ENTRY EXECUTION ———

  When entering:
    position_size = capital * RISK_PER_TRADE / HARD_STOP_PCT
    shares = position_size / TQQQ weekly close
    entry_price = TQQQ weekly close
    peak_high = TQQQ weekly close
    capital -= shares * entry_price

  ——— EXIT EXECUTION ———

  When exiting:
    exit_price = TQQQ weekly close
    pnl = (exit_price - entry_price) * shares
    capital += shares * exit_price
    record trade


=====================================================
SECTION 4: WHAT TO TRACK
=====================================================

PER TRADE:
  entry_date, entry_price
  exit_date, exit_price
  exit_reason ("macd_zero_cross" or "stop_loss")
  pnl, pnl_pct
  holding_weeks
  peak_gain_pct
  max_drawdown_pct

DAILY/WEEKLY:
  portfolio_value
  in_position
  macd_line, signal_line
  active_stop level

KEY DIFFERENCES FROM VIBHA:
  - Weekly bars, not daily
  - Signals come from QQQ, execution on TQQQ
  - Only 2 entry rules, 2 exit rules
  - No distribution days, no sell signal checklist
  - Holds for months at a time during bull runs
  - Position sizing is 20% of capital, not 100%

The tradeable universe is: XLK/TECL, SPY/UPRO, QQQ/TQQQ, and SMH/SOXL.
"""
base_ticker = 'QQQ'
leveraged_ticker = 'SQQQ'
fast_period = 12
slow_period = 26
signal_period = 9


output_folder = Path(r'D:\test_data\3x_short')
output_folder.mkdir(parents=True, exist_ok=True)
stock_folder = Path(r'D:\stock_data\daily')

base_fn = stock_folder.joinpath(f'{base_ticker}.parquet')
df_base = pd.read_parquet(base_fn, engine='pyarrow')
df_base.set_index('quote_datetime', inplace=True)
df_base.sort_index(inplace=True)
df_base['200ma'] = talib.SMA(df_base['close'].to_numpy(float), timeperiod=200)
df_base['50ma'] = talib.SMA(df_base['close'].to_numpy(float), timeperiod=50)

lev_fn = stock_folder.joinpath(f'{leveraged_ticker}.parquet')
df_lev = pd.read_parquet(lev_fn, engine='pyarrow')
df_lev.set_index('quote_datetime', inplace=True)
df_lev.sort_index(inplace=True)


df_base['macd'], df_base['macd_signal'], df_base['macd_hist'] = talib.MACD(df_base['close'].to_numpy(float), fast_period,
                                                                        slow_period, signal_period)
df_base['macd_prev'] = df_base['macd'].shift(1)

start_date = df_lev.index[0] 
end_date = df_lev.index[-1]
df_base = df_base[(df_base.index >= start_date) & (df_base.index <= end_date)]


risk_per_trade = 0.20

if __name__ == '__main__':

    dts = df_base.index.tolist()
    equity = 100_000
    hard_stop = 0
    current_trade = None
    stopped_out = False
    trades = []
    daily_record = []
    for dt in dts:

        if current_trade is not None:
            # update
            close = df_lev.loc[dt, 'close']
            high = df_lev.loc[dt, 'high']
            peak_high = max(peak_high, high)
            unrealized_pct = (close - current_trade['entry_price']) / current_trade['entry_price']
            current_trade['peak_gain_pct'] = max(current_trade['peak_gain_pct'], unrealized_pct)
            current_trade['max_drawdown_pct'] = min(current_trade['max_drawdown_pct'], unrealized_pct)
            current_trade['holding_period'] += 1

            # check for exit
            close = df_lev.loc[dt, 'close']
            macd = df_base.loc[dt, 'macd']
            exit_trade = False
            exit_reason = ''
            if macd > 0:
                exit_trade = True
                exit_reason = "macd gt 0"
            if exit_trade:
                current_trade['exit_date'] = dt
                current_trade['exit_price'] = close
                current_trade['pnl'] = (close - current_trade['entry_price']) * current_trade['shares']
                current_trade['pnl_pct'] = (close - current_trade['entry_price']) / current_trade['entry_price']
                current_trade['exit_reason'] = exit_reason
                equity += current_trade['shares'] * close
                trades.append(current_trade)
                current_trade = None
                active_stop = np.nan

                peak_high = np.nan


        # Check for trade entry - but not on the same day as exit
        elif current_trade is None:
            base_dt = df_base.loc[dt]
            lev_dt = df_lev.loc[dt]
            macd = base_dt['macd']
            prev_macd = base_dt['macd_prev']
            signal = base_dt['macd_signal']
            entry_px = lev_dt['close']
            shares = equity / entry_px
            enter_trade = False
            if macd < 0 and prev_macd >= 0:
                enter_trade = True
                entry_type = 'primary'
            elif stopped_out and macd < 0 and macd < signal:
                enter_trade = True
                entry_type = 'secondary'
            if enter_trade:
                current_trade = {
                    'entry_date': dt,
                    'entry_price': entry_px,
                    'entry_type': entry_type,
                    'shares': shares,
                    'peak_gain_pct': 0.0,
                    'max_drawdown_pct': 0.0,
                    'holding_period': 0,
                }
                equity -= shares * entry_px
                peak_high = entry_px
                active_stop = entry_px * (1 - hard_stop_pct)

                stopped_out = False

        # record daily record
        daily_record.append({
            'date': dt,
            'close': df_lev.loc[dt, 'close'],
            'portfolio_value': equity + (current_trade['shares'] * df_lev.loc[dt, 'close'] if current_trade else 0),
            'in_trade': current_trade is not None,
        })

    df_daily = pd.DataFrame(daily_record)
    df_daily.set_index('date', inplace=True)
    df_trades = pd.DataFrame(trades)
    ticker = f'{base_ticker}/{leveraged_ticker}'
    portfolio_stats, trade_stats = print_report(ticker, df_trades, df_daily,
                                                f"{leveraged_ticker} Daily QQQ Under 200 MA Strategy", frequency='daily')

    portfolio_stats_fn = output_folder.joinpath(f"portfolio_stats_{leveraged_ticker}.csv")
    trades_stats_fn = output_folder.joinpath(f"trades_stats_{leveraged_ticker}.csv")
    trades_fn = output_folder.joinpath(f"trades_{leveraged_ticker}.csv")
    portfolio_stats.to_csv(portfolio_stats_fn, index=True)
    trade_stats.to_csv(trades_stats_fn, index=True)
    df_trades.to_csv(trades_fn, index=False)