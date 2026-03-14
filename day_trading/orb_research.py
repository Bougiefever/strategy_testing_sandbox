"""
ORB Research in preparation to test ORB 0DTE options strategies - first find if there's even a directional edge

"""
import pandas as pd
import numpy as np
from pathlib import Path
from collections import deque
import datetime
from utility import *
import matplotlib.pyplot as plt
import talib

ticker = 'SPY'
start_date = datetime.datetime(2016, 3, 9)
end_date = datetime.datetime(2022, 12, 23)

""""
This section is to build the daily bar indicators to use for the intraday strategy

FOR each day:
    daily.Open  = first bar's Open
    daily.High  = max(High) across all bars that day
    daily.Low   = min(Low)  across all bars that day
    daily.Close = last bar's Close

THEN compute daily indicators on the daily bars:
    Range, TrueRange, ATR(14)
    Stretch(10)          # avg of (High-Open) and (Open-Low) over 10 days
    NR4, NR7
    InsideDay
    WideSpread           # Range > 1.5 * AvgRange(10)
"""
daily_data_folder = Path(r'D:\stock_data\daily')
daily_fn = daily_data_folder.joinpath(f'{ticker}.parquet')

df_daily = pd.read_parquet(daily_fn)
df_daily.set_index('quote_datetime', inplace=True)
df_daily.sort_index(inplace=True)

df_daily['range'] = df_daily['high'] - df_daily['low']
df_daily['20ma_range'] = df_daily['range'].rolling(20).mean()
df_daily['min_range_4'] = df_daily['range'].rolling(4, min_periods=4).min()
df_daily['min_range_7'] = df_daily['range'].rolling(7, min_periods=7).min()
df_daily['mean_range_10'] = df_daily['range'].rolling(10, min_periods=10).mean()
df_daily['nr4'] = df_daily['range'].eq(df_daily['range'].rolling(4, min_periods=4).min())
df_daily['nr7'] = df_daily['range'].eq(df_daily['range'].rolling(7, min_periods=7).min())
df_daily['prev_high'] = df_daily['high'].shift(1)
df_daily['prev_low'] = df_daily['low'].shift(1)
df_daily['inside_day'] = (df_daily['high'] < df_daily['prev_high']) & (df_daily['low'] > df_daily['prev_low'])
df_daily['widespread_day'] = df_daily['range'] > 1.5 * df_daily['mean_range_10']
df_daily['today_direction'] = df_daily.apply(lambda x: 1 if x['close'] > x['open'] else 0, axis=1)
df_daily['up_stretch'] = (df_daily['high'] - df_daily['open']).rolling(10, min_periods=10).mean()
df_daily['dn_stretch'] = (df_daily['open'] - df_daily['low']).rolling(10, min_periods=10).mean()
df_daily['stretch'] = (abs((df_daily['up_stretch'] - df_daily['dn_stretch'])) / 2)
df_daily['atr'] = talib.ATR(df_daily['high'].to_numpy(float), df_daily['low'].to_numpy(float), df_daily['close'].to_numpy(float), timeperiod=14)

df_daily = df_daily[(df_daily.index >= start_date) & (df_daily.index <= end_date)]

data_folder = Path(r'D:\save\temp')
ticker_fn = data_folder.joinpath(f'{ticker}.parquet')

df = pd.read_parquet(ticker_fn)

def get_entry(long_entry_dt, short_entry_dt, long_entry_px, short_entry_px, stretch):
    if pd.notna(long_entry_dt):
        if pd.isna(short_entry_dt) or long_entry_dt < short_entry_dt:
            entry_px = long_entry_px
            entry_dt = long_entry_dt
            stop_px = entry_px - stretch
            target_px = entry_px + stretch * 2.0
            return entry_px, entry_dt, stop_px, target_px, 'long'

    if pd.notna(short_entry_dt):
        entry_px = short_entry_px
        entry_dt = short_entry_dt
        stop_px = entry_px + stretch
        target_px = entry_px - stretch * 2.0
        return entry_px, entry_dt, stop_px, target_px, 'short'
    return None, None, None, None, None

def get_exit(profit_dt, stop_dt, eod_dt, profit_px, stop_px, eod_px):
    if pd.notna(profit_dt):
        if pd.isna(stop_dt) or profit_dt < stop_dt:
            exit_px = profit_px
            exit_dt = profit_dt
            exit_reason = 'profit'
            return exit_px, exit_dt, exit_reason
    if pd.notna(stop_dt):
        exit_px = stop_px
        exit_dt = stop_dt
        exit_reason = 'stopped'
        return exit_px, exit_dt, exit_reason

    return eod_px, eod_dt, 'eod close'

open_time = datetime.time(9, 30)
orb_time = datetime.time(9, 35)
open_trade_end_time = datetime.time(10, 30)
close_time = datetime.time(15, 59)

orb_minutes = 5
trade_id = 0
equity = 1_000

df.set_index('quote_datetime', inplace=True)
df.sort_index(inplace=True)
df = df[(df.index >= start_date) & (df.index <= end_date)]

dts = df_daily.index.tolist()

trades = []
daily_records = []
cum_pnl = []
running_total = 0


