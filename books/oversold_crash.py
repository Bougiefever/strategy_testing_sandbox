from pathlib import Path
import pandas as pd
import talib
import math
import numpy as np
import csv
import pyperclip

from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.vertical import Vertical
from options_framework.spreads.single import Single

options_folder = Path(r'D:\options_data\daily')
stock_folder = Path(r'D:\stock_data\daily_stock_prices')
stock_calcs_folder = Path(r'D:\stock_data\calcs')
results_fn = Path(r'D:\test_data\conners\crash\results.csv')

def trade_stats(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"n_trades": 0}

    r = trades["return"].to_numpy(float)
    wins = r[r > 0]
    losses = r[r < 0]

    gross_profit = wins.sum() if wins.size else 0.0
    gross_loss = -losses.sum() if losses.size else 0.0
    pf = (gross_profit / gross_loss) if gross_loss > 0 else np.inf

    return {
        "n_trades": int(len(trades)),
        "win_rate": float((r > 0).mean()),
        "avg_return": float(r.mean()),
        "median_return": float(np.median(r)),
        "profit_factor": float(pf),
        "avg_hold_days": float(trades["hold_days"].mean()),
        "median_hold_days": float(trades["hold_days"].median()),
        "best_trade": float(r.max()),
        "worst_trade": float(r.min()),
    }

def build_trades_from_entries_exits(
    df: pd.DataFrame,
    entry_idx: np.ndarray,
    entry_price: np.ndarray,
    next_exit: np.ndarray,
) -> pd.DataFrame:
    """
    - entry_idx: indices where limit order filled (entry executes on that bar)
    - entry_price: executed price at entry_idx
    - next_exit[i]: index of first bar >= i where exit signal is True, else -1
    Exit execution: next day's open after the exit-signal day.
    """

    ticker = df.iloc[0]['symbol']
    idx = df.index
    o = df["open"].to_numpy(float)
    c = df["close"].to_numpy(float)
    limit_px = df["limit_px"].to_numpy(float)  # for logging if you want

    trades = []
    n = len(df)

    flat_from = 0  # earliest index we are allowed to enter (we're flat before this)

    for e in entry_idx:
        if e < flat_from:
            continue  # already in a trade, skip overlapping entry signals

        ep = float(entry_price[e])
        if not np.isfinite(ep):
            continue

        # Exit signal day: first day at/after entry where exits == True
        x_sig = int(next_exit[e])
        if x_sig == -1:
            break  # no exit signal remaining in data; ignore open trade

        # Exit executes next day open
        x_exec = x_sig + 1
        if x_exec >= n or not np.isfinite(o[x_exec]):
            break  # can't execute exit on last day (or missing open)

        xp = float(o[x_exec])

        # Short return: profit when price falls
        ret = (ep - xp) / ep

        trades.append({
            "symbol": ticker,
            "entry_date": idx[e],
            "exit_signal_date": idx[x_sig],
            "exit_date": idx[x_exec],
            "entry_price": ep,
            "exit_price": xp,
            "hold_days": int(x_exec - e),
            "return": ret,
            "limit_px": float(limit_px[e]),
            "close_on_entry_day": float(c[e]),
        })

        # next trades can only start after we exit
        flat_from = x_exec + 1

    return pd.DataFrame(trades)


stock_files = stock_folder.glob('*.parquet')
stock_calc_files = list(stock_calcs_folder.glob('*.parquet'))

results = [['ticker','entries','crsi_min','crsi_max','hist_vol_min','hist_vol_max','crsi_gt_90','hist_vol_gt_100']]
all_trades = []
for stock_file in stock_files:
    ticker = stock_file.stem[:-1]
    stock_fn = stock_folder.joinpath(f'{ticker}_.parquet')
    calc_fn = stock_calcs_folder.joinpath(f'{ticker}_calcs.parquet')
    if not calc_fn.exists():
        continue

    df = pd.read_parquet(stock_fn, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume', 'close_orig'], engine='pyarrow')
    df_calc = pd.read_parquet(calc_fn, columns=['symbol', 'quote_datetime','crsi', 'hist_vol_100'], engine='pyarrow')

    df = df.merge(df_calc, how='inner', on=['symbol','quote_datetime'])
    df.set_index('quote_datetime', inplace=True)
    df.sort_index(inplace=True)

    df['hist_vol'] = df['hist_vol_100'] * np.sqrt(252)
    df['vol_21_ma'] = talib.MA(df['volume'].to_numpy().astype(float), timeperiod=21)

    vol_ma_pass = df['vol_21_ma'] >= 1_000_000
    crsi_pass = df['crsi'] >= 90
    hist_vol_pass = df['hist_vol'] >= 1.0
    price_pass = df['close_orig'] >= 5

    df['cond_true'] = (
            (df['vol_21_ma'] >= 1_000_000) &
            (df['crsi'] >= 90) &
            (df['hist_vol'] >= 1.0) &
            (df['close_orig'] >= 5)
    )

    df['limit_px'] = df['close'].shift(1) * 1.03
    df['cond_true_shift'] = df['cond_true'].shift(1, fill_value=False)
    df['exits'] = (df['crsi'] <= 30).fillna(False)

    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    limit_px = df['limit_px'].to_numpy(float)

    signal = df["cond_true_shift"].to_numpy(bool)
    filled_today = (h >= limit_px)
    entries = signal & filled_today

    entry_price = np.full(len(df), np.nan, dtype=float)
    entry_price[entries] = np.where(o[entries] >= limit_px[entries], o[entries], limit_px[entries])
    entry_idx = np.flatnonzero(entries)

    exit_sig = df['exits'].to_numpy(bool)
    n = len(exit_sig)
    next_exit = np.full(n, -1, dtype=int)

    last = -1
    for i in range(n-1, -1, -1):
        if exit_sig[i]:
            last = i
        next_exit[i] = last

    trades = build_trades_from_entries_exits(df, entry_idx, entry_price, next_exit)
    # stats = trade_stats(trades)
    # if stats['n_trades'] > 0:
    print(ticker)
    #     print(stats)
    all_trades.append(trades)

df_all = pd.concat(all_trades)
stats = trade_stats(df_all)
print("************************************************************************************")
print(stats)
results_fn = r'D:\test_data\conners\crash\trades.csv'
df_all.to_csv(results_fn, index=False, header=True)


#     # print(ticker)
#     # print("count_entries:", len(df[df['entries'] == True]))
#     #
#     # print("CRSI_min/max:", df["crsi"].min(), df["crsi"].max())
#     # print("HV_min/max:", df["hist_vol"].min(), df["hist_vol"].max())
#     #
#     # print("count_crsi>=90:", (df["crsi"] >= 90).sum())
#     # print("count_hv>=1.0:", (df["hist_vol"] >= 1.0).sum())
#     # print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
#     #
#     # result = [ticker, len(df[df['entries'] == True]),df["crsi"].min(),df["crsi"].max(),df["hist_vol"].min(),df["hist_vol"].max(),(df["crsi"] >= 90).sum(),(df["hist_vol"] >= 1.0).sum()]
#     # results.append(result)
#
#
# with open(results_fn, 'w', newline='') as csvfile:
#     writer = csv.writer(csvfile)
#     writer.writerows(results)



