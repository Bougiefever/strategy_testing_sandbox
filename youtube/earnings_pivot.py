import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
import datetime
import talib
from utility import *

# get the earnings data
earn_data_fn = Path(r'D:\stock_data\earnings_data.csv')
stock_data_folder = Path(r'D:\stock_data\daily_stock_prices')
df_earn = pd.read_csv(earn_data_fn, index_col='Earnings_Date', parse_dates=True)
df_earn.sort_values(by=['Earnings_Date', 'Symbol'], inplace=True)
start_date = pd.to_datetime(datetime.datetime(2021, 5, 11))

# get stock market open days from SPY daily
spy_daily_fn = Path(r'D:\stock_data\daily_stock_prices\SPY_.parquet')
_spy = pd.read_parquet(spy_daily_fn, engine="pyarrow")
_spy.set_index('quote_datetime', inplace=True)
_spy.sort_index(inplace=True)
dts = _spy.loc[start_date:].index.values.tolist()

# df_earn['trade_date'] = pd.NaT
# for row in df_earn.itertuples():
#     dt = row[0]
#     when = row.BMO_AMC
#     ticker = row.Symbol
#     if when == "BMO":
#         trade_dt = dt
#     elif when == "AMC":
#         find_dt = dt
#         if find_dt not in _spy.index:
#             while find_dt not in _spy.index:
#                 find_dt = find_dt + pd.Timedelta(days=1) # data has day before for AMC date, which is sometimes not a market day
#             trade_dt = find_dt
#         else:
#             i = _spy.index.get_loc(find_dt)
#             trade_dt = _spy.iloc[i+1].name
#     else:
#         trade_dt = pd.NaT
#
#     df_earn.loc[(df_earn.index == dt) & (df_earn['Symbol'] == ticker), 'trade_date'] = trade_dt



# get all the stock data
symbols = df_earn['Symbol'].unique()
#symbols = df_earn.loc[pd.to_datetime(start_date) + pd.Timedelta(days=1), 'Symbol'].tolist()
dfs = defaultdict(pd.DataFrame)
for symbol in symbols[:]:
    fn = stock_data_folder.joinpath(f'{symbol}_.parquet')
    if not fn.exists():
        continue
    df_stock = pd.read_parquet(fn, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume', 'close_orig'], engine="pyarrow")
    df_stock.set_index('quote_datetime', inplace=True)
    df_stock.sort_index(inplace=True)
    df_stock['adv_30d'] = (df_stock['volume'].rolling(window=30, min_periods=30).mean()*df_stock['close_orig']).shift(1)
    df_stock['atr'] = talib.ATR(df_stock['high'].to_numpy(float), df_stock['low'].to_numpy(float),
                                df_stock['close'].to_numpy(float),
                                timeperiod=14)
    df_stock['atr'] = df_stock['atr'].shift(1)# shift back one day - this is what you would know before trading decision
    df_stock = df_stock.dropna()
    df_stock = df_stock[df_stock.index >= start_date]
    dfs[symbol] = df_stock

open_time = datetime.time(9, 30)
close_time = datetime.time(16, 0)
position_risk = 0.01
starting_equity = 100_000
equity = starting_equity
trades = []


for dt in dts:
    dt_earn = df_earn.loc[dt:dt]
    for row in dt_earn.itertuples():
        ticker = row.Symbol
        when = row.BMO_AMC
        trade_dt = row.trade_date
        if trade_dt == pd.NaT:
            print(f'{dt}, {ticker} ***********************************************************  no trade date')
            continue
        print(dt, ticker, equity)

        df = dfs.get(ticker)
        if df is None:
            continue
        df_row = df.loc[trade_dt]

        roc_ma = row.ROC_100D_SMA
        gap = row.Earnings_Gap_Pct
        earn_surprise = row.Earnings_Surprise_Pct
        rev_surprise = row.Revenue_Surprise_Pct

        long_ok = (roc_ma >= -10) & (gap >= 10)
        if long_ok:
            if earn_surprise >= 100 or rev_surprise >= 20:
                long_ok = True
            elif earn_surprise >= 50 and rev_surprise >= 5:
                long_ok = True
            else:
                long_ok = False

        short_ok = (roc_ma <= 0) & (gap <= -5) & (earn_surprise <= -20) & (rev_surprise <= -5)

        if long_ok or short_ok:
            entry_px = df_row['open']
            high_px = df_row['high']
            low_px = df_row['low']
            #exit_px = df_row['close']
            direction = "short" if short_ok else "long"
            entry_dt = pd.Timestamp(f"{df_row.name.date()} {open_time}")
            exit_dt = pd.Timestamp(f"{df_row.name.date()} {close_time}")
            exit_reason = 'eod'
            atr = df_row['atr']
            stop_px = entry_px + atr*1.5 if short_ok else entry_px - atr*1.5

            # position sizing
            dollar_risk = equity * position_risk
            risk_per_share = abs(entry_px - stop_px)
            shares = max(0, int(np.floor(dollar_risk / risk_per_share)))

            if short_ok:
                if high_px >= stop_px:
                    exit_px = stop_px
                    exit_reason = 'stop'
                else:
                    exit_px = df_row['close']
                    exit_reason = 'eod'
            else:
                if low_px <= stop_px:
                    exit_px = stop_px
                    exit_reason = 'stop'
                else:
                    exit_px = df_row['close']
                    exit_reason = 'eod'
            pnl = (entry_px - exit_px) * shares if short_ok else (exit_px - entry_px) * shares
            equity = equity + pnl

            trades.append({
                "symbol": ticker,
                "date": df_row.name.date(),
                "direction": direction,
                "entry_dt": entry_dt,
                "entry_px": entry_px,
                "stop_px": stop_px,
                "exit_dt": exit_dt,
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

trades_df.to_csv(r'D:\test_data\earnings\trades_daily.csv')
