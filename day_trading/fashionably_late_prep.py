"""

The Fashionably Late Scalp trade requires a stock with a strong daily chart setup with a pullback to the 5 EMA

This script finds the stocks that meet this criteria.

"""

from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
import talib

daily_stock_dir = r'D:\stock_data\daily'
daily_stock_files = [x for x in Path(daily_stock_dir).iterdir() if x.is_file()]

df_trade_dates = pd.DataFrame({
   'trade_dt': pd.Series(dtype='datetime64[ns]'),
   'symbol': pd.Series(dtype='str'),
})

dfs = []

for sf in daily_stock_files:
   ticker = sf.stem
   print(ticker)
   df = pd.read_parquet(sf, engine='pyarrow', columns=['quote_datetime', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'close_orig'])
   if len(df) < 252:
      continue
   ema5 = talib.EMA(df['close'].to_numpy(), timeperiod=5)
   vol20ma = talib.SMA(df['volume'].astype(float).to_numpy(), timeperiod=20)
   df['atr'] = talib.ATR(df['high'].to_numpy(), df['low'].to_numpy(), df['close'].to_numpy(), timeperiod=14)
   close = df['close']
   low = df['low']
   close_3mo = close.shift(63)
   close_6mo = close.shift(126)
   pct_gain_3mo = (close - close_3mo) / close_3mo
   pct_gain_6mo = (close - close_6mo) / close_6mo

   cond_uptrend_3mo = close > close_3mo
   cond_uptrend_6mo = close > close_6mo
   cond_gain_3mo = pct_gain_3mo >= 0.30
   cond_gain_6mo = pct_gain_6mo >= 0.30
   cond_pullback = low <= ema5
   cond_vol = vol20ma >= 500_000
   px_cond = df['close_orig'] >= 5.0
   df['trade_dt'] = df['quote_datetime'].shift(-1)
   df = df[(cond_uptrend_3mo & cond_uptrend_6mo) & (cond_gain_3mo | cond_gain_6mo) & cond_pullback & cond_vol & px_cond]
   if len(df) == 0:
      continue

   df = df[['trade_dt', 'symbol', 'atr']]
   dfs.append(df)

trade_dt_fn = r'D:\projects\data\fashionably_late\trade_dts.parquet'
df_trades = pd.concat(dfs)
df_trades.sort_values(by=['symbol', 'trade_dt'], inplace=True)
df_trades.to_parquet(trade_dt_fn, engine='pyarrow')

