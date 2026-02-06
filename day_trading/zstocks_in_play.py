import sys
import datetime
import pandas as pd
import numpy as np
from pathlib import Path
import talib
from utility import *

nasdaq_folder = Path(r'D:\stock_data\intraday\stocks\nasdaq')
daily_folder = Path(r'D:\stock_data\daily_stock_prices')
nq_files = nasdaq_folder.glob('*.parquet')

ticker = 'AAPL'
start_date = datetime.datetime(2021, 1, 1)
end_date = datetime.datetime(2023, 1, 1)
rvol_days = 14
r_vol_limit = 1.5
first_candle_minutes = 5
s = 0.15
position_risk = 0.01
starting_equity = 100_000

open_time = datetime.time(9, 30)
or_close = datetime.time(9, 35)
close_time = datetime.time(15, 59)
valid_entry_time = datetime.time(10, 30)
exit_trade_time = datetime.time(15, 55)

nasdaq_files = list(nasdaq_folder.glob('*.parquet'))

for fn in nasdaq_files:
    df = pd.read_parquet(fn, engine='pyarrow')
    ticker = fn.stem

    # get rvol 14 ma for first 5 minutes
    df['dt'] = df['quote_datetime'].astype('datetime64[ns]')
    min_of_day = df["dt"].dt.hour * 60 + df["dt"].dt.minute
    mask = (min_of_day >= 570) & (min_of_day <= 574)
    df5 = df.loc[mask, ['symbol', 'dt', 'volume']]
    df5['quote_datetime'] = df5['dt'].dt.normalize()
    vol5 = df5.groupby(["symbol", "quote_datetime"], sort=True)["volume"].sum().rename("vol_5").reset_index()
    vol5 = vol5.sort_values(["symbol", "quote_datetime"])
    vol5['mean_14'] = vol5.groupby('symbol')['vol_5'].transform(lambda x: x.rolling(14, min_periods=14).mean().shift(1)) # shift so we don't peek into the future
    vol5["rvol_5"] = vol5["vol_5"] / vol5["mean_14"]

    df.set_index('quote_datetime', inplace=True)
    df.sort_index(inplace=True)

    daily_fn = daily_folder.joinpath(f'{ticker}_.parquet')
    df_daily = pd.read_parquet(daily_fn, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume', 'close_orig'], engine='pyarrow')
    df_daily = df_daily.merge(vol5, on=['symbol', 'quote_datetime'], how='inner')
    df_daily['rvol_signal'] = df_daily['rvol_5'] > r_vol_limit

    df_daily.set_index('quote_datetime', inplace=True)
    df_daily.sort_index(inplace=True)
    df_daily['atr'] = talib.ATR(df_daily['high'].to_numpy(float), df_daily['low'].to_numpy(float), df_daily['close'].to_numpy(float),
                                timeperiod=14)

    df_daily = df_daily[(df_daily.index >= start_date) & (df_daily.index <= end_date)]
    df = df[(df.index >= start_date) & (df.index <= end_date)]

    dts = df_daily.index

    equity = starting_equity
    trades = []
    for dt in dts:
        df_dt = df[df.index.normalize() == dt]
        daily = df_daily.loc[dt]
        if not daily['rvol_signal']:
            continue

        open_dt = pd.Timestamp(f"{dt.date()} {open_time}")
        entry_dt = pd.Timestamp(f"{dt.date()} {or_close}")
        close_dt = pd.Timestamp(f"{dt.date()} {close_time}")
        valid_dt = pd.Timestamp(f"{dt.date()} {valid_entry_time}")
        exit_dt = pd.Timestamp(f"{dt.date()} {exit_trade_time}")

        # First 5-min candle
        first_window = df_dt.loc[open_dt: open_dt + pd.Timedelta(minutes=first_candle_minutes) - pd.Timedelta(minutes=1)]
        o1 = float(first_window["open"].iloc[0])
        c1 = float(first_window["close"].iloc[-1])
        h1 = float(first_window["high"].max())
        l1 = float(first_window["low"].min())
        or_range = h1 - l1
        atr = daily['atr']

        direction = "skip" if c1 == o1 else "long" if c1 > o1 else "short"
        buffer = 0.10 * atr
        valid_scan = df_dt.loc[entry_dt:valid_dt]

        if direction == "skip":
            continue
        elif direction == "long":
            target_entry = h1 + buffer
            entry_px = max(target_entry, o1)
            stop_px = entry_px - (s * atr)
            valid_s = valid_scan['high'] >= entry_px
            valid = any(valid_s)
        elif direction == "short":
            target_entry = l1 - buffer
            entry_px = min(target_entry, o1)
            stop_px = entry_px + (s * atr)
            valid_s = valid_scan['low'] <= entry_px
            valid = any(valid_s)

        if not valid:
            continue

        entry_dt = first_true_ts(valid_s)
        stop_scan = df_dt.loc[entry_dt:exit_dt].copy()[1:]
        if direction == "long":
            stop_scan.loc[stop_scan['low'] <= stop_px, 'stop_hit'] = True
        else:
            stop_scan.loc[stop_scan['high'] >= stop_px, 'stop_hit'] = True
        stop_hit = stop_scan['stop_hit'].astype(bool).fillna(False)
        stop_dt = first_true_ts(stop_hit)
        if pd.isna(stop_dt):
            stop_dt = exit_dt
            exit_reason = "eod"
            exit_px = df_dt.loc[stop_dt, 'close']
        else:
            exit_reason = "stop"
            exit_px = stop_px

        # position sizing
        dollar_risk = equity * position_risk
        risk_per_share = abs(entry_px - stop_px)
        shares = max(0, int(np.floor(dollar_risk / risk_per_share)))

        if direction == "long":
            pnl = (exit_px - entry_px) * shares
        else:
            pnl = (entry_px - exit_px) * shares

        equity = equity + pnl

        trades.append({
            "symbol": ticker,
            "date": dt.date(),
            "direction": direction,
            "entry_dt": entry_dt,
            "entry_px": entry_px,
            "stop_px": stop_px,
            "exit_dt": stop_dt,
            "exit_px": exit_px,
            "shares": shares,
            "gross_pnl": pnl,
            "net_pnl": pnl,
            "fees": 0.0,
            "exit_reason": exit_reason,
            "equity_after": equity,
        })

        pass


