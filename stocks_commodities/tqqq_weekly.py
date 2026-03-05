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
from itertools import product
import datetime
import talib
import copy

import pandas as pd
import numpy as np

qqq_fn = Path(r'D:\stock_data\daily\QQQ_.parquet')
df_qqq = pd.read_parquet(qqq_fn, engine='pyarrow')
df_qqq['200ma'] = talib.SMA(df_qqq['close'].to_numpy(float), timeperiod=200)
df_qqq['yesterday_200_ma'] = df_qqq['200ma'].shift(1)
df_qqq['return20d'] = df_qqq['close'].pct_change(20)
df_qqq['yesterday_return20d'] = df_qqq['return20d'].shift(1)
df_qqq.set_index('quote_datetime', inplace=True)
vix_fn = Path(r'D:\stock_data\daily\VIX_.parquet')
df_vix = pd.read_parquet(vix_fn, engine='pyarrow')
df_vix.set_index('quote_datetime', inplace=True)

output_folder = Path(r'D:\test_data\stock_commodities\tqqq_weekly_trade')
tqqq_fn = Path(r'D:\stock_data\intraday\stocks\etfs\TQQQ.parquet')
df = pd.read_parquet(tqqq_fn, engine='pyarrow')
df.set_index('quote_datetime', inplace=True)
df.sort_index(inplace=True)

dts = df.index.normalize().unique().tolist()

strat_params = {
    'start_date': datetime.datetime(2020, 1, 2),
    'end_date': datetime.datetime(2022, 12, 29),
    'entry_cutoff_minutes': 30,
    'price_drop_entry_trigger': 0.01,
    'profit_multiplier': 1.01,
    'breakeven_trigger_multiplier': 0.005,
    'starting_equity': 100_000,
    'equity_pct': 0.25,
    'run_number': 7
}

monday = 0

df = df.loc[strat_params['start_date']:strat_params['end_date']]
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

base_params = copy.deepcopy(strat_params)
base_run = int(base_params.get('run_number', 1))

grid = {
    "entry_cutoff_minutes": [30, 90, 150, 1440],
    "breakeven_trigger_multiplier": [0.005, 0.0075, 0.01,],
}

keys = list(grid.keys())
values = [grid[k] for k in keys]

run_number = base_run

for combo in product(*values):
    params = copy.deepcopy(base_params)
    params.update(dict(zip(keys, combo)))
    params['run_number'] = run_number
    print()
    print("-"*50)
    print("Run number: ", run_number)
    print(params)
    print("-" * 50)

    trades = []
    trade_id = 0
    trade_datas = []
    equity = params['starting_equity']

    for dt in monday_dts:
        # find the year and week of this monday date - select the entire week
        year = dt.isocalendar().year
        week = dt.isocalendar().week
        df_week = df[(df.index.isocalendar().year == year) & (df.index.isocalendar().week == week)]

        first_row = df_week.iloc[0]
        #print(first_row.name)

        # 4 - QQQ > 200 MA
        today = dt.normalize()
        # qqq_price = df_qqq.loc[today, 'open']
        # qqq_200_ma = df_qqq.loc[today, 'yesterday_200_ma']
        # if qqq_price < qqq_200_ma:
        #     print('qqq < 200 ma')
        #     continue

        # 5: QQQ 20 day return > 0
        twenty_day_return = df_qqq.loc[today, 'yesterday_return20d']
        if twenty_day_return < 0:
            continue

        # # 6: VIX < 25
        # vix_price = df_vix.loc[today, 'open']
        # if vix_price > 25:
        #     continue

        monday_px = first_row['open']
        entry_px = monday_px - (monday_px * params['price_drop_entry_trigger'])

        # price must drop by 1% to trigger a trade
        # 2 - only monday
        #monday_scan = df_week[df_week.index.weekday == monday]

        # 3: adding before 10:00 rule
        monday_scan = df_week.loc[:first_row.name + pd.Timedelta(minutes=params['entry_cutoff_minutes'])]
        entry_scan = monday_scan['low'] <= entry_px
        entry_dt = first_true_ts(entry_scan)

        # check that price actually dropped to trigger price for strategy
        if pd.isna(entry_dt):
            #print(df_week.index[0], "no entry")
            continue

        # check after entry for both profit and drawdown to see which, if either are hit, comes first
        window = df_week[df_week.index > entry_dt]
        profit_target_px = entry_px * params['profit_multiplier']
        profit_target_scan = window['high'] >= profit_target_px
        profit_target_dt = first_true_ts(profit_target_scan)

        # if entry_dt.weekday() == monday:
        #     # get week data starting with Tuesday - We are supposed to wait one day
        #     start_scan_dt = df_week[df_week.index.weekday == 1].iloc[0].name
        #     window = df_week[df_week.index >= start_scan_dt]
        breakeven_trigger_px = entry_px - (entry_px * params['breakeven_trigger_multiplier'])
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

        shares = max(100, int(np.floor(equity*params['equity_pct'] / entry_px)))
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

    params_series = pd.Series(params)
    print(params_series)

    df_trades = pd.DataFrame(trades)
    stats = trade_stats(df_trades)
    print(stats)
    df_stats = pd.DataFrame(stats)

    #df_trades = df_trades[['id','date','entry_dt','breakeven_trigger_px','profit_target_px','entry_px','exit_dt','exit_px','pct_return','per_share_dollars','exit_reason']]

    daily_data = daily_portfolio_from_trades(prices_1m=df, trades=df_trades, initial_cash=100_000)
    portfolio_stats = perf_metrics(equity=daily_data["total_value"])
    p = pd.Series(portfolio_stats)
    print(p)
    port_stats = pd.DataFrame(p)

    params_fn = output_folder.joinpath(f'params_{params["run_number"]}.csv')
    params_series.to_csv(params_fn, index=True)
    stats_fn = output_folder.joinpath(f'trade_stats_{params["run_number"]}.csv')
    df_stats.to_csv(stats_fn, index=True)
    trades_fn = output_folder.joinpath(f"trades_{params["run_number"]}.csv")
    df_trades.to_csv(trades_fn, index=False)
    port_stats_fn = output_folder.joinpath(f'portfolio_stats_{params["run_number"]}.csv')
    port_stats.to_csv(port_stats_fn, index=True)

    print("="*50)

    run_number += 1





