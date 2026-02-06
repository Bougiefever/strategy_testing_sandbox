import sys
import datetime
import pandas as pd
import numpy as np
from pathlib import Path
import talib
from utility import *

stock_folder = Path(r'D:\stock_data\intraday\stocks\sp500')
daily_folder = Path(r'D:\stock_data\daily_stock_prices')
data_fn = Path(r'D:\test_data\day_trading\orb_rvol_sp500.parquet')
stock_files = list(stock_folder.glob('*.parquet'))

open_time = datetime.time(9, 30)
or_close = datetime.time(9, 35)
valid_entry_time = datetime.time(10, 30)
exit_trade_time = datetime.time(15, 55)

start_date = datetime.datetime(2021, 1, 1)
end_date = datetime.datetime(2024, 1, 1)

rvol_days = 14
r_vol_limit = 1.5
first_candle_minutes = 5

rows= []
for fn in stock_files:
    ticker = fn.stem
    print(ticker)

    daily_fn = daily_folder.joinpath(f'{ticker}_.parquet')
    if not daily_fn.exists():
        continue

    df_daily = pd.read_parquet(daily_fn, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume',
                                                  'close_orig'], engine='pyarrow')
    df_daily.set_index('quote_datetime', inplace=True)
    df_daily.sort_index(inplace=True)
    df_daily['atr'] = talib.ATR(df_daily['high'].to_numpy(float), df_daily['low'].to_numpy(float),
                                df_daily['close'].to_numpy(float),
                                timeperiod=14)
    df_daily = df_daily[pd.Timestamp(start_date):pd.Timestamp(end_date)]

    df = pd.read_parquet(fn, engine='pyarrow')
    df.set_index('quote_datetime', inplace=True)
    df.sort_index(inplace=True)
    df = df[pd.Timestamp(start_date):pd.Timestamp(end_date) + pd.Timedelta(days=1)]

    df["session"] = df.index.normalize()
    df['dt'] = df.index.astype('datetime64[ns]')
    min_of_day = df["dt"].dt.hour * 60 + df["dt"].dt.minute
    mask = (min_of_day >= 570) & (min_of_day <= 574)
    df5 = df.loc[mask, ['symbol', 'dt', 'volume']].copy()
    df5.index= df5.index.normalize()
    vol5 = df5.groupby(["symbol", "quote_datetime"], sort=True)["volume"].sum().rename("vol_5").reset_index()
    vol5 = vol5.sort_values(["symbol", "quote_datetime"])
    vol5['mean_14'] = vol5.groupby('symbol')['vol_5'].transform(
        lambda x: x.rolling(14, min_periods=14).mean().shift(1))  # shift so we don't peek into the future
    vol5["rvol_5"] = vol5["vol_5"] / vol5["mean_14"]


    df_daily = df_daily.merge(vol5, on=['symbol', 'quote_datetime'], how='inner')
    df_daily['rvol_signal'] = df_daily['rvol_5'] > r_vol_limit
    df_daily.set_index('quote_datetime', inplace=True)
    df_daily.sort_index(inplace=True)

    for dt, df_dt in df.groupby("session", sort=True):
        try:
            daily = df_daily.loc[dt]
            atr = daily['atr']

            open_dt = pd.Timestamp(f"{dt.date()} {open_time}")
            entry_dt = pd.Timestamp(f"{dt.date()} {or_close}")
            valid_dt = pd.Timestamp(f"{dt.date()} {valid_entry_time}")
            exit_dt = pd.Timestamp(f"{dt.date()} {exit_trade_time}")

            # First 5-min candle
            first_window = df_dt.loc[open_dt: open_dt + pd.Timedelta(minutes=first_candle_minutes) - pd.Timedelta(minutes=1)]
            o1 = float(first_window["open"].iloc[0])
            c1 = float(first_window["close"].iloc[-1])
            h1 = float(first_window["high"].max())
            l1 = float(first_window["low"].min())

            if c1 == o1:
                direction = "skip"
            elif c1 > o1:
                direction = "long"
            else:
                direction = "short"

            buffer = 0.10 * atr
            vol_5 = daily["vol_5"]
            mean_14 = daily["mean_14"]
            rvol_5 = daily["rvol_5"]
            valid_scan = df_dt[(df_dt.index > entry_dt) & (df_dt.index < valid_dt)]

            target_entry = h1 + buffer if direction == "long" else l1 - buffer
            entry_bar_open = df_dt.iloc[first_candle_minutes]['open']
            entry_px = max(target_entry, entry_bar_open) if direction == "long" else min(target_entry, entry_bar_open)
            valid_s = valid_scan['high'] >= entry_px if direction == "long" else valid_scan['low'] <= entry_px
            entry_dt = first_true_ts(valid_s)

            triggered_by_1030 = (any(valid_s)) & (rvol_5 > r_vol_limit)  & (direction != "skip")

            row = {
                "session": dt,
                "symbol": ticker,
                "atr": atr,
                "vol_5": vol_5,
                "mean_14": mean_14,
                "rvol_5": rvol_5,
                "direction": direction,
                "entry_px": entry_px,
                "entry_dt": entry_dt,
                "triggered_by_1030": triggered_by_1030,
            }
            rows.append(row)
        except Exception as e:
            print(ticker, e)
            if type(e) == KeyError:
                continue
            raise

df_data = pd.DataFrame(rows)
df_data = df_data.sort_values(by=['session', 'rvol_5'], ascending=[True, False])
df_data['rank_rvol'] = df_data.groupby("session").cumcount().add(1)
df_data['in_play'] = (df_data["rvol_5"] > r_vol_limit) & (df_data["rank_rvol"] <= 5) & (df_data["direction"] != "skip")
df_data["has_trade"] = df_data["in_play"] & df_data["triggered_by_1030"]
df_data.sort_values(by=['session', 'symbol'], inplace=True)
df_data.to_parquet(data_fn, engine='pyarrow')
