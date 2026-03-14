import pandas as pd
import numpy as np
from pathlib import Path
import talib
from scipy.stats import linregress, pearsonr

def calc_regression(series):
    x = np.arange(len(series))
    slope, intercept, r_value, p_value, std_err = linregress(x, series)
    return pd.Series({'slope': slope, 'r_squared': r_value**2})


base_ticker = 'QQQ'
leveraged_ticker = 'SQQQ'

stock_folder = Path(r'D:\stock_data\daily')
fast_period = 12
slow_period = 26
signal_period = 9
lin_regress_lookback = 10

base_fn = stock_folder.joinpath(f'{base_ticker}.parquet')
df_base = pd.read_parquet(base_fn, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume'], engine='pyarrow')
df_base.set_index('quote_datetime', inplace=True)
df_base.sort_index(inplace=True)
df_base = df_base.resample('W-FRI').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum',
}).dropna()
df_base[f'{base_ticker}_macd'], df_base[f'{base_ticker}_macd_signal'], df_base['macd_hist'] = talib.MACD(df_base['close'].to_numpy(float), fast_period,
                                                                        slow_period, signal_period)

df_base['macd_reg_slope'] = df_base['macd'].rolling(window=lin_regress_lookback).apply(lambda x: linregress(np.arange(lin_regress_lookback), x).slope, raw=True)
df_base['macd_reg_r2'] = df_base['macd'].rolling(window=lin_regress_lookback).apply(lambda x: linregress(np.arange(lin_regress_lookback), x).rvalue ** 2, raw=True)
df_base['macd_slope_change'] = df_base['macd_reg_slope'].diff()

lev_fn = stock_folder.joinpath(f'{leveraged_ticker}.parquet')
df_lev = pd.read_parquet(lev_fn, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume'], engine='pyarrow')

df_lev.set_index('quote_datetime', inplace=True)
df_lev.sort_index(inplace=True)
df_lev = df_lev.resample('W-FRI').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum',
}).dropna()
df_lev = df_lev.rename(columns={'open': f'{leveraged_ticker}_open', 'high': f'{leveraged_ticker}_high', 'low': f'{leveraged_ticker}_low', 'close': f'{leveraged_ticker}_close', 'volume': f'{leveraged_ticker}_volume'})
close_field = f'{leveraged_ticker}_close'
macd_field = f'{base_ticker}_macd'
df_lev[f'{leveraged_ticker}_fwd_1day'] = df_lev[close_field].shift(-1) / df_lev[close_field] - 1
df_lev[f'{leveraged_ticker}_fwd_3day'] = df_lev[close_field].shift(-3) / df_lev[close_field] - 1
df_lev[f'{leveraged_ticker}_fwd_5day'] = df_lev[close_field].shift(-5) / df_lev[close_field] - 1
df_lev[f'{leveraged_ticker}_fwd_10day'] = df_lev[close_field].shift(-10) / df_lev[close_field] - 1
df_lev[f'{leveraged_ticker}_macd'], df_lev[f'{leveraged_ticker}_macd_signal'], df_lev[f'{leveraged_ticker}_macd_hist'] = talib.MACD(df_lev[close_field].to_numpy(float), fast_period,
                                                                         slow_period, signal_period)
df_lev[f'{leveraged_ticker}_macd_chg'] = df_lev[f'{leveraged_ticker}_macd'].diff(1)
start_date = df_lev.iloc[0].name.to_pydatetime()

df = df_base.merge(df_lev, on='quote_datetime', how='inner')

regime = False
results = []
for m in df[macd_field]:
    if m < 0 and not regime:
        regime = True
    elif m > 0.20 and regime:
        regime = False
    results.append(regime)

df['regime_on'] = results
# df['regime_on'] = (df['macd'] < 0)
df['regime_id'] = (df['regime_on'] != df['regime_on'].shift()).cumsum()
grouped = df[df['regime_on']].groupby('regime_id')
entry_price = grouped[close_field].transform('first')
peak_price = grouped[close_field].transform('max')

df['pct_captured'] = (df[close_field] - entry_price) / (peak_price - entry_price)
df.loc[df['pct_captured'] == -np.inf, 'pct_captured'] = np.nan

df_active = df[df['regime_on'] == True]
#df_inactive = df_[~fltr]
active_pct = df['regime_on'].mean()


labels = ['Q1', 'Q2', 'Q3', 'Q4']
df_active['macd_chg_quartile'] = pd.qcut(df_active[f'{leveraged_ticker}_macd_chg'], q=4, labels=labels)

df_result = df_active[[f'{base_ticker}_macd', close_field, f'{leveraged_ticker}_fwd_1day',
       f'{leveraged_ticker}_fwd_3day', f'{leveraged_ticker}_fwd_5day', f'{leveraged_ticker}_fwd_10day',
       f'{leveraged_ticker}_macd', f'{leveraged_ticker}_macd_signal', f'{leveraged_ticker}_macd_chg',
        'macd_chg_quartile', 'regime_on', 'regime_id', 'pct_captured']]

df_result['pct_captured'].loc[df_result['pct_captured'] == -np.inf] = np.nan
avg_pct_captured = df_result['pct_captured'].mean()
df_result.to_csv(r'D:\test_data\3x_short\data.csv', index=True)
