import pandas as pd
import numpy as np
import pyperclip
import csv
from pathlib import Path
import datetime
import talib
from utility import *

stock_dir = Path(r'D:\stock_data\intraday\stocks\etfs')
daily_stock_dir = Path(r'D:\stock_data\daily_stock_prices')

ticker = 'QQQ'
tz = "America/New_York"
open_time = datetime.time(9, 30)
trade_entry = datetime.time(9, 35)
close_time = datetime.time(15, 59)
check_R_time = datetime.time(10, 15)
first_candle_minutes = 5
starting_cash = 100_000
target_R = 0.5
position_risk = 0.01
max_leverage = 4.0
min_R = 0.15
avg_or = 1.4
start_date = datetime.datetime(2022, 1, 1)
end_date = datetime.datetime(2024, 1, 1)

df = pd.read_parquet(stock_dir.joinpath(f'{ticker}.parquet'), engine='pyarrow')
df.set_index('quote_datetime', inplace=True)
df.sort_index(inplace=True)
df = df[(df.index >= start_date) & (df.index <= end_date)]

df_daily = pd.read_parquet(daily_stock_dir.joinpath(f'{ticker}_.parquet'), engine='pyarrow')
df_daily.set_index('quote_datetime', inplace=True)
df_daily.sort_index(inplace=True)
df_daily = df_daily[(df_daily.index >= start_date) & (df_daily.index <= end_date)]
df_daily['atr'] = talib.ATR(df_daily['high'].to_numpy(float), df_daily['low'].to_numpy(float), df_daily['close'].to_numpy(float),
                            timeperiod=14)
df_daily['ma_200'] = talib.MA(df_daily['close'].to_numpy(float), timeperiod=200)

# remove warm-up period
start_date = datetime.datetime(2023, 1, 1)
df = df[df.index >= start_date]
df_daily = df_daily[df_daily.index >= start_date]

dts = df_daily.index.tolist()
equity = starting_cash
equity_rows = []
trades = []
for dt in dts:
    print(dt)
    daily = df_daily.loc[dt]
    df_dt = df[df.index.normalize() == dt]
    if df_dt.empty:
        continue

    open_dt = pd.Timestamp(f"{dt.date()} {open_time}")
    entry_dt = pd.Timestamp(f"{dt.date()} {trade_entry}")
    close_dt = pd.Timestamp(f"{dt.date()} {close_time}")
    check_R = pd.Timestamp(f"{dt.date()} {check_R_time}")

    first_window = df_dt.loc[open_dt: open_dt + pd.Timedelta(minutes=first_candle_minutes) - pd.Timedelta(minutes=1)]

    # First 5-min candle
    o1 = float(first_window["open"].iloc[0])
    c1 = float(first_window["close"].iloc[-1])
    h1 = float(first_window["high"].max())
    l1 = float(first_window["low"].min())
    or_range = h1 - l1

    if or_range < avg_or:
        equity_rows.append((dt, equity, or_range))
        continue

    if abs(c1 - o1) <= 0.02:
        # doji -> no trade - under 2 cents diff
        equity_rows.append((dt, equity, or_range))
        continue

    # set up price parameters
    direction = "long" if c1 > o1 else "short"
    entry_px = df_dt.loc[entry_dt, 'open']
    if direction == "long":
        stop_px = l1
        R = entry_px - stop_px
        target_px = entry_px + (target_R * R)
    else:
        stop_px = h1
        R = stop_px - entry_px
        target_px = entry_px - (target_R * R)

    if R <= min_R:
        equity_rows.append((dt, equity, or_range))
        continue

    # position sizing
    dollar_risk = equity * position_risk
    shares_risk = int(np.floor(dollar_risk / R))
    shares_lev = int(np.floor((equity * max_leverage) / entry_px))
    shares = max(0, min(shares_risk, shares_lev))

    if shares <= 0:
        equity_rows.append((dt, equity, or_range))
        continue

    scan = df_dt.loc[entry_dt: close_dt]
    if scan.empty or len(scan) < 385: # no data or a half day - do not trade
        equity_rows.append((dt, equity, or_range))
        continue

    exit_px = None
    exit_dt = None
    exit_reason = None

    # check R @ 10:15
    r_scan = scan.loc[entry_dt:check_R]
    if direction == "long":
        scan['stop'] = scan['low'] <= stop_px
        r_scan['target'] = r_scan['high'] >= target_px
    else:
        scan['stop'] = scan['high'] >= stop_px
        r_scan['target'] = r_scan['low'] <= target_px

    scan['exit'] = scan['stop'] #| scan['target']
    exit_dt = first_true_ts(scan['exit'])
    target_dt = first_true_ts(r_scan['target'])
    if pd.isna(exit_dt):
        # no exit signal hit after entry -> EOD exit (last bar)
        exit_dt = scan.index[-1]
        exit_px = scan.iloc[-1]['close']
        exit_reason = "eod"
    elif bool(scan.loc[exit_dt, "stop"]):
        exit_reason = "stop"
        exit_px = stop_px
    elif pd.isna(target_dt):
        exit_dt = check_R
        exit_px = scan.loc[check_R]['close']
        exit_reason = "no_follow_thru"
    else:
        pass

    if direction == "long":
        pnl = (exit_px - entry_px) * shares
    else:
        pnl = (entry_px - exit_px) * shares

    equity = equity + pnl

    trades.append({
        "date": dt.date(),
        "direction": direction,
        "entry_dt": entry_dt,
        "entry_px": entry_px,
        "stop_px": stop_px,
        "target_px": target_px,
        "exit_dt": exit_dt,
        "exit_px": exit_px,
        "shares": shares,
        "gross_pnl": pnl,
        "net_pnl": pnl,
        "fees": 0.0,
        "exit_reason": exit_reason,
        "R_per_share": R,
        "equity_after": equity,
    })

    equity_rows.append((dt, equity, or_range))


trades_df = pd.DataFrame(trades)
t_stats = trade_stats(trades_df)
print(t_stats)

rows_fn = Path(r'C:\_junk\equity_rows.csv')
with open(rows_fn, 'w', newline='') as f:
    csvwriter = csv.writer(f)
    csvwriter.writerows(equity_rows)
