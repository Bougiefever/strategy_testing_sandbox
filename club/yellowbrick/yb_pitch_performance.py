import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path

output_folder = Path(r'D:\test_data\yellowbrick')

stock_data = Path(r'D:\stock_data\daily')
df_spy = pd.read_parquet(stock_data.joinpath('SPY.parquet'), engine='pyarrow', columns=['quote_datetime', 'close'])
df_spy = df_spy.drop_duplicates(subset='quote_datetime', keep='last')
df_spy.set_index('quote_datetime', inplace=True)
df_spy.sort_index(inplace=True)


yb_signals_fn = Path(r'D:\projects\club\Yellowbrick\yb_data_dates.csv')
df_yb = pd.read_csv(yb_signals_fn, parse_dates=['pitch_date'])
df_yb = pd.read_csv(yb_signals_fn, parse_dates=['pitch_date'])
df_yb.set_index('pitch_date', inplace=True)
df_yb.sort_index(inplace=True)
df_yb = df_yb[(df_yb['sentiment'] == 'bearish') | (df_yb['sentiment'] == 'bullish')]
df_yb.drop(columns=['company_name'], inplace=True)
dts = [x.to_pydatetime() for x in df_yb.index.unique()]

dtypes = {
   'tip_id': 'int64',
   'contributor': 'str',
   'ticker': 'str',
   'tip_date': 'datetime64[ns]',
   'sentiment': 'str',
   'day': 'int64',
   'date': 'datetime64[ns]',
   'stock_rtn': 'float64',
   'spy_rtn': 'float64',
   'excess_rtn': 'float64',
}

df_returns = pd.DataFrame(columns=dtypes.keys()).astype(dtypes)

for dt in dts:
   print(dt)
   end_dt = dt + timedelta(weeks=52)
   spy = df_spy[(df_spy.index >= dt) & (df_spy.index <= end_dt)]
   benchmark = pd.Series(spy['close'] / spy['close'].iloc[0] - 1, name='spy_rtn')

   yb_dt = df_yb.loc[dt:dt]
   for _, row in yb_dt.iterrows():
      tip_id = row['id']
      ticker = row['ticker']
      contributor = row['author_name']
      sentiment = row['sentiment']
      direction = 1 if sentiment == 'bullish' else -1

      fn = stock_data.joinpath(f'{ticker}.parquet')
      if fn.exists():
         print(ticker)
         df = pd.read_parquet(fn, engine='pyarrow', columns=['quote_datetime', 'close'])
         df = df.drop_duplicates(subset='quote_datetime', keep='last')
         df = df[(df['quote_datetime'] >= dt) & (df['quote_datetime'] <= end_dt)]
         if len(df) == 0:
            continue
         df.set_index('quote_datetime', inplace=True)
         df.sort_index(inplace=True)

         rtn = pd.Series(df['close'] / df['close'].iloc[0] - 1, name='rtn')
         bm = benchmark.loc[benchmark.index.isin(df.index)]
         excess = direction * (rtn - bm)

         return_data = pd.DataFrame(index=df.index)
         return_data['tip_id'] = tip_id
         return_data['contributor'] = contributor
         return_data['ticker'] = ticker
         return_data['tip_date'] = dt
         return_data['sentiment'] = sentiment
         return_data['day'] = range(0, len(df))
         return_data['date'] = return_data.index
         return_data['stock_rtn'] = rtn
         return_data['spy_rtn'] = bm
         return_data['excess_rtn'] = excess
         return_data.reset_index(drop=True)
         df_returns = pd.concat([df_returns, return_data], ignore_index=True)

df_returns.to_parquet(r'D:\projects\club\Yellowbrick\yb_returns.parquet', engine='pyarrow', index=False)
df_returns.to_csv(r'D:\projects\club\Yellowbrick\yb_returns.csv', index=False)





