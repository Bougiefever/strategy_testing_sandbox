import sys
import datetime
import pandas as pd
import numpy as np
from pathlib import Path
import talib
from utility import *
import pyarrow.parquet as pq
from collections import defaultdict

pd.options.mode.chained_assignment = None

data_fn = Path(r'D:\test_data\day_trading\orb_rvol_sp500.parquet')
stock_folder = Path(r'D:\stock_data\intraday\stocks\sp500')
stock_files = list(stock_folder.glob('*.parquet'))

dfs = defaultdict(pd.DataFrame)
for fn in stock_files:
    ticker = fn.stem
    df = pd.read_parquet(fn, engine='pyarrow')
    df.set_index('quote_datetime', inplace=True)
    df.sort_index(inplace=True)
    dfs[ticker] = df

df_slices = pd.read_parquet(data_fn, engine='pyarrow')

n = 5
position_risk = 0.1
s = 0.15
exit_trade_time = datetime.time(15, 55)

starting_equity = 100_000
equity = starting_equity

dts = df_slices['session'].dt.normalize()
dts = dts.unique().tolist()

trades = []
for dt in dts:
    print(dt)
    dt_slice = df_slices[df_slices['session'] == dt]
    dt_slice = dt_slice.sort_values(by='rank_rvol')[:n]
    exit_dt = pd.Timestamp(f"{dt.date()} {exit_trade_time}")
    if any(dt_slice['has_trade']):
        for _, row in dt_slice.iterrows():
            has_trade = row['has_trade']
            if not has_trade:
                continue
            ticker = row['symbol']
            direction = row['direction']
            atr = row['atr']
            entry_px = row['entry_px']
            entry_dt = row['entry_dt']
            stop_px = entry_px - (s * atr) if direction == 'long' else entry_px + (s * atr)
            df = dfs[ticker]
            stop_scan = df.loc[entry_dt:exit_dt].copy()[1:]
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

trades_df = pd.DataFrame(trades)
stats = trade_stats(trades_df)
print(stats)

trades_fn = Path(r'D:\test_data\day_trading\trades2.csv')
trades_df.to_csv(trades_fn, index=False)

