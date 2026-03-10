import pandas as pd
from pathlib import Path
import talib

base_ticker = 'QQQ'
leveraged_ticker = 'SQQQ'

stock_folder = Path(r'D:\stock_data\daily')
fast_period = 12
slow_period = 26
signal_period = 9


base_fn = stock_folder.joinpath(f'{base_ticker}.parquet')
df_base = pd.read_parquet(base_fn, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume'], engine='pyarrow')
df_base.set_index('quote_datetime', inplace=True)
df_base.sort_index(inplace=True)
df_base['200ma'] = talib.SMA(df_base['close'].to_numpy(float), timeperiod=200)
df_base['50ma'] = talib.SMA(df_base['close'].to_numpy(float), timeperiod=50)
df_base['macd'], df_base['macd_signal'], df_base['macd_hist'] = talib.MACD(df_base['close'].to_numpy(float), fast_period,
                                                                        slow_period, signal_period)

lev_fn = stock_folder.joinpath(f'{leveraged_ticker}.parquet')
df_lev = pd.read_parquet(lev_fn, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume'], engine='pyarrow')
df_lev = df_lev.rename(columns={'open': 'lev_open', 'high': 'lev_high', 'low': 'lev_low', 'close': 'lev_close', 'volume': 'lev_volume'})
df_lev.set_index('quote_datetime', inplace=True)
df_lev.sort_index(inplace=True)

start_date = df_lev.iloc[0].name.to_pydatetime()

df = df_base.merge(df_lev, on='quote_datetime', how='inner')

filter1 = df['close'] < df['200ma']
filter2 = df['50ma'] < df['200ma']
filter3 = df['macd'] < 0

filters = [('QQQ < 200 SMA',filter1), ('QQQ Death Cross',filter2), ('QQQ MACD < 0',filter3)]

returns = [1, 3, 5, 10, 20]

results = []
for filter_name, fltr in filters:
    df_ = df.copy()
    active_pct = fltr.mean()
    for r in returns:
        field_name = f'{r}_day_return'
        df_[field_name] = df_['lev_close'].pct_change(r)
        df_active = df_[fltr]
        df_inactive = df_[~fltr]
        active_rtn = df_active[field_name].mean()
        inactive_rtn = df_inactive[field_name].mean()
        results.append({
            'filter_name': filter_name,
            'active_pct': active_pct,
            'return_days': r,
            'active_avg_return': active_rtn,
            'inactive_avg_return': inactive_rtn,
        })

years = df.index.isocalendar().year.unique().tolist()

results = []
for yr in years:
    df_ = df[df.index.isocalendar().year == yr]
    fltr = df_['macd'] < 0
    active_pct = fltr.mean()
    for r in returns:
        field_name = f'{r}_day_return'
        df_[field_name] = df_['lev_close'].pct_change(r)
        df_active = df_[fltr]
        df_inactive = df_[~fltr]
        active_rtn = df_active[field_name].mean()
        inactive_rtn = df_inactive[field_name].mean()
        results.append({
            'year': yr,
            'active_pct': active_pct,
            'return_days': r,
            'active_avg_return': active_rtn,
            'inactive_avg_return': inactive_rtn,
        })



pass

