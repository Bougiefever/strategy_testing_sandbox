import pandas as pd
import numpy as np
from pathlib import Path
import datetime
import pyarrow as pa
from pyarrow import parquet as pq
from pyarrow import compute as pc
import math
import talib

stock_folder = Path(r'D:\stock_data\daily')
earnings_file = stock_folder.parent.joinpath('earnings_dates.csv')
start_date = datetime.datetime(2020, 1, 1)
end_date = datetime.datetime(2026, 12, 31)

# spy_daily_fn = stock_folder.joinpath('SPY_.parquet')
# _spy = pd.read_parquet(spy_daily_fn, engine="pyarrow")
# _spy.set_index('quote_datetime', inplace=True)
# _spy.sort_index(inplace=True)
# dts = _spy.loc[start_date:end_date].index.values.tolist()

df_earn = pd.read_csv(earnings_file, parse_dates=['date', 'effective_date'], index_col="effective_date")
df_earn.sort_values(by=['effective_date', 'symbol'], inplace=True)
df_earn.reset_index(inplace=True)


tickers = df_earn['symbol'].unique().tolist()
tickers.sort()

results = []
for ticker in tickers:
    print(ticker)
    # get stock data file
    fn = stock_folder.joinpath(f'{ticker}_.parquet')
    if not fn.exists():
        continue
    df = pd.read_parquet(fn, engine="pyarrow", columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume', 'close_orig'])
    # df.set_index('quote_datetime', inplace=True)
    # df.sort_index(inplace=True)
    df = df[(df['quote_datetime'] >= start_date) & (df['quote_datetime'] <= end_date)]

    # calculate
    df['vol_20_ma'] = talib.SMA(df['volume'].to_numpy(float), timeperiod=20)
    df['prev_close'] = df['close'].shift(1)

    df_ticker = df_earn[df_earn['symbol'] == ticker]
    merged = df_ticker.merge(df[['quote_datetime', 'symbol', 'open', 'low', 'prev_close', 'vol_20_ma']], how='left', left_on=['symbol', 'effective_date'], right_on=['symbol', 'quote_datetime'])
    merged.dropna(subset=["open", "prev_close"])
    merged['gap_pct'] = (merged['open'] - merged['prev_close']) / merged['prev_close']
    merged = merged[(merged['gap_pct'] >= 0.10) | (merged['gap_pct'] <= -0.10)]
    merged = merged[merged['vol_20_ma'] > 1_000_000]

    if len(merged) > 0:
        results.append(merged)

output_fn = Path(r'D:\test_data\basic\pead\signals.csv')
signals = pd.concat(results)
signals.to_csv(output_fn, index=False)






