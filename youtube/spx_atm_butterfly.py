"""
As per Claude, these are the parameters

Entry time: 1:00 PM
Structure: ATM butterfly (center strike = nearest to SPX at entry)
Wing widths: 15-point and 20-point (so two butterflies per day)
Filter: VIX < 15 at entry AND first-15-minute range < 6 points
Tracking: Butterfly spread mark-to-market at 5-minute intervals from 13:00 to 15:00
Years: All available (2016–2022)

"""

import datetime
from pathlib import Path
from options_framework.config import settings
from options_framework.option_types import OptionPositionType
from options_framework.utils.helpers import get_market_dates
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.butterfly import Butterfly
from collections import defaultdict
from utility import *

options_root = Path(r'D:\options_data\daily')
output_folder = Path(r'D:\test_data\spx_ic\atm_butterfly')
df_spx = pd.read_parquet(r'D:\stock_data\intraday\market\indices\SPX.parquet', engine='pyarrow')
df_spx.set_index('quote_datetime', inplace=True)
df_spx.sort_index(inplace=True)
df_vix = pd.read_parquet(r'D:\stock_data\intraday\market\indices\VIX.parquet', engine='pyarrow')
df_vix.set_index('quote_datetime', inplace=True)
df_vix.sort_index(inplace=True)
df_vix.rename(columns={'close': 'vix'}, inplace=True)
df = df_spx.merge(df_vix[['vix']], on='quote_datetime', how='left')
df['vix'] = df['vix'].ffill()
start_date = datetime.datetime(2016, 3, 9)
end_date = datetime.datetime(2022, 11, 23)

starting_cash = 100_000
start_time = datetime.time(9, 30)
orb_time = datetime.time(9,45)
entry_time = datetime.time(13, 0)
end_time = datetime.time(15, 59)
ticker = 'SPXW'

wing1 = 15
wing2 = 20

vix_limit=20
orb_range_limit=6
orb_window_minutes = 15
time_granularity = 5

dts = get_market_dates(start_date=start_date, end_date=end_date)
portfolio = OptionPortfolio(cash=starting_cash, start_date = start_date, end_date = end_date, check_margin_on_open=False)

def get_buttefly_prices(position):
    lower_price = position.lower_option.price
    lower_bid = position.lower_option.bid
    lower_ask = position.lower_option.ask
    center_price = position.center_option.price
    center_bid = position.center_option.bid
    center_ask = position.center_option.ask
    upper_price = position.upper_option.price
    upper_bid = position.upper_option.bid
    upper_ask = position.upper_option.ask

    price = position._calculate_price(lower_price=lower_price, center_price=center_price, upper_price=upper_price)
    bid = position._calculate_price(lower_price=lower_bid, center_price=center_ask, upper_price=upper_bid)
    ask = position._calculate_price(lower_price=lower_ask, center_price=center_bid, upper_price=upper_ask)

    return bid, ask, price


def get_day_times(dt: datetime.datetime, granularity: int) -> list[datetime.datetime]:
    tm = start_time
    today = []
    while tm <= end_time:
        new_dt = datetime.datetime.combine(dt, tm)
        today.append(new_dt)
        new_dt += datetime.timedelta(minutes=granularity)
        tm = new_dt.time()
    return today

