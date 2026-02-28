"""
Explore the relationship between actual options trades and potential directional indicators
"""

import pandas as pd
import numpy as np
import talib
import datetime
from pathlib import Path
from options_framework.config import settings
from options_framework.utils.helpers import get_market_dates
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.vertical import Vertical
from collections import defaultdict
from utility import *

options_root = Path(r'D:\options_data\daily')
df_spy = pd.read_parquet(r'D:\stock_data\intraday\market\etfs\SPY.parquet', engine='pyarrow')
df_spx = pd.read_parquet(r'D:\stock_data\intraday\market\indices\SPX.parquet', engine='pyarrow')
df_vix = pd.read_parquet(r'D:\stock_data\intraday\market\indices\VIX.parquet', engine='pyarrow')

# calculate vwap
df_spy.sort_values(by=['quote_datetime'], inplace=True)
df_spy['typical_price'] = (df_spy['high'] + df_spy['low'] + df_spy['close']) / 3
df_spy['typ_vol'] = df_spy['typical_price'] * df_spy['volume']
df_spy['cum_tp_vol'] = df_spy.groupby(df_spy['quote_datetime'].dt.date)['typ_vol'].cumsum()
df_spy['cum_vol'] = df_spy.groupby(df_spy['quote_datetime'].dt.date)['volume'].cumsum()
df_spy['vwap'] = df_spy['cum_tp_vol'] / df_spy['cum_vol']
df_spy.set_index('quote_datetime', inplace=True)
df_spy.sort_index(inplace=True)

df_spx.set_index('quote_datetime', inplace=True)
df_spx.sort_index(inplace=True)
df_spx['return_5m'] = df_spx['close'].pct_change(periods=5)
df_spx['return_15m'] = df_spx['close'].pct_change(periods=15)
df_spx['return_60m'] = df_spx['close'].pct_change(periods=60)

df_vix.set_index('quote_datetime', inplace=True)
df_vix.sort_index(inplace=True)

start_date = datetime.datetime(2022, 1, 3)
end_date = datetime.datetime(2022, 11, 23)

starting_cash = 100_000
start_time = datetime.time(9, 30)
open_times = defaultdict(datetime.time)
open_times[1] = datetime.time(10, 45)
open_times[2] = datetime.time(11, 45)
open_times[3] = datetime.time(12, 45)
open_times[4] = datetime.time(13, 45)
open_times[5] = datetime.time(14, 45)
closing_time = datetime.time(15, 50)
end_time = datetime.time(15, 59)
ticker = 'SPXW'
delta_target = 0.10
delta_min = 0.08
delta_max= 0.16
prem_target = 1.25
prem_min = 0.75
prem_max = 2.5
starting_width = 30

def get_day_times(dt: datetime.datetime) -> list[datetime.datetime]:
    tm = start_time
    today = []
    while tm <= end_time:
        new_dt = datetime.datetime.combine(dt, tm)
        today.append(new_dt)
        new_dt += datetime.timedelta(minutes=1)
        tm = new_dt.time()
    return today

def get_vertical_spread(option_type, short_strike, long_strike_target):
    long_strike = min(strikes, key=lambda x: abs(long_strike_target - x))
    credit_spread = Vertical.create(option_chain=option_chain, expiration=exp, option_type=option_type,
                                         long_strike=long_strike, short_strike=short_strike)
    premium = credit_spread.short_option.get_open_price() - credit_spread.long_option.get_open_price()
    return credit_spread, premium

def score_candidate_pairs(call_candidate, put_candidate):
    call_delta = call_candidate[0].short_option.delta
    put_delta = abs(put_candidate[0].short_option.delta)

    delta_penalty = abs(call_delta - delta_target) + abs(put_delta - delta_target)

    total_prem = call_candidate[1] + put_candidate[1]
    return delta_penalty, total_prem

def get_closing_price(vertical_spread):
    short_price = vertical_spread.short_option.get_closing_price()
    long_price = vertical_spread.long_option.get_closing_price()
    return long_price - short_price, short_price

def get_df_value(df, loc_value, field):
    val = None
    while True:
        if loc_value in df.index:
            val = df.loc[loc_value, field]
            break
        else:
            loc_value = df[df.index >= loc_value].iloc[0].name
    return val

def on_expired(vertical_spread):
    vertical_spread.user_defined['exit_reason'] = 'expired'

dts = get_market_dates(start_date=start_date, end_date=end_date)

start_date = datetime.datetime.combine(start_date, start_time)
end_date = datetime.datetime.combine(end_date, end_time)
portfolio = OptionPortfolio(cash=starting_cash, start_date = start_date, end_date = end_date, check_margin_on_open=False)
portfolio.bind(position_expired=on_expired)

