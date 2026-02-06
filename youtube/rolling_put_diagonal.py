from pathlib import Path
import sys
import datetime
import time
import talib
import pandas as pd
import numpy as np
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.single import Single
from options_framework.option_types import OptionPositionType
from utility import *

spx_intra_fn = r'D:\stock_data\intraday\market\indices\SPX.parquet'
spx_daily_fn = r'D:\stock_data\daily_stock_prices\SPX_.parquet'
ticker = 'SPXW'
start_date = datetime.datetime(2016, 2, 1) # set earlier for warmup of emas
end_date = datetime.datetime(2022, 11, 23)
df_intra = pd.read_parquet(spx_intra_fn, engine='pyarrow')
df_daily = pd.read_parquet(spx_daily_fn, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume'], engine='pyarrow')
df_intra = df_intra[(df_intra['quote_datetime'] >= start_date) & (df_intra['quote_datetime'] <= end_date)]
df_daily = df_daily[(df_daily['quote_datetime'] >= start_date) & (df_daily['quote_datetime'] <= end_date)]
df_intra.set_index('quote_datetime', inplace=True)
df_intra.sort_index(inplace=True)

df_daily.dropna(inplace=True)
df_daily.set_index('quote_datetime', inplace=True)
df_daily.sort_index(inplace=True)

# get weekly regime filter
df_weekly = df_daily['close'].resample("W-FRI").last().to_frame("weekly_close")
df_weekly["weekly_ema"] = df_weekly["weekly_close"].ewm(span=9, adjust=False).mean()
df_weekly["weekly_ema_slope"] = df_weekly["weekly_ema"] - df_weekly["weekly_ema"].shift(3)
df_weekly["regime_close_gt_ema"] = df_weekly["weekly_close"] > df_weekly["weekly_ema"]
df_weekly["regime_slope_pos"] = df_weekly["weekly_ema_slope"] > 0
df_weekly["weekly_regime"] = (df_weekly["regime_close_gt_ema"] & df_weekly["regime_slope_pos"]).shift(1)
df_daily = df_daily.join(df_weekly[["weekly_close","weekly_ema","weekly_ema_slope","weekly_regime"]], how="left")
df_daily[["weekly_close","weekly_ema","weekly_ema_slope","weekly_regime"]] = df_daily[["weekly_close","weekly_ema","weekly_ema_slope","weekly_regime"]].ffill()
df_daily['yesterday_close'] = df_daily['close'].shift(1)

# df_daily['MA9'] = talib.EMA(df_daily['close'].to_numpy(float), timeperiod=9)
# df_daily['MA20'] = talib.EMA(df_daily['close'].to_numpy(float), timeperiod=20)
start_date = datetime.datetime(2016, 3, 1) # move past warmup period
df_daily = df_daily[df_daily.index >= start_date]

def find_short_leg(dt, option_chain, strike=None):
    expirations = option_chain.expirations
    next_exp = next(e for e in expirations if e > dt.date())
    if strike is  None:
        strike = next(x for x in option_chain.expiration_strikes[next_exp][::-1] if x < close)

    short_leg = Single.create(option_chain=option_chain, expiration=next_exp, strike=strike, option_type='put')
    return short_leg

def on_closed(close_position):
    print(close_position.get_close_datetime(), close_position, close_position.get_profit_loss())

def on_expired(expired_position):
    print(f'expired: {expired_position} {expired_position.get_profit_loss():.2f}')


if __name__ == "__main__":

    dts = df_daily.index.normalize().tolist()

    portfolio = OptionPortfolio(cash=1_000_000, start_date=start_date, end_date=end_date, check_margin_on_open=False)
    portfolio.bind(position_expired=on_expired)
    portfolio.bind(position_closed=on_closed)
    start_date = datetime.datetime(2016, 3, 1, 9, 31)
    start_time = datetime.time(9,45)

    in_campaign = False
    for dt in dts:
        daily = df_daily.loc[dt]
        regime_ok = daily['weekly_regime']

        df_dt = df_intra[(df_intra.index.normalize() == dt) & (df_intra.index.time >= start_time)]
        if not in_campaign and not regime_ok:
            continue

        for dt_intra, row in df_dt.iterrows():
            close = row['close']
            portfolio.next(dt_intra, ticker, portfolio.cash, portfolio.portfolio_margin_allocation)
            option_chain = portfolio.option_chains[ticker]

            if not in_campaign:
                if len(option_chain.expirations) == 0 or len(option_chain.options) == 0:
                    continue

                short_leg = find_short_leg(dt, option_chain)

                # look for the long leg option with about double the price of the short leg
                target_expiration = dt.date() + datetime.timedelta(days=14)
                target_price = short_leg.price * 2
                exps = [x for x in option_chain.expirations if x >= target_expiration]
                long_leg = None
                for exp in exps:
                    options = [x for x in option_chain.options if x['option_type'] == 'put' and x['expiration'] == exp and x['delta'] < -0.30]
                    deltas = [x['delta'] for x in options][::-1]
                    delta = deltas.pop()
                    to_open = False
                    while delta >= -0.35:
                        option_data = next(x for x in options if x['delta'] == delta)
                        price = option_data['price']
                        if 1.5 <= price / short_leg.price >= 3.0:
                            to_open = True
                            break


                        delta = deltas.pop()
                    if to_open:
                        long_strike = option_data['strike']
                        long_leg = Single.create(option_chain=option_chain, expiration=exp, strike=long_strike,
                                                 option_type='put')

                if long_leg is None:
                    continue
                portfolio.open_position(short_leg, quantity=-1, open_spot_price=close)
                portfolio.open_position(long_leg, quantity=1)
                # print(dt_intra, long_leg)
                # print(dt_intra, short_leg)

                in_campaign = True
                break

            elif in_campaign:
                try:
                    # close current short leg
                    short_leg = next(x for x in portfolio.positions if x.position_type == OptionPositionType.SHORT)
                    long_leg = next(x for x in portfolio.positions if x.position_type == OptionPositionType.LONG)

                    if regime_ok == False:
                        portfolio.close_position(short_leg.instance_id)
                        portfolio.close_position(long_leg.instance_id)
                        in_campaign = False
                        break

                    if long_leg.get_dte() <= 2:
                        portfolio.close_position(short_leg.instance_id)
                        portfolio.close_position(long_leg.instance_id)
                        in_campaign = False
                        continue


                    to_roll = False
                    if abs(short_leg.option.delta) <= abs(long_leg.option.delta):
                        to_roll = True

                    if short_leg.expiration == dt.date():
                        to_roll = True

                    if to_roll:
                        open_date = short_leg.get_open_datetime()

                        # if this is the same day the option was opened, skip to next day
                        if open_date.date() == dt.date():
                            break

                        open_spot_price = short_leg.user_defined['open_spot_price']
                        if close >= open_spot_price:
                            new_short_leg = find_short_leg(dt, option_chain)

                        elif close < open_spot_price:
                            # open new at same strike - but only if expiration will be different
                            new_short_leg = find_short_leg(dt, option_chain,  strike=short_leg.strike)

                        portfolio.close_position(short_leg.instance_id)
                        portfolio.open_position(new_short_leg, quantity=-1, open_spot_price=close)
                        # print(dt_intra, new_short_leg)
                        break
                    else:
                        break # check again tomorrow
                except StopIteration:
                    print(dt_intra, "cannot find short leg")
                    for pos in portfolio.positions:
                        print(pos)
                except Exception as e:
                    print(dt_intra, e)
                    # for pos in portfolio.positions:
                    #     print(pos)
                    raise

    open_positions = portfolio.positions.copy()
    for pos in open_positions:
        portfolio.close_position(pos.instance_id)


    print(portfolio.current_value)
    portfolio_running_values = portfolio.close_values
    dates = [x[0] for x in portfolio_running_values]
    nlv = pd.Series([x[1] for x in portfolio_running_values], index=dates, name='nlv')
    cash = pd.Series([x[2] for x in portfolio_running_values], index=dates, name='cash')
    margin = pd.Series([x[3] for x in portfolio_running_values], index=dates, name='margin')

    trades_data = [
        [o.get_open_datetime(), o.get_close_datetime(), o.get_profit_loss(), o.get_trade_premium(), o.get_fees()] for o
        in
        portfolio.closed_positions]
    trades_index = [o.instance_id for o in portfolio.closed_positions]
    trades_df = pd.DataFrame(data=trades_data, index=trades_index,
                             columns=['entry_date', 'exit_date', 'pnl', 'capital_at_risk', 'fees'])
    output = portfolio_stats_options(nlv, trades_df, cash, margin)
    print(output)
    print("*****************************************************************************************************")
    tstats =  trade_stats(trades_df)
    print(tstats)