orb_ranges = deque()
for dt in dts: # we need to get yesterday data, so start with row 1
    # get relevant data for today
    i = df_daily.index.get_loc(dt)
    print(dt)
    cum_pnl.append(running_total)

    yesterday_ = df_daily.iloc[i-1]
    df_dt = df.loc[df.index.normalize() == dt]
    if df_dt.empty:
        continue

    # get orb values
    open_dt = pd.Timestamp(f"{dt.date()} {open_time}")
    orb_dt = pd.Timestamp(f"{dt.date()} {orb_time}")
    open_trade_end_dt = pd.Timestamp(f"{dt.date()} {open_trade_end_time}")
    eod_dt = df_dt.iloc[-1].name
    if orb_dt not in df_dt.index:
        orb_dt = df_dt.iloc[5].name

    orb_window = df_dt.loc[open_dt: open_dt + pd.Timedelta(minutes=orb_minutes) - pd.Timedelta(minutes=1)]
    o1 = float(orb_window["open"].iloc[0])
    c1 = float(orb_window["close"].iloc[-1])
    h1 = float(orb_window["high"].max())
    l1 = float(orb_window["low"].min())
    orb_range = h1 - l1
    orb_ranges.append(orb_range)

    # orb_ranges.append(orb_range)
    if len(orb_ranges) < 20:
        continue
    elif len(orb_ranges) == 20:
        range_ma20 = sum(orb_ranges) / 20
        orb_ranges.popleft()

    # get values from the daily data
    nr4 = yesterday_['nr4']
    nr7 = yesterday_['nr7']
    inside_day = yesterday_['inside_day']
    widespread_day = yesterday_['widespread_day']
    stretch = yesterday_['stretch']

    # dow = dt.weekday()
    # if dow not in [0, 2, 4]:
    #     continue

    if orb_range > range_ma20:
        daily_records.append({
            'date': dt,
            'close': df_dt.iloc[0]['close'],
            'portfolio_value': equity,
            'in_trade': False,
        })
        continue

    long_entry_px = h1 + stretch
    short_entry_px = l1 - stretch

    open_trade_window = df_dt.loc[orb_dt:open_trade_end_dt]
    long_entry_scan = open_trade_window['high'] >= long_entry_px
    long_entry_dt = first_true_ts(long_entry_scan)
    short_entry_scan = open_trade_window['low'] <= short_entry_px
    short_entry_dt = first_true_ts(short_entry_scan)

    # determine if long or short or no trade today
    # get entry, profit,and stop prices
    entry_px, entry_dt, stop_px, target_px, direction = get_entry(long_entry_dt, short_entry_dt, long_entry_px, short_entry_px, stretch)
    if entry_px is None:
        daily_records.append({
            'date': dt,
            'close': df_dt.iloc[0]['close'],
            'portfolio_value': equity,
            'in_trade': False,
        })
        continue

    trade_close_window = df_dt[entry_dt + pd.Timedelta(minutes=1):eod_dt]
    if direction == 'long':
        profit_scan = trade_close_window['high'] >= target_px
        stop_scan = trade_close_window['low'] <= stop_px

    elif direction == 'short':
        profit_scan = trade_close_window['low'] <= target_px
        stop_scan = trade_close_window['high'] >= stop_px
    profit_dt = first_true_ts(profit_scan)
    stop_dt = first_true_ts(stop_scan)

    eod_px = df_dt.loc[eod_dt]['close']
    exit_px, exit_dt, exit_reason = get_exit(profit_dt, stop_dt, eod_dt, target_px, stop_px, eod_px)

    shares = 100
    if direction == 'long':
        pnl = shares * (exit_px - entry_px)
        pct_return = (exit_px - entry_px) / entry_px
    elif direction == 'short':
        pnl = shares * (entry_px - exit_px)
        pct_return = (entry_px - exit_px) / entry_px

    equity += pnl
    trade_id += 1

    trade = {
        "id": trade_id,
        "date": dt,
        "entry_dt": entry_dt,
        "profit_target_px": target_px,
        "entry_px": entry_px,
        "exit_dt": exit_dt,
        "exit_px": exit_px,
        "shares": shares,
        "pnl": pnl,
        "net_pnl": pnl,
        "pnl_pct": pct_return,
        "fees": 0.0,
        "exit_reason": exit_reason,
        "equity_after": equity,
        "holding_period": 0,
    }
    trades.append(trade)
    daily_records.append({
        'date': dt,
        'close': df_dt.iloc[0]['close'],
        'portfolio_value': equity,
        'in_trade': True,
    })
    running_total += pnl
    cum_pnl[-1] = running_total


df_trades = pd.DataFrame(trades)
print(f'ending equity: {equity:.2f}')

df_daily = pd.DataFrame(daily_records)
df_daily.set_index('date', inplace=True)

portfolio_stats, trade_stats = print_report(ticker, df_trades, df_daily,
                                                f"{ticker} 5-min ORB Strategy", frequency='daily')

dts = dts[:len(cum_pnl)]

plt.figure(figsize=(12, 6))
plt.plot(dts, cum_pnl)
plt.title('ORB Equity Curve')
plt.xlabel('Trade date')
plt.ylabel('Cumulative pnl $')
plt.axhline(y=0, color='gray', linestyle='--')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

pass