pair_id = 0
for dt in dts:
    print(dt)
    times = get_day_times(dt)
    trade_num = 1
    trade_time = open_times[trade_num]
    exp = None
    find_trade = False
    spy_dt = df_spy[df_spy.index.normalize() == dt]
    spx_dt = df_spx[df_spx.index.normalize() == dt]
    vix_dt = df_vix[df_vix.index.normalize() == dt]

    spx_open = spx_dt.iloc[0]['open']
    for dtt in times:
        tm = dtt.time()
        #print(tm)
        portfolio.next(dtt, ticker)
        option_chain = portfolio.option_chains[ticker]
        if len(option_chain.expirations) == 0:
            continue

        # find today expiration
        if exp is None:
            try:
                expirations = option_chain.expirations
                exp = next(x for x in expirations if x == dt.date())
                strikes = option_chain.expiration_strikes[exp]
            except StopIteration:
                break # if there is not a 0dte expiration, go to next date

        if tm >= closing_time:
            open_positions = portfolio.positions.copy()
            for p in open_positions:
                short_price = p.short_option.get_closing_price()
                exit_reason = ''
                to_close = False

                if short_price > 0.05:
                    exit_reason = 'time'
                    to_close = True

                if to_close:
                    portfolio.close_position(p, exit_reason=exit_reason)

        # check open positions
        if find_trade or tm == trade_time:
            # open new trade
            vix = get_df_value(vix_dt, dtt, 'close')  # vix_dt.loc[dtt, 'close']
            spy = spy_dt.loc[dtt, 'close']
            vwap = spy_dt.loc[dtt, 'vwap']
            spx = spx_dt.loc[dtt]
            spx_close = spx['close']

            spx_vs_open = spx_close - spx_open
            spx_open_pct = (spx_close - spx_open) / spx_open
            spy_vs_vwap = spy - vwap
            spy_vwap_pct = (spy - vwap) / vwap
            spx_5m = spx['return_5m']
            spx_15m = spx['return_15m']
            spx_60m = spx['return_60m']

            #print(trade_num, trade_time)
            candidates = []
            spread_width = starting_width
            if spx_vs_open > 0 and spx_60m <= 0:

                # find calls
                call_options = [x for x in option_chain.options if x['expiration'] == exp and x['option_type'] == 'call'
                                and x['delta'] >= delta_min]
                call_options.sort(key=lambda x: x['delta'], reverse=False)


                while True:
                    short = call_options.pop(0)
                    short_strike = short['strike']
                    long_strike_target = short['strike'] + spread_width
                    call_spread, premium = get_vertical_spread('call', short_strike, long_strike_target)
                    if delta_min < call_spread.short_option.delta < delta_max:
                        candidates.append((call_spread, call_spread.short_option.delta))
                    else:
                        break
            elif spx_vs_open <= 0 and spx_60m < 0:
                put_options =  [x for x in option_chain.options if x['expiration'] == exp and x['option_type'] == 'put'
                                and x['delta'] <= -delta_min]
                put_options.sort(key=lambda x: x['delta'], reverse=True)
                while True:
                    short = put_options.pop(0)
                    short_strike = short['strike']
                    long_strike_target = short['strike'] - spread_width
                    put_spread, premium = get_vertical_spread('put', short_strike, long_strike_target)
                    if -delta_min > put_spread.short_option.delta > -delta_max:
                        candidates.append((put_spread, put_spread.short_option.delta))
                    else:
                        break

            if len(candidates) == 0:
                find_trade = True if tm.minute < (trade_time.minute + 15) else False
                continue

            min_delta = min([x[1] for x in candidates], key=lambda x: (x - delta_target))
            vertical_spread = next(x[0] for x in candidates if x[1] == min_delta)

            portfolio.open_position(vertical_spread, quantity=1,
                                    spx_vs_open=spx_vs_open,
                                    spx_open_pct=spx_open_pct,
                                    spy_vs_vwap=spy_vs_vwap,
                                    spy_vwap_pct=spy_vwap_pct,
                                    return_5m=spx_5m,
                                    return_15m=spx_15m,
                                    return_60m=spx_60m,
                                    vix=vix)

            pair_id += 1
            trade_num += 1
            trade_time = open_times[trade_num]
            find_trade = False


closed_positions = portfolio.closed_positions.copy()

trades = [{
        'id': x.instance_id,
        'symbol': x.symbol,
        'option_type': x.option_type,
        'pair_id': x.user_defined['pair_id'],
        'entry_dt': x.get_open_datetime(),
        'exit_dt': x.get_close_datetime(),
        'open_premium': x.get_trade_premium(),
        'expiration': x.expiration,
        'open_spot_price': x.long_option.trade_open_info.spot_price,
        'close_spot_price': x.spot_price,
        'open_price': x.get_trade_price(),
        'close_price': x.get_closed_price(),
        'pnl': x.get_profit_loss(),
        'pnl_pct': x.get_profit_loss_percent(),
        'qty': x.long_option.trade_open_info.quantity,
        'fees': x.get_fees(),
        'spx_vs_open': x.user_defined['spx_vs_open'],
        'spx_open_pct': x.user_defined['spx_open_pct'],
        'spy_vs_vwap': x.user_defined['spy_vs_vwap'],
        'spy_vwap_pct': x.user_defined['spy_vwap_pct'],
        'return_5m': x.user_defined['return_5m'],
        'return_15m': x.user_defined['return_15m'],
        'return_60m': x.user_defined['return_60m'],
        'vix': x.user_defined['vix']
        }
        for x in portfolio.closed_positions]

df_trades = pd.DataFrame(trades)
df_trades.sort_values(by=['pair_id', 'option_type'], inplace=True)
# stats = trade_stats(df_trades)
# print(stats)

output_folder = Path(r'D:\test_data\spx_ic')
fn = output_folder.joinpath('x_trades_2.csv')
df_trades.to_csv(fn, index=False)
# stats.to_csv(output_folder.joinpath('stats_4.csv'), index=True)







