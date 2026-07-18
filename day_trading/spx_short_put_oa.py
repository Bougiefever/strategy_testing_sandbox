"""
Option Alpha trade bot:

Open before 12:10 PM EST
DOW is Mon/Tue/Thu (0/2/3)
High is above 60-min opening range
60-min opening range width today is >= 0.2% of the opening price
% change from previous close is between -0.15% and 0.15%

Today's expiration
Short leg @ -0.34 delta
long leg 40 below short leg
Exit 45% of max profit
Exit at 250% of premium received
"""

import pandas as pd
import datetime, time
import numpy as np
from pathlib import Path
from options_framework import settings, get_market_dates, get_day_times, OptionPortfolio, Vertical, OptionPositionType, OptionStatus
from utility import *

def on_expired(position):
    position.user_defined['exit_reason'] = 'expired'
    pnl = position.get_profit_loss()
    long_closing_price = position.long_option.get_closing_price()
    short_closing_price = position.short_option.get_closing_price()
    print(f'expired {position} pnl: {pnl:.2f}')

columns = ['quote_datetime', 'option_id', 'symbol', 'strike', 'expiration',
       'option_type', 'spot_price', 'bid', 'ask', 'price', 'delta']

#px_prices = Path(r'E:\_data\thetadata\index_data\data\SPX.parquet')
spx_prices = Path(r'D:\stock_data\intraday\market\indices\SPX.parquet')
df1 = pd.read_parquet(spx_prices, engine='pyarrow', columns=['quote_datetime', 'symbol', 'open', 'high', 'low', 'close'])
spx_prices2 = Path(r'E:\_data\thetadata\index_data\data\SPX.parquet')
df2 = pd.read_parquet(spx_prices2, engine='pyarrow', columns=['quote_datetime', 'symbol', 'open', 'high', 'low', 'close'])
df = pd.concat([df1, df2], ignore_index=True)
df = df.drop_duplicates(subset='quote_datetime', keep='last')
df.set_index('quote_datetime', inplace=True)
df.sort_index(inplace=True)

cash = 100_000
start_date = datetime.datetime(2022, 4, 18)
end_date = datetime.datetime(2026, 3, 20)
dow_permitted = [0, 2, 3]

df = df.loc[(df.index >= start_date) & (df.index <= end_date + datetime.timedelta(days=1))]

portfolio = OptionPortfolio(cash, start_date, end_date)
portfolio.bind(position_expired=on_expired)
start_time_sett = settings.get('start_time', '09_30')
end_time_sett = settings.get('end_time', '16_00')
start_time = datetime.time(int(start_time_sett[:2]), int(start_time_sett[-2:]))
end_time = datetime.time(int(end_time_sett[:2]), int(end_time_sett[-2:]))
start_orb = datetime.time(9, 30)
end_orb = datetime.time(10, 30)
end_open_trade_time = datetime.time(12, 10)
granularity = settings.get('minute_granularity')
target_delta = -0.34
min_spread_width = 40
max_risk_pct = 0.20
loss_pct = -2.5
profit_pct = 0.45

dts = get_market_dates(start_date, end_date)

