import pandas as pd
import numpy as np
from pathlib import Path
import pyarrow.parquet as pq
import pyarrow as pa
from glob import glob
import datetime

start_date = datetime.datetime(2023, 1, 1)
end_date = datetime.datetime(2025, 1, 1)
front_month_dte = 30
back_month_dte = 60
buffer = 5

# fix earnings dates
earnings_file = Path(r'D:\stock_data\earnings_dates.csv')

# get market dates for the time range - ff will have gaps
spy_daily_fn = Path(r'D:\stock_data\daily_stock_prices\SPY_.parquet')
_spy = pd.read_parquet(spy_daily_fn, engine="pyarrow")
_spy.set_index('quote_datetime', inplace=True)
_spy.sort_index(inplace=True)
dts = _spy.loc[start_date:end_date].index.values.tolist()
df_earn = pd.read_csv(earnings_file, parse_dates=['date', 'effective_date'])
df_earn['effective_date'] = pd.to_datetime(df_earn['effective_date'])
df_earn = df_earn.sort_values(by=['effective_date', 'symbol'])
df_earn.dropna(subset=['effective_date'], inplace=True)

# df_earn['effective_date'] = pd.NaT
# df_earn_ = df_earn.copy()
# for row in df_earn_.itertuples():
#     id_ = row[0]
#     dt = row.date
#     bmo_amc = row.BMO_AMC
#     print(id_, dt, row.symbol)
#     if bmo_amc == 'AMC':
#         dt = dt + pd.Timedelta(days=1) # move to next day for effective date, the day the market has the earnings data
#     if dt > _spy.index.max():
#         continue
#     has_date = False
#     while not has_date:
#         try:
#             _spy.loc[dt]
#             df_earn.loc[id_, 'effective_date'] = dt
#             has_date = True
#         except KeyError:
#             dt = dt + pd.Timedelta(days=1)
#             has_date = False



# ff_folder = Path(r'D:\test_data\forward_factor\source_files')
# files = list(ff_folder.glob('*'))
# ta = pq.read_table(files)
ta = pq.read_table(r'D:\test_data\forward_factor\ff.parquet')
df_forward_factor = ta.to_pandas()
# df_forward_factor['symbol'] = df_forward_factor['symbol'].astype(str)
df_forward_factor["quote_datetime"] = df_forward_factor["quote_datetime"].astype("datetime64[ns]")
#df_forward_factor.set_index('quote_datetime', inplace=True)
df_forward_factor = df_forward_factor.sort_values(by=['quote_datetime', 'symbol'])
df_forward_factor = df_forward_factor[(df_forward_factor['quote_datetime'] >= start_date) & (df_forward_factor['quote_datetime'] <=end_date)]

df_forward_factor = df_forward_factor[(df_forward_factor['front_dte'] >= (front_month_dte - buffer)) & (df_forward_factor['front_dte'] <= (front_month_dte + buffer))]
df_forward_factor = df_forward_factor[(df_forward_factor['back_dte'] >= (back_month_dte - buffer)) & (df_forward_factor['back_dte'] <= (back_month_dte + buffer))]


mrg = pd.merge_asof(
    df_forward_factor,
    df_earn,
    left_on="quote_datetime",
    right_on="effective_date",
    by="symbol",
    direction="forward",
    allow_exact_matches=True,
)

earn_in_window = mrg['date'].notna() & (mrg['effective_date'] <= mrg['back_exp'])

#test = df_ff[['quote_datetime', 'symbol', 'front_exp', 'back_exp']]

# for row in df_ff.itertuples():
#     id_ = row[0]
#     front_dt = row.quote_datetime
#     back_dt = row.back_exp
#     symbol = row.symbol
#     earns = df_earn[(df_earn['symbol'] == symbol) & (df_earn['date'] >= front_dt) & (df_earn['date'] <= back_dt)]
#     if not earns.empty:
#         df_ff.drop(index=id_)
df_filtered = mrg.loc[~earn_in_window]
df_filtered = df_filtered.drop(columns=['date', 'when', 'BMO_AMC'])

df_filtered.to_parquet(r'D:\test_data\forward_factor\ff_30_60.parquet')
