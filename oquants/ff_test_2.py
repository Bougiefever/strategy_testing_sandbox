import pandas as pd
import numpy as np
from pathlib import Path
import datetime

from options_framework.option_types import OptionPositionType
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.calendar import Calendar
import pyarrow as pa
from pyarrow import parquet as pq
from collections import defaultdict
import math
from utility import *


# Do not trade when earnings is before the front expiration
# Filter by options volume
# Select 30/60 calendars

start_date = datetime.datetime(2023, 1, 1)
end_date = datetime.datetime(2025, 1, 1)
front_month_dte = 30
back_month_dte = 60
buffer = 5
trades_per_day = 3
portfolio_pct = 0.50
trade_allocation = 0.02
BAN = {"NDX","NDXW","SPX","SPXW","VIX"}

# get market dates for the time range - ff will have gaps
spy_daily_fn = Path(r'D:\stock_data\daily_stock_prices\SPY_.parquet')
_spy = pd.read_parquet(spy_daily_fn, engine="pyarrow")
_spy.set_index('quote_datetime', inplace=True)
_spy.sort_index(inplace=True)
dts = _spy.loc[start_date:end_date].index.values.tolist()

output_folder = Path(r'D:\test_data\forward_factor')

options_root = Path(r'D:\options_data\daily')
option_dirs = list(options_root.glob('*'))

def on_expired(expired_position):
    print(f'expired {expired_position}')

df_ff = pd.read_parquet(r'D:\test_data\forward_factor\ff_30_60.parquet')
df_ff = df_ff[~df_ff['symbol'].isin(BAN)]

df_stats = pd.read_parquet(r'D:\test_data\forward_factor\stats.parquet')

df_ff = df_ff.merge(df_stats, on=['symbol', 'quote_datetime'], how='left')
df_ff = df_ff[df_ff['vol_20_ma'] > 10_000] # filter out low liquidity tickers
portfolio = OptionPortfolio(cash=100_000, start_date=start_date, end_date=end_date, check_margin_on_open=False)

def on_expired(expired_position):
    expired_position.user_defined['expired'] = True
    print(f'expired {expired_position}')

for dt in dts:
    print(dt)
    df_ff_dt = df_ff[df_ff['quote_datetime'] == dt]
    df_ff_dt = df_ff_dt.sort_values(by=['symbol','forward_factor'], ascending=[True, False])
    # to_trade = df_ff_dt.groupby(['quote_datetime', 'symbol'], as_index=False).head(1)
    # to_trade = to_trade.sort_values(by=['forward_factor'], ascending=[False])
    to_trade = df_ff_dt.copy()
    symbols_dt = to_trade['symbol'].unique().tolist()
    portfolio.next(dt, symbols_dt)

    check_positions = portfolio.positions.copy()
    for p in check_positions:
        if p.front_option.expiration <= dt.date():
            portfolio.close_position(p, close_spot_price=p.spot_price)
            pnl= p.get_profit_loss()

    num_trades = 0
    for row in to_trade.itertuples():
        symbol = row.symbol
        front_exp = row.front_exp.date()
        front_dte = row.front_dte
        back_dte = row.back_dte
        back_exp = row.back_exp.date()
        forward_factor = row.forward_factor
        option_chain = portfolio.option_chains[symbol]
        if len(option_chain.options) == 0:
            continue
        strikes_front = option_chain.expiration_strikes[front_exp]
        strikes_back = option_chain.expiration_strikes[back_exp]
        spot_price = option_chain.options[0]['spot_price']
        strikes = list(set(strikes_front) & set(strikes_back))
        if len(strikes) == 0:
            continue
        strikes.sort()
        strike = min(strikes, key=lambda x: abs(x - spot_price))
        options = [x for x in option_chain.options if x['option_type'] == 'call'
                   and (x['expiration'] == front_exp or x['expiration'] == back_exp)
                   and x['strike'] == strike]

        # can't sell if there is no bid
        if not all(o['bid'] > 0.0 for o in options):
            continue
        if not all(o['ask'] > 0.0 for o in options):
            continue
        if not all(o['ask'] > o['bid'] for o in options):
            continue
        if not all(o['price'] > 0.0 for o in options):
            continue

        # liquidity - make sure bid/ask spread < 0.15 of spot price
        if not all(((o['ask'] - o['bid']) / o['price'] / spot_price) <= 0.15 for o in options):
            # print(f'{dt} cannot open: {strangle} - bid/ask spread > 0.15 of spot')
            continue

        calendar = Calendar.create(option_chain=option_chain, strike=strike, front_expiration=front_exp,
                                   back_expiration=back_exp, option_type='call', forward_factor=forward_factor,
                                   front_dte=front_dte, back_dte=back_dte, spot_price=spot_price)

        # take worst option - sell on the bid, buy on the ask
        calendar.position_type = OptionPositionType.LONG
        calendar.front_option.price = calendar.front_option.bid
        calendar.back_option.price = calendar.back_option.ask
        if calendar.price < 0.1:
            continue

        #contracts = max(1, math.floor((portfolio.cash * 0.02) / (calendar.price * 100)))
        contracts = 1

        portfolio.open_position(calendar, quantity=contracts, front_bid=calendar.front_option.bid, front_ask=calendar.front_option.ask,
                                back_bid=calendar.back_option.bid, back_ask=calendar.back_option.ask)
        # num_trades += 1
        # if num_trades >= trades_per_day:
        #     break


