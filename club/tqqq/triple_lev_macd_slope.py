import numpy as np
import pandas as pd
from scipy.stats import linregress, pearsonr
from pathlib import Path
import talib
import datetime

data_folder = Path(r'D:\stock_data\daily')

start_date = datetime.datetime(2018, 1, 2)

base_ticker = "QQQ"
lev_ticker = "TQQQ"
fast_period = 12
slow_period = 26
signal_period = 9
lin_regress_lookback = 10
drawdown_lookback = 52

base_df = pd.read_parquet(data_folder.joinpath(f'{base_ticker}.parquet'), engine='pyarrow')
base_df.set_index('quote_datetime', inplace=True)

lev_df = pd.read_parquet(data_folder.joinpath(f'{lev_ticker}.parquet'), engine='pyarrow')
lev_df.set_index('quote_datetime', inplace=True)
lev_df = lev_df.loc[start_date:]

df = base_df[['close']].rename(columns={'close': 'base_close'})
df['lev_close'] = lev_df['close']


df['base_macd'], df['base_macd_signal'], df['macd_hist'] = talib.MACD(df['base_close'].to_numpy(float), fast_period,
                                                                        slow_period, signal_period)

df['base_peak'] = df['base_close'].rolling(drawdown_lookback).max()
df['base_drawdown'] = (df['base_close'] - df['base_peak']) / df['base_peak']
df = df.dropna()

df['base_macd_slope'] = df['base_macd'].rolling(window=lin_regress_lookback).apply(lambda x:
                         linregress(np.arange(lin_regress_lookback), x).slope, raw=True)

df['lev_macd'], df['lev_macd_signal'], df['lef_macd_hist'] = talib.MACD(df['lev_close'].to_numpy(float), fast_period,
                                                                        slow_period, signal_period)

df['lev_macd_slope'] = df['lev_macd'].rolling(window=lin_regress_lookback).apply(lambda x:
                         linregress(np.arange(lin_regress_lookback), x).slope, raw=True)

drawdown_threshold = -0.075
flatten_threshold = 0.025

position = False
peak_lev_slope = 0
entry_price = 0
entry_date = None
trades = []

for i in range(len(df)):
    row = df.iloc[i]

    # Skip rows with NaN indicators
    if pd.isna(row['base_macd_slope']) or pd.isna(row['lev_macd_slope']):
        continue

    if not position:
        # Entry: QQQ drawdown + negative MACD slope
        if row['base_drawdown'] < drawdown_threshold and row['base_macd_slope'] < 0:
            position = True
            entry_px = row['lev_close']
            entry_dt = df.index[i]
            peak_lev_slope = 0

    else:
        if row['lev_macd_slope'] > peak_lev_slope:
            peak_lev_slope = row['lev_macd_slope']

        if peak_lev_slope > flatten_threshold and row['lev_macd_slope'] <= flatten_threshold:
            exit_px = row['lev_close']
            exit_dt = df.index[i]
            pct_return = (exit_px - entry_px) / entry_px

            trades.append({
                'entry_date': entry_dt,
                'exit_date': exit_dt,
                'entry_price': entry_px,
                'exit_price': exit_px,
                'return': pct_return,
                'weeks_held': (exit_dt - entry_dt).days / 7,
                'peak_slope': peak_lev_slope
            })

            position = False
            peak_lev_slope = 0

trades_df = pd.DataFrame(trades)

print(f"Total trades: {len(trades_df)}")
print(f"Win rate: {(trades_df['return'] > 0).mean():.1%}")
print(f"Mean return: {trades_df['return'].mean():.2%}")
print(f"Median return: {trades_df['return'].median():.2%}")
print(f"Avg weeks held: {trades_df['weeks_held'].mean():.1f}")
print(f"Best trade: {trades_df['return'].max():.2%}")
print(f"Worst trade: {trades_df['return'].min():.2%}")
print()
print(trades_df.to_string(index=False))