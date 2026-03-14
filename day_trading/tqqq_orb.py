"""
From the WhitePaper Can Day Trading Really Be Profitable?
D:\projects\documents\tqqq_research\tqqq_orb.pdf

Psuedocode from Claude

INITIALIZE:
    capital = 25000
    max_leverage = 4
    risk_per_trade = 0.01
    commission_per_share = 0.0005
    profit_target_multiplier = 10

FOR each trading day:
    first_candle = get_5min_candle(9:30 - 9:35)

    // Skip doji candles
    IF first_candle.open == first_candle.close:
        CONTINUE to next day

    // Determine direction
    IF first_candle.close > first_candle.open:
        direction = LONG
        entry_price = second_candle.open  // open of 9:35-9:40 candle
        stop_price = first_candle.low
    ELSE:
        direction = SHORT
        entry_price = second_candle.open
        stop_price = first_candle.high

    // Calculate position size
    R = |entry_price - stop_price|
    shares_by_risk = FLOOR(capital * risk_per_trade / R)
    shares_by_leverage = FLOOR(4 * capital / entry_price)
    shares = MIN(shares_by_risk, shares_by_leverage)

    // Simulate intraday price action
    profit_target = entry_price + direction * (10 * R)

    FOR each subsequent 5min candle until 4:00 PM:
        IF direction == LONG:
            IF candle.low <= stop_price:
                exit_price = stop_price
                BREAK
            IF candle.high >= profit_target:
                exit_price = profit_target
                BREAK
        ELSE:  // SHORT
            IF candle.high >= stop_price:
                exit_price = stop_price
                BREAK
            IF candle.low <= profit_target:
                exit_price = profit_target
                BREAK

    // If no stop or target hit, exit at market close
    IF no exit yet:
        exit_price = last_candle.close

    // Update capital
    pnl = direction * shares * (exit_price - entry_price)
    commission = shares * 2 * commission_per_share  // entry + exit
    capital = capital + pnl - commission

"""

import pandas as pd
import numpy as np
from pathlib import Path
import datetime
from utility import *
import matplotlib.pyplot as plt

capital = 25000
max_leverage = 4
risk_per_trade = 0.01
commission_per_share = 0.0005
profit_target_multiplier = 10
open_time = datetime.time(9, 30)
orb_time = datetime.time(9, 35)
close_time = datetime.time(15, 59)
start_date = datetime.datetime(2016, 1, 1)
end_date = datetime.datetime(2023, 2, 28)
orb_minutes = 5
trade_id = 0

tqqq_data_file = Path(r'D:\save\temp\TQQQ.parquet')
tqqq_daily = Path(r'D:\stock_data\daily\TQQQ.parquet')
df = pd.read_parquet(tqqq_data_file, engine='pyarrow')
df.set_index('quote_datetime', inplace=True)
df.sort_index(inplace=True)
df = df[(df.index >= start_date) & (df.index <= end_date)]

dts = df.index.normalize().unique().tolist()

def get_exit(profit_target_dt, stop_dt, eod_dt, profit_target_price, stop_price, eod_price):
    # Profit target hit before stop triggered (or stop never triggered)
    if pd.notna(profit_target_dt):
        if pd.isna(stop_dt) or profit_target_dt < stop_dt:
            return profit_target_dt, profit_target_price, 'profit target'

    # stop triggered
    if pd.notna(stop_dt):
        return stop_dt, stop_price, 'stopped out'

    # otherwise, eod close
    return eod_dt, eod_price, 'eod close'

trades = []
daily_records = []
cum_pnl = []
running_total = 0
for dt in dts[1:-1]:
    print(dt)
    cum_pnl.append(running_total)
    df_dt = df[df.index.normalize() == dt]
    open_dt = pd.Timestamp(f"{dt.date()} {open_time}")
    orb_dt = pd.Timestamp(f"{dt.date()} {orb_time}")
    eod_dt = df_dt.iloc[-1].name
    if orb_dt not in df_dt.index:
        continue

    orb_window = df_dt.loc[open_dt: open_dt + pd.Timedelta(minutes=orb_minutes) - pd.Timedelta(minutes=1)]
    o1 = float(orb_window["open"].iloc[0])
    c1 = float(orb_window["close"].iloc[-1])
    h1 = float(orb_window["high"].max())
    l1 = float(orb_window["low"].min())
    orb_range = h1 - l1
    orb_open_close = abs(c1-o1)

    # check for doji
    if orb_range == 0:
        continue
    is_doji = (orb_open_close / orb_range) < 0.05
    if is_doji:
        continue

    # Determine direction. Get open and stop prices
    open_candle = df_dt.loc[orb_dt]
    direction = 'long' if c1 > o1 else 'short'
    entry_dt = orb_dt
    entry_px = open_candle['open']
    stop_px = l1 if direction == 'long' else h1

    #Calculate position size
    R = abs(entry_px - stop_px)
    if R == 0:
        continue
    shares_by_risk = int(np.floor(capital * risk_per_trade / R))
    shares_by_leverage = int(np.floor(4 * capital / entry_px))
    shares = min(shares_by_risk, shares_by_leverage)

    trading_window = df_dt.loc[orb_dt:eod_dt]

    if direction == 'long':
        profit_target_px = entry_px + (10 * R)
        profit_scan = trading_window['high'] >= profit_target_px
        stop_scan = trading_window['low'] <= stop_px
    elif direction == 'short':
        profit_target_px = entry_px - (10 * R)
        profit_scan = trading_window['low'] <= profit_target_px
        stop_scan = trading_window['high'] >= stop_px
    profit_dt = first_true_ts(profit_scan)
    stop_dt = first_true_ts(stop_scan)
    eod_px = df_dt.loc[eod_dt]['close']

    exit_dt, exit_px, exit_reason = get_exit(profit_dt, stop_dt, eod_dt, profit_target_px, stop_px, eod_px)

    if direction == 'long':
        pnl = shares * (exit_px - entry_px)
        pct_return = (exit_px - entry_px) / entry_px
    elif direction == 'short':
        pnl = shares * (entry_px - exit_px)
        pct_return = (entry_px - exit_px) / entry_px

    capital += pnl
    trade_id += 1
    trade = {
        "id": trade_id,
        "date": entry_dt,
        "entry_dt": entry_dt,
        "profit_target_px": profit_target_px,
        "entry_px": entry_px,
        "exit_dt": exit_dt,
        "exit_px": exit_px,
        "shares": shares,
        "gross_pnl": pnl,
        "net_pnl": pnl,
        "pct_return": pct_return,
        "fees": 0.0,
        "exit_reason": exit_reason,
        "equity_after": capital,

    }
    trades.append(trade)
    daily_records.append({
        'date': dt,
        'close': df_dt.iloc[0]['close'],
        'portfolio_value': f'{capital:.2f}'
    })
    running_total += pnl
    cum_pnl[-1] = running_total



df_trades = pd.DataFrame(trades)
t_stats = trade_stats(df_trades)
print(t_stats)

print(f'ending capital: {capital:.2f}')

dts = dts[:len(cum_pnl)]

plt.figure(figsize=(12, 6))
plt.plot(dts, cum_pnl)
plt.title('TQQQ ORB Equity Curve')
plt.xlabel('Trade date')
plt.ylabel('Cumulative pnl $')
plt.axhline(y=0, color='gray', linestyle='--')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

pass