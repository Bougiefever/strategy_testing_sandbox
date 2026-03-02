"""
From Stocks & Commodities Magazine
One Pct a Week High Prob Strategy for TQQQ

Rules:

Monday Open price as anchor
If price drops 1% during the week, place a buy limit order at Monday Price * 0.99
After fill:
    The next day create limit order for Entry price * 1.01
    If at any time after entry, the position drops 0.5% below the entry price, try for a breakeven exit. Place an exit limit order at entry price.
    If stop limit is not hit, close at end of day on Friday
"""
import pandas as pd
import numpy as np
from pathlib import Path
import datetime
from utility import *
import datetime

import pandas as pd
import numpy as np



output_folder = Path(r'D:\test_data\stock_commodities\tqqq_weekly_trade')
tqqq_fn = Path(r'D:\stock_data\intraday\stocks\etfs\TQQQ.parquet')
df = pd.read_parquet(tqqq_fn, engine='pyarrow')
df.set_index('quote_datetime', inplace=True)
df.sort_index(inplace=True)

dts = df.index.normalize().unique().tolist()

start_date = datetime.datetime(2020, 1, 2)
end_date = datetime.datetime(2022, 12, 29)

df = df.loc[start_date:end_date]
price_drop = 0.01
entry_multiplier = 0.99
profit_multiplier = 1.01
breakeven_trigger_multiplier = 0.005
monday = 0
equity = 100_000
equity_pct = 0.25
monday_cutoff_time = datetime.time(10, 0)

weeks = df.index.isocalendar().week


def get_exit(profit_target_dt, breakeven_trigger_dt, stop_dt,
             profit_target_price, entry_price, friday_close_price, friday_close_dt):
    # Profit target hit before breakeven triggered (or breakeven never triggered)
    if pd.notna(profit_target_dt):
        if pd.isna(breakeven_trigger_dt) or profit_target_dt < breakeven_trigger_dt:
            return profit_target_dt, profit_target_price, 'TARGET'

    # Breakeven triggered and recovery found
    if pd.notna(breakeven_trigger_dt) and pd.notna(stop_dt):
        return stop_dt, entry_price, 'BREAKEVEN'

    # Everything else: Friday close
    return friday_close_dt, friday_close_price, 'FRIDAY_CLOSE'

idx = df.index.normalize().unique()
idx = idx[idx.weekday == monday]
monday_dts = idx.tolist()