daily_records = []
for i in range(1, len(dts)):
    dt = dts[i]
    print(dt)
    yesterday_eod = pd.Timestamp(f'{dts[i-1]} 15:59')
    eod = df.loc[yesterday_eod]
    yesterday_close = eod['close']
    today_eod = pd.Timestamp(f'{dts[i]} 15:59')
    today_close = df.loc[today_eod, 'close']
    # times = get_day_times(dt, start_time, end_time, granularity)
    # tm0 = times[1]

    # Determine if today is mon/tue/thu

    dow = dt.weekday()
    if dow not in dow_permitted:
        daily_records.append(
            {"date": dt, "close": today_close, "portfolio_value": portfolio.current_value, "in_trade": False})
        continue

    # Find if today is 0DTE
    first_ts = pd.Timestamp(f'{dt.date()} 09:31')
    portfolio.next(first_ts, 'SPXW')
    option_chain = portfolio.option_chains.get('SPXW')
    expirations = option_chain.expirations
    if len(expirations) == 0:
        daily_records.append(
            {"date": dt, "close": today_close, "portfolio_value": portfolio.current_value, "in_trade": False})
        continue
    exp = snap(dt.date(), expirations)
    if dt.date() != exp: # no expiration found for today
        daily_records.append(
            {"date": dt, "close": today_close, "portfolio_value": portfolio.current_value, "in_trade": False})
        continue

    # Today is 0DTE, get 60-min ORB
    orb_open = pd.Timestamp(f'{dt.date()} {start_orb}')
    orb_close = pd.Timestamp(f'{dt.date()} {end_orb}')
    orb_window = df.loc[orb_open:orb_close]
    open_price = orb_window['open'].iloc[0]
    orb_high = orb_window['high'].max()
    orb_low = orb_window['low'].min()
    orb_range = orb_high - orb_low

    # Check that opening range is >= 0.2% of open price
    price_test = open_price * 0.002
    if orb_range < price_test:
        daily_records.append(
            {"date": dt, "close": today_close, "portfolio_value": portfolio.current_value, "in_trade": False})
        continue

    prev_close_low_test = yesterday_close - (yesterday_close * 0.0015)
    prev_close_high_test = yesterday_close + (yesterday_close * 0.0015)

    today_eod = pd.Timestamp(f'{dt.date()} {end_time}')
    end_open_trade = pd.Timestamp(f'{dt.date()} {end_open_trade_time}')

    # get times between end of ORB period and last time to open a trade, 12:10 PM EST
    open_trade_window = df.loc[orb_close:end_open_trade].copy()
    cond_high_gt_orb_high = open_trade_window['high'] > orb_high
    cond_px_lt_prev_high_test = open_trade_window['close'] <= prev_close_high_test
    cond_px_gt_prev_low_test = open_trade_window['close'] >= prev_close_low_test
    open_trade_window['scan'] = cond_high_gt_orb_high & cond_px_lt_prev_high_test & cond_px_gt_prev_low_test
    open_trade_tm = first_true_ts(open_trade_window['scan'])
    if pd.isna(open_trade_tm):
        daily_records.append(
            {"date": dt, "close": today_close, "portfolio_value": portfolio.current_value, "in_trade": False})
        continue

    portfolio.next(open_trade_tm, 'SPXW')
    option_chain = portfolio.option_chains.get('SPXW')
    options = option_chain.options
    options = [x for x in options if x['expiration'] == exp]
    deltas = [x['delta'] for x in options]
    strikes = option_chain.expiration_strikes[exp]

    short_delta = snap(target_delta, deltas)
    short_option = next(x for x in options if x['delta'] == short_delta)
    long_strike_target = short_option['strike'] - 40
    long_strike = snap(long_strike_target, strikes)
    long_option = next(x for x in options if x['strike'] == long_strike and x['option_type'] == 'put')

    vertical = Vertical.create(option_chain=option_chain, expiration=exp, option_type='put',
                               short_strike = short_option['strike'], long_strike = long_option['strike'],
                               position_type=OptionPositionType.SHORT)
    max_loss = vertical.max_loss
    risk_amount = portfolio.current_value * max_risk_pct
    contracts = max(1, int(np.floor(risk_amount / max_loss)))

    portfolio.open_position(vertical, contracts, yesterday_close=yesterday_close)
    print(f'{open_trade_tm} open {vertical}   max loss: {vertical.max_loss:.2f}')

    # find 45% profit, 300% loss, or EOD
    updates = vertical.get_updates()
    df_updates = pd.DataFrame(updates)
    df_updates.set_index('quote_datetime', inplace=True)
    profit_scan = df_updates['pnl_pct'] >= profit_pct
    loss_scan = df_updates['pnl_pct'] <= loss_pct
    profit_dt = first_true_ts(profit_scan)
    loss_dt = first_true_ts(loss_scan)

    exit_reason = None
    if pd.isna(loss_dt):
        if pd.isna(profit_dt):
            # set time to eod so any expiring trades get marked as expired
            tm = datetime.datetime.combine(dt.date(), datetime.time(16,0))
        else:
            # no loss time but has profit time
            tm = profit_dt
            exit_reason = 'profit'
    else:
        if pd.isna(profit_dt):
            # has loss time but no profit time
            tm = loss_dt
            exit_reason = 'loss'
        else:
            # both profit and loss conditions found. First one is taken
            if profit_dt < loss_dt:
                exit_reason = 'profit'
                tm = profit_dt
            else:
                exit_reason = 'loss'
                tm = loss_dt


    # profit_updates = [x for x in updates if x['pnl_pct'] >= profit_pct]
    # loss_updates = [x for x in updates if x['pnl_pct'] < loss_pct]
    # profit_tm = None
    # loss_tm = None
    # if len(profit_updates) > 0:
    #     profit_tm = profit_updates[0]['quote_datetime']
    # if len(loss_updates) > 0:
    #     loss_tm = loss_updates[0]['quote_datetime']

    portfolio.next(tm, 'SPXW')
    if OptionStatus.TRADE_IS_OPEN in vertical.status:
        portfolio.close_position(vertical, exit_reason=exit_reason)
        print(f'{tm} close {vertical} pnl: {vertical.get_profit_loss():.2f} {portfolio.current_value:,.2f}')


    #
    # eod_tm = datetime.datetime.combine(dt.date(), datetime.time(16,0))
    # portfolio.next(eod_tm)

    daily_records.append(
        {"date": dt, "close": today_close, "portfolio_value": portfolio.current_value, "in_trade": True})


