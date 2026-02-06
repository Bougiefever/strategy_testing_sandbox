from __future__ import annotations

import datetime
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.vertical import Vertical
from options_framework.config import settings
import pandas as pd
import talib
import numpy as np
import vectorbtpro as vbt

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

from pathlib import Path
options_root = Path(settings['options_directory'], 'daily')
stock_root = Path(settings['stock_data_files'])

ticker = 'VXX'


stock_file = stock_root.joinpath(f'{ticker}_.parquet')

if __name__ == "__main__":

    df = pd.read_parquet(stock_file, engine='pyarrow')
    df.set_index('quote_datetime', inplace=True)
    df.sort_index(inplace=True)
    df['sma_10'] = talib.SMA(df['close'].to_numpy(), timeperiod=10)
    df['sma_30'] = talib.MA(df['close'].to_numpy(), timeperiod=30)

    c = df['close']
    o = df['open']

    buy_sig  = df["sma_10"] < df["sma_30"]
    sell_sig = (df["sma_30"] < df["sma_10"])

    buy_sig = buy_sig.fillna(False).to_numpy(bool)
    sell_sig = sell_sig.fillna(False).to_numpy(bool)

    n = len(df)
    next_exit = np.full(n, -1, dtype=int)
    last = -1
    for i in range(n - 1, -1, -1):
        if sell_sig[i]:
            last = i
        next_exit[i] = last

    entry_idx = np.flatnonzero(buy_sig)

    flat_from = 0  # earliest bar we can enter (we're flat before this)

    trades = []

    for en in entry_idx:
        if en < flat_from:
            continue
        if en + 1 >= n:
            break # we've reached the end

        # find next exit signal
        ex = next_exit[en + 1]
        if ex == -1:
            break  # no exit signal remaining

        entry_px = c.iloc[en]
        exit_px = c.iloc[ex]
        ret = (exit_px / entry_px) - 1.0  # LONG return


        trades.append({
            "entry_date": df.index[en],
            "exit_date": df.index[ex],
            "entry_price": entry_px,
            "exit_price": exit_px,
            "hold_days": int(ex - en),
            "return": float(ret),
        })

        flat_from = ex + 1 # start looking for next signal on the bar after exit

    trades_df = pd.DataFrame(trades)
    stats = trade_stats(trades_df)
    s = pd.Series(stats)
    print(s)