trades = []
trade_id = 0
trade_datas = []
for dt in monday_dts:
    # find the year and week of this monday date - select the entire week
    year = dt.isocalendar().year
    week = dt.isocalendar().week
    df_week = df[(df.index.isocalendar().year == year) & (df.index.isocalendar().week == week)]

    first_row = df_week.iloc[0]
    print(first_row.name)
    monday_px = first_row['open']
    entry_px = monday_px - (monday_px * price_drop)

    # price must drop by 1% to trigger a trade
    monday_scan = df_week
    # adding before 10:00 rule
    # monday_scan = df_week.loc[:first_row.name + pd.Timedelta(minutes=30)]
    entry_scan = monday_scan['low'] <= entry_px
    entry_dt = first_true_ts(entry_scan)

    # check that price actually dropped to trigger price for strategy
    if pd.isna(entry_dt):
        print(df_week.index[0], "no entry")
        continue

    # check after entry for both profit and drawdown to see which, if either are hit, comes first
    window = df_week[df_week.index > entry_dt]
    profit_target_px = entry_px * profit_multiplier
    profit_target_scan = window['high'] >= profit_target_px
    profit_target_dt = first_true_ts(profit_target_scan)

    if entry_dt.weekday() == monday:
        # get week data starting with Tuesday - We are supposed to wait one day
        start_scan_dt = df_week[df_week.index.weekday == 1].iloc[0].name
        window = df_week[df_week.index >= start_scan_dt]
    breakeven_trigger_px = entry_px - (entry_px * breakeven_trigger_multiplier)
    breakeven_trigger_scan = window['low'] <= breakeven_trigger_px
    breakeven_trigger_dt = first_true_ts(breakeven_trigger_scan)

    if not pd.isna(breakeven_trigger_dt):
        stop_scan_window = df_week[df_week.index > breakeven_trigger_dt]
        stop_scan = stop_scan_window['high'] >= entry_px
        stop_dt = first_true_ts(stop_scan)
    else:
        stop_dt = pd.NaT

    friday_dt = df_week.iloc[-1].name
    friday_close_px = df_week.iloc[-1]['close']

    exit_dt, exit_px, exit_reason = get_exit(profit_target_dt, breakeven_trigger_dt, stop_dt,
                                                profit_target_px, entry_px, friday_close_px, friday_dt)


    #print(entry_dt, exit_dt, monday_px, trigger_px, entry_px, exit_px)

    # Find MAE
    trade_window = df_week.loc[entry_dt:exit_dt]
    lowest_low = trade_window['low'].min()
    mae_scan = trade_window['low'] == lowest_low
    mae_dt = first_true_ts(mae_scan)

    shares = max(100, int(np.floor(equity*equity_pct / entry_px)))
    open_value = shares * entry_px
    close_value = shares * exit_px
    pnl = round(close_value - open_value, 2)
    pct_return = (exit_px - entry_px) / entry_px
    per_share_dollars = exit_px - entry_px
    equity = equity + pnl
    trade_id += 1
    trade = {
        "id": trade_id,
        "date": entry_dt,
        "entry_dt": entry_dt,
        "breakeven_trigger_px": breakeven_trigger_px,
        "profit_target_px": profit_target_px,
        "entry_px": entry_px,
        "exit_dt": exit_dt,
        "exit_px": exit_px,
        "shares": shares,
        "gross_pnl": pnl,
        "net_pnl": pnl,
        "pct_return": pct_return,
        "per_share_dollars": per_share_dollars,
        "fees": 0.0,
        "exit_reason": exit_reason,
        "equity_after": equity,
        "MAE": lowest_low,
        "MAE_dt": mae_dt,
    }
    trades.append(trade)

    # get trade value at end of each day

    # daily = df_week.groupby(pd.Grouper(key='quote_datetime', freq='d')).first().reset_index()
    # hourly = hourly.dropna()
    # hourly.set_index('quote_datetime', inplace=True)
    # trade_history = []
    # # first time might be before entry - get rid of it
    # if hourly.iloc[0].name < entry_dt:
    #     hourly = hourly.iloc[1:]
    #     entry_row = df_week.loc[entry_dt:entry_dt]
    #     trade_history.append(entry_row)
    #
    # trade_history.append(hourly)
    #
    # # last trade might be before the last entry, add the exit row as the last row
    # if hourly.empty or hourly.iloc[0].name < exit_dt:
    #     exit_row = df_week.loc[exit_dt:exit_dt]
    #     trade_history.append(exit_row)
    #
    # trade_data = pd.concat(trade_history)
    # trade_data['trade_id'] = trade_id
    # trade_data = trade_data[['trade_id', 'open', 'high', 'low', 'close']]
    # trade_datas.append(trade_data)

df_trades = pd.DataFrame(trades)
stats = trade_stats(df_trades)
print(stats)
df_stats = pd.DataFrame(stats)
stats_fn = output_folder.joinpath('trade_stats_1.csv')
df_stats.to_csv(stats_fn, index=True)

trades_fn = output_folder.joinpath("trades_1.csv")
#df_trades = df_trades[['id','date','entry_dt','breakeven_trigger_px','profit_target_px','entry_px','exit_dt','exit_px','pct_return','per_share_dollars','exit_reason']]
df_trades.to_csv(trades_fn, index=False)

daily_data = daily_portfolio_from_trades(prices_1m=df, trades=df_trades, initial_cash=100_000)
portfolio_stats = perf_metrics(equity=daily_data["total_value"])
p = pd.Series(portfolio_stats)
print(p)
port_stats = pd.DataFrame(p)
port_stats_fn = output_folder.joinpath('portfolio_stats_1.csv')
port_stats.to_csv(port_stats_fn, index=True)