filter_info = []
for dt in dts:
    print(dt)
    times = get_day_times(dt, 1)
    exp = None
    price_history = []
    portfolio.next(times[0], ticker)
    option_chain = portfolio.option_chains[ticker]

    df_dt = df[df_spx.index.normalize() == dt]
    orb_window = df_dt.loc[times[0]:times[0] + pd.Timedelta(minutes=orb_window_minutes)]
    orb_high = orb_window['high'].max()
    orb_low = orb_window['low'].max()
    orb_range = orb_high - orb_low
    if abs(orb_range) >= orb_range_limit:
        filter_info.append({'date': dt, 'reason': f'orb_range {orb_range}'})
        continue

    times = get_day_times(dt, 5)
    times = [x for x in times if x.time() >= entry_time and x.time() <= end_time]

    for dtt in times:
        tm = dtt.time()
        portfolio.next(dtt, ticker)
        option_chain = portfolio.option_chains[ticker]

        if len(option_chain.expirations) == 0:
            continue

        if exp is None:
            try:
                expirations = option_chain.expirations
                exp = next(x for x in expirations if x == dt.date())
                strikes = option_chain.expiration_strikes[exp]
            except StopIteration:
                #filter_info.append({'date':dt, 'reason': 'not 0DTE day'})
                break  # if there is not a 0dte expiration, go to next date

        if dtt.time() > entry_time:
            for p in portfolio.positions:
                prices = get_buttefly_prices(position=p)
                price_history.append((p.instance_id,) + prices)

        # if dtt.time() == end_time:
        #     open_positions = portfolio.positions.copy()
        #     for p in open_positions:
        #         price_hist = [x for x in price_history if x[0] == p.instance_id]
        #         portfolio.close_position(p, price_hist=price_hist)
        #         final_price = p.get_closed_price()

        if dtt.time() == entry_time:
            vix = df_dt.loc[dtt]['vix']
            if vix > vix_limit:
                filter_info.append({'date':dt, 'reason': f'vix at {vix}'})
                break

            spot_price = df_dt.loc[dtt]['close']
            center_strike = min(strikes, key=lambda x: abs(x - spot_price))
            upper_strike = center_strike + wing1
            lower_strike = center_strike - wing1

            butterfly_1 = Butterfly.create(option_chain=option_chain, expiration=exp, option_type='put',
                                           center_strike=center_strike, upper_strike=upper_strike,
                                           lower_strike=lower_strike, position_type=OptionPositionType.LONG)

            portfolio.open_position(butterfly_1, quantity=1, spread_width=wing1, vix=vix, orb_range=orb_range)
            prices = get_buttefly_prices(position=butterfly_1)
            price_history.append((butterfly_1.instance_id,) + prices)

            upper_strike = center_strike + wing2
            lower_strike = center_strike - wing2

            butterfly_2 = Butterfly.create(option_chain=option_chain, expiration=exp, option_type='put',
                                           center_strike=center_strike, upper_strike=upper_strike,
                                           lower_strike=lower_strike, position_type=OptionPositionType.LONG)

            portfolio.open_position(butterfly_2, quantity=1, spread_width=wing2, vix=vix, orb_range=orb_range)
            prices = get_buttefly_prices(position=butterfly_2)
            price_history.append((butterfly_2.instance_id,) + prices)

closed_positions = portfolio.closed_positions.copy()
trades = [{
        'id': x.instance_id,
        'symbol': x.symbol,
        'option_type': x.option_type,
        'entry_dt': x.get_open_datetime(),
        'open_premium': x.get_trade_premium(),
        'expiration': x.expiration,
        'open_spot_price': x.lower_option.trade_open_info.spot_price,
        'close_spot_price': x.spot_price,
        'open_price': x.get_trade_price(),
        'close_price': x.get_closed_price(),
        'pnl': x.get_profit_loss(),
        'pnl_pct': x.get_profit_loss_percent(),
        'qty': x.lower_option.trade_open_info.quantity,
        'fees': x.get_fees(),
        'spread_width': x.user_defined['spread_width'],
        'center_strike': x.center_option.strike,
        'intrinsic_value': max(0, x.user_defined['spread_width'] - abs(x.spot_price - x.center_option.strike)),
        'vix': x.user_defined['vix'],
        'first_15_min_range': x.user_defined['orb_range'],}
        for x in portfolio.closed_positions]

df_trades = pd.DataFrame(trades)
df_trades.to_csv(output_folder.joinpath("trades_3.csv"), index=False)

# all_records = []
# for c in closed_positions:
#     instance_id = c.instance_id
#     spread_width = c.user_defined['spread_width']
#     detailed_prices = c.user_defined['price_hist']
#     history = c.get_price_history()
#     records = []
#     for i in range(len(history)):
#         h = history[i]
#         p = detailed_prices[i]
#         rec = {
#             'trade_id': instance_id,
#             'spread_width': spread_width,
#             'date':h[0].date(),
#             'time': h[0].time(),
#             'bid': p[1],
#             'ask': p[2],
#             'mid_price': p[3],
#             'price': h[1],
#             'spot_price': h[2],
#             }
#         records.append(rec)
#     all_records.extend(records)
#
# df_history = pd.DataFrame(all_records)
# df_history.to_csv(output_folder.joinpath("history_3.csv"), index=False)
#
# df_filters = pd.DataFrame(filter_info)
# df_filters.to_csv(output_folder.joinpath("filter_3.csv"), index=False)