check_positions = portfolio.positions.copy()
for p in check_positions:
    #print(p.instance_id)
    portfolio.close_position(p, close_spot_price=p.spot_price)

trades = [{
    'id':x.instance_id,
    'symbol':x.symbol,
    'entry_date':x.get_open_datetime(),
    'exit_date':x.get_close_datetime(),
    'open_premium':x.get_trade_premium(),
    'front_exp':x.front_option.expiration,
    'back_exp':x.back_option.expiration,
    'strike':x.front_option.strike,
    'open_spot_price':x.user_defined['spot_price'],
    'close_spot_price':x.spot_price,
    'calendar_open_price':x.get_trade_price(),
    'front_option_open_price':x.front_option.trade_open_info.price,
    'front_option_open_bid':x.user_defined['front_bid'],
    'front_option_open_ask':x.user_defined['front_ask'],
    'front_option_close_price':x.front_option.price,
    'front_option_close_bid':x.front_option.bid,
    'front_option_close_ask': x.front_option.ask,
    'front_option_pnl': x.front_option.get_profit_loss(),
    'calendar_close_price': x.price,
    'back_option_open_price':x.back_option.trade_open_info.price,
    'back_option_open_bid':x.user_defined['back_bid'],
    'back_option_open_ask':x.user_defined['back_ask'],
    'back_option_close_price': x.back_option.price,
    'back_option_close_bid':x.back_option.bid,
    'back_option_close_ask':x.back_option.ask,
    'back_option_pnl': x.back_option.get_profit_loss(),
    'gross_pnl':x.get_profit_loss(),
    'net_pnl':(x.get_profit_loss() - x.get_fees()),
    'pnl_pct':x.get_profit_loss_percent(),
    'days_in_trade':x.get_days_in_trade(),
    'fees':x.get_fees(),
    'front_dte_at_open':x.user_defined['front_dte'],
    'back_dte_at_open':x.user_defined['back_dte'],
    'forward_factor': x.user_defined['forward_factor']}
for x in portfolio.closed_positions]

df_trades = pd.DataFrame(trades)
stats = trade_stats(df_trades)
print(stats)
fn = output_folder.joinpath(f'results_7.csv')
df_trades.to_csv(fn, index=False)
stats.to_csv(output_folder.joinpath('results_7_stats.csv'), index=True)
# ta = pa.Table.from_pandas(df_trades)
# schema = ta.schema.remove_metadata()
# ta = ta.replace_schema_metadata(schema.metadata)
# fn = output_folder.joinpath(f'results_2.parquet')
# pq.write_table(ta, fn)
