"""
Option Alpha trade bot:

2:50 EST M-F
Skip short days

0DTE
0.31% above underlying price
25-wide wings
mid-price >= 20.80
"""

from pathlib import Path
from utility import *
from options_framework import OptionPortfolio, IronButterfly, get_market_dates, OptionPositionType, settings
from datetime import datetime, time

df = pd.read_parquet(spx_prices2, engine='pyarrow', columns=['quote_datetime', 'symbol', 'open', 'high', 'low', 'close'])
df = df.drop_duplicates(subset='quote_datetime', keep='last')
df.set_index('quote_datetime', inplace=True)
df.sort_index(inplace=True)

start_date = datetime(2022, 1, 1)
end_date = datetime(2026, 3,20)
cash = 100_000

def on_expired(position):
   position.user_defined['exit_reason'] = 'expired'
   pnl = position.get_profit_loss()
   print(f'expired {position} pnl: {pnl:.2f}')

portfolio = OptionPortfolio(cash, start_date, end_date)
portfolio.bind(position_expired=on_expired)
granularity = settings.get('minute_granularity')
target_px = -0.14
target_spread_width = 5
target_price = 4.95

dts = get_market_dates(start_date, end_date)

daily_records = []
for dt in dts:
    trade_tm = pd.Timestamp(f'{dt.date()} 13:09')
    eod_tm = pd.Timestamp(f'{dt.date()} 16:00')
    portfolio.next(trade_tm, 'SPXW')

    option_chain = portfolio.option_chains.get('SPXW')
    expirations = option_chain.expirations
    if len(expirations) == 0:
        continue

    expiration = snap(dt.date(), expirations)
    if expiration != dt.date():
        continue # no 0DTE expiration today

    strikes = option_chain.expiration_strikes[expiration]
    options = option_chain.options

    deltas = [x['delta'] for x in options]
    delta = snap(target_delta, deltas)
    center_put = next(x for x in options if x['option_type'] == 'put' and x['delta'] == delta)
    center_strike = center_put['strike']
    center_call = next(x for x in options if x['option_type'] == 'call' and x['strike'] == center_strike)
    call_wing_strike = center_strike
    put_wing_strike = center_strike
    target = target_spread_width
    while call_wing_strike <= center_strike:
        call_wing_strike = snap(center_strike + target, strikes)
        target += 5
    target = target_spread_width
    while put_wing_strike >= center_strike:
        put_wing_strike = snap(center_strike - target, strikes)
        target += 5

    ib = IronButterfly.create(option_chain=option_chain, expiration=expiration, center_strike=center_strike,
                              lower_strike=put_wing_strike, upper_strike=call_wing_strike,
                              position_type=OptionPositionType.SHORT)
    price = ib.price

    if price >= target_price:
        portfolio.open_position(ib, quantity=1)
        print(f'{dt} open for {price:.2f}')

    # advance to eod
    portfolio.next(eod_tm)

    print(f'{dt} ${portfolio.current_value:,.2f}')