positions = portfolio.positions.copy()
for p in positions:
    p.close_position(p)

print(f'{portfolio.current_value:,.2f}')

closed_positions = portfolio.closed_positions.copy()
trades = []
for x in closed_positions:
    history = x.get_history()
    mae = min(x['pnl'] for x in history)
    mae_pct = min(x['pnl_pct'] for x in history)
    trade = {
        'id': x.instance_id,
        'expiration': x.expiration,
        'long_strike': x.long_option.strike,
        'short_strike': x.short_option.strike,
        'long_price': x.long_option.trade_open_info.price,
        'short_price': x.short_option.trade_open_info.price,
        'option_type': x.option_type,
        'entry_dt': x.get_open_datetime(),
        'exit_dt': x.get_close_datetime(),
        'open_premium': x.get_trade_premium(),
        'open_spot_price': x.long_option.trade_open_info.spot_price,
        'long_close_spot_price': x.long_option.trade_close_info.spot_price,
        'short_close_spot_price': x.short_option.trade_close_info.spot_price,
        'prev_day_close': x.user_defined['yesterday_close'],
        'entry_px': x.get_trade_price(),
        'exit_px': x.get_closed_price(),
        'pnl': x.get_profit_loss(),
        'pnl_pct': x.get_profit_loss_percent(),
        'max_risk': x.max_loss,
        'mae_pnl': mae,
        'mae_pct': mae_pct,
        'qty': x.long_option.trade_open_info.quantity,
        'fees': x.get_fees(),
        'holding_period': int(np.floor((x.get_close_datetime() - x.get_open_datetime()).total_seconds() / 60)),
        'exit_reason': x.user_defined['exit_reason']
    }
    trades.append(trade)

df_trades = pd.DataFrame(trades)
df_daily = pd.DataFrame(daily_records)
df_daily.set_index('date', inplace=True)

run = 6
output_folder = Path(r'D:\test_data\day_trading\spx_trade')
trades_fn = output_folder.joinpath(f'trades_{run}.csv')
daily_fn = output_folder.joinpath(f'daily_{run}.csv')

portfolio_stats, trades_stats = print_report('SPX', df_trades, df_daily,
                                                        "SPX Trade", frequency='intraday')

trades_stats.to_csv(output_folder.joinpath(f'trades_stats_{run}.csv'), index=True)
portfolio_stats.to_csv(output_folder.joinpath(f'portfolio_stats{run}.csv'), index=True)
df_trades.to_csv(trades_fn, index=False)
df_daily.to_csv(daily_fn, index=True)

