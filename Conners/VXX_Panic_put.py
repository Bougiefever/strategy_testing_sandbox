from __future__ import annotations

import sys
import csv
import datetime
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.single import Single
from options_framework.config import settings
import pandas as pd
import talib
import numpy as np
from pathlib import Path

def trade_stats(trades: pd.DataFrame) -> dict:
    # Summary stats
    if trades_df.empty:
        stats = {"n_trades": 0}
        return trades_df, stats

    r = trades_df["return"].to_numpy(float)
    wins = r[r > 0]
    losses = r[r < 0]

    gross_profit = wins.sum() if wins.size else 0.0
    gross_loss = -losses.sum() if losses.size else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.inf

    stats = {
        "n_trades": int(len(trades_df)),
        "win_rate": float((r > 0).mean()),
        "avg_return": float(r.mean()),
        "median_return": float(np.median(r)),
        "profit_factor": float(profit_factor),
        "avg_hold_days": float(trades_df["hold_days"].mean()),
        "median_hold_days": float(trades_df["hold_days"].median()),
        "best_trade": float(r.max()),
        "worst_trade": float(r.min()),
    }

    return stats

def build_entry_exit_idx_same_close(df, ema_len=5, rsi_len=4, rsi_th=70):
    df = df.sort_index()

    close = df['close'].to_numpy(float)
    ema = df['EMA'].to_numpy(float)
    rsi = df['RSI'].to_numpy(float)

    buy_sig = (close > ema) & (rsi > rsi_th)
    sell_sig = (close < ema)

    buy_sig = np.where(np.isfinite(ema) & np.isfinite(rsi), buy_sig, False).astype(bool)
    sell_sig = np.where(np.isfinite(ema), sell_sig, False).astype(bool)

    n = len(close)

    # next sell signal index at/after each bar
    next_exit = np.full(n, -1, dtype=int)
    last = -1
    for i in range(n - 1, -1, -1):
        if sell_sig[i]:
            last = i
        next_exit[i] = last

    entry_idx_all = np.flatnonzero(buy_sig)

    entry_idx = []
    exit_idx = []

    flat_from = 0
    for e in entry_idx_all:
        if e < flat_from:
            continue

        # exit strictly AFTER entry
        if e + 1 >= n:
            break
        x = next_exit[e + 1]
        if x == -1:
            break

        entry_idx.append(e)
        exit_idx.append(x)

        flat_from = x + 1

    return np.array(entry_idx, dtype=int), np.array(exit_idx, dtype=int)


options_root = Path(settings['options_directory'], 'daily')
stock_root = Path(settings['stock_data_files'])

ticker = 'VXX'
rsi_period = 4
ma_period = 5
rsi_th = 70

stock_file = stock_root.joinpath(f'{ticker}_.parquet')

if __name__ == "__main__":

    df = pd.read_parquet(stock_file, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume'], engine='pyarrow')
    df.set_index('quote_datetime', inplace=True)
    df.sort_index(inplace=True)
    df['RSI'] = talib.RSI(df['close'].to_numpy(), timeperiod=rsi_period)
    df['EMA'] = talib.EMA(df['close'].to_numpy(), timeperiod=ma_period)

    portfolio = OptionPortfolio(cash=100_000, start_date=df.index[0], end_date=df.index[-1])
    trades = []

    entry_idx, exit_idx = build_entry_exit_idx_same_close(df)
    dt = df.iloc[0].name
    for i in entry_idx:
        for i in entry_idx:
            df_trade = df.iloc[i:]

            if df_trade.iloc[0].name < dt:
                continue

            qty = 0
            entry_px = 0
            for dt, row in df_trade.iterrows():
                dt = row.name.to_pydatetime()
                close = row['close']
                ema = row['EMA']

                portfolio.next(dt, ticker)
                print(dt)
                if close > entry_px and qty > -4:
                    option_chain = portfolio.option_chains[ticker]
                    if len(option_chain.expirations) == 0:
                        break

                    expiration_target = dt + datetime.timedelta(days=30)
                    expiration = min(option_chain.expirations, key=lambda x: abs((x - expiration_target.date()).days))
                    days_diff = (expiration - dt.date()).days
                    if days_diff < 28 or days_diff > 49:
                        break

                    deltas = [x['delta'] for x in option_chain.options if x['option_type'] == 'put' and x['expiration'] == expiration]
                    delta = min(deltas, key=lambda x: abs(x - -(0.8)))
                    put_data = next(x for x in option_chain.options if x['option_type'] == 'put' and x['delta'] == delta)

                    put_option = Single.create(option_chain=option_chain, expiration=expiration, strike=put_data['strike'], option_type='put')

                    qty -= 1
                    portfolio.open_position(put_option, quantity=qty)

                    entry_px = close
                elif close < ema: # close everything
                    for put_option in portfolio.positions:
                        portfolio.close_position(put_option.instance_id)
                        trades.append(put_option)
                        qty = put_option.option.trade_close_info.quantity
                        print(put_option, qty, put_option.get_profit_loss())

                    break

    trades_index = [f'{o.symbol}_{o.instance_id}' for o in trades]
    trades_data = [[o.symbol, o.get_open_datetime(), o.get_close_datetime(), o.get_trade_price(), o.price,
                    (o.get_close_datetime() - o.get_open_datetime()).days, o.get_profit_loss_percent()] for o in
                   trades]
    trades_df = pd.DataFrame(data=trades_data, index=trades_index,
                             columns=['symbol', 'entry_date', 'exit_date', 'entry_price', 'exit_price', 'hold_days',
                                      'return'])

    stats = trade_stats(trades_df)
    s = pd.Series(stats)
    print(s)

    output_fn = r'D:\test_data\conners\vxx_panic\output_buy_puts_2.txt'
    s.to_csv(output_fn, header=False)
    results_fn = r'D:\test_data\conners\vxx_panic\trades_options_2.csv'
    trades_df.to_csv(results_fn, index=False, header=True)
    balance_fn = r'D:\test_data\conners\vxx_panic\balance_2.csv'
    close_values = portfolio.close_values
    close_values.insert(0, ['date', 'current value'])
    with open(balance_fn, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(portfolio.close_values)