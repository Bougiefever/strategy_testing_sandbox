import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, time
import talib

from utility import first_true_ts

agg_rules = {
    "symbol": "first",
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",  # Often used alongside price data
    "vwap": "last"
}

equity = 100_000
max_risk = 0.01

trade_dt_fn = r'D:\projects\data\fashionably_late\trade_dts.parquet'
stocks_dir = Path(r'D:\stock_data\intraday\market\stocks')

signals_df = pd.read_parquet(trade_dt_fn, engine='pyarrow')
symbols = list(signals_df['symbol'].unique())
symbols.sort()

stock_file_symbols = [x.stem for x in stocks_dir.glob('*.parquet')]

test_symbols = [s for s in symbols if s in stock_file_symbols]

trades = []
for symbol in test_symbols:
    stock_signals_df = signals_df[signals_df['symbol'] == symbol]
    stock_fn = stocks_dir / f'{symbol}.parquet'
    stock_df = pd.read_parquet(stock_fn, engine='pyarrow')


    for _, signal in stock_signals_df.iterrows():
        trade_dt = signal['trade_dt']
        atr = signal['atr']
        dt_norm = trade_dt.normalize()
        df = stock_df[stock_df['quote_datetime'].dt.normalize() == dt_norm]

        # calculate vwap
        df = df.sort_values('quote_datetime')
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['typ_vol'] = df['typical_price'] * df['volume']
        df['cum_tp_vol'] = df.groupby(df['quote_datetime'].dt.date)['typ_vol'].cumsum()
        df['cum_vol'] = df.groupby(df['quote_datetime'].dt.date)['volume'].cumsum()
        df['vwap'] = df['cum_tp_vol'] / df['cum_vol']

        df = df[['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume', 'vwap']].resample('2min', on='quote_datetime').agg(agg_rules).reset_index()

        # calculate 9 ema and slope
        df['ema9'] = talib.EMA(df['close'].to_numpy(), timeperiod=9)
        df['slope'] = (df['ema9'] - df['ema9'].shift(-5)) / atr

        df.set_index('quote_datetime', inplace=True)

        start_time = time(10, 30)
        end_time = time(13, 30)

        scan_window = df[(df.index.time >= start_time) & (df.index.time <= end_time)]

        scan = (scan_window['ema9'] > scan_window['vwap']) & (scan_window['ema9'].shift(-1) < scan_window['vwap'].shift(-1))
        first_cross = first_true_ts(scan)
        if pd.isna(first_cross):
            continue

        trade_record = df.loc[first_cross]

        # check the slope at the time of the crossover
        slope = trade_record['slope']
        if slope < 0.05:
            continue

        # trade will be taken. Find LOD to calculate MM
        scan_window = df[df.index < first_cross]
        lod = scan_window['low'].min()
        mm = trade_record['close'] - lod
        stop_distance = round((mm/3), 2)


        # check to make sure the measured move is a reasonbly large value to trade
        if mm / atr < 0.25:
            continue

        stop_px = trade_record['close'] - stop_distance
        target_px = trade_record['close'] + mm

        # check to see if stop_px or target_px were hit, and which one was first if both
        scan_window = df[df.index > first_cross]
        scan = scan_window['high'] >= target_px
        target_dt = first_true_ts(scan)
        scan = scan_window['low'] <= stop_px
        stop_dt = first_true_ts(scan)

        exit_reason = ''
        if pd.notna(stop_dt):
            if pd.notna(target_dt):
                if target_dt < stop_dt:
                    exit_dt = target_dt
                    exit_px = df.loc[target_dt]['close']
                    exit_reason = 'profit'
                else:
                    exit_dt = stop_dt
                    exit_px = df.loc[stop_dt]['close']
                    exit_reason = 'loss'
            else:
                exit_dt = stop_dt
                exit_px = df.loc[stop_dt]['close']
                exit_reason = 'loss'
        else:
            if pd.notna(target_dt):
                exit_dt = target_dt
                exit_px = df.loc[target_dt]['close']
                exit_reason = 'profit'
            else: # both target and stop were not hit - take eod price and time
                exit_dt = df.iloc[-1].name
                exit_px = df.iloc[-1]['close']
                exit_reason = 'eod'

        entry_px = trade_record['open']
        pnl_pct = (exit_px - entry_px) / entry_px

        share_size = int(np.floor(equity * max_risk / stop_distance))
        pnl = (exit_px - entry_px) * share_size

        equity += pnl

        trade = {'symbol': symbol,
                 'entry_dt': first_cross,
                 'entry_px': entry_px,
                 'quantity': share_size,
                 'exit_dt': exit_dt,
                 'exit_px': exit_px,
                 'exit_reason': exit_reason,
                 'holding_period': int(np.floor((exit_dt - first_cross).total_seconds() / 60)),}

        trades.append(trade)

        print(symbol, dt_norm, f'${pnl:,.2f}')

trades_df = pd.DataFrame(trades)
trades_df.to_csv(r'D:\test_data\day_trading\fashionably_late\trades.csv', index=False)