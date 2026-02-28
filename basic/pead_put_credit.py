import pandas as pd
import numpy as np
from pathlib import Path
import datetime
import pyarrow as pa
from pyarrow import parquet as pq
from pyarrow import compute as pc
import math
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.vertical import Vertical
from utility import *
from collections import defaultdict

stock_folder = Path(r'D:\stock_data\daily')
signals_fn = Path(r'D:\test_data\basic\pead\signals.csv')

start_date = datetime.datetime(2020, 1, 1)
end_date = datetime.datetime(2025, 12, 31)

# Define strategy parameters
target_delta_min = 0.20
target_delta = 0.30
target_delta_max = 0.40
spread_width = 10           # dollars, or nearest available
target_dte_min = 30
target_dte = 37
target_dte_max = 45
profit_target_pct = 0.50    # close at 50% of credit received
stop_loss_pct = -2.0  # 3x stop loss
time_exit_dte = 7            # close when DTE <= 7
starting_cash = 100_000

spy_daily_fn = stock_folder.joinpath('SPY_.parquet')
_spy = pd.read_parquet(spy_daily_fn, engine="pyarrow")
_spy.set_index('quote_datetime', inplace=True)
_spy.sort_index(inplace=True)
dts = _spy.loc[start_date:end_date].index.values.tolist()




def on_expired(expired_position):
    expired_position.user_defined['exit_reason'] = 'expired'

df_signals = pd.read_csv(signals_fn, parse_dates=['effective_date'])
dfs = defaultdict(pd.DataFrame)
symbols = df_signals['symbol'].unique().tolist()
symbols.sort()
for symbol in symbols:
    fn = stock_folder.joinpath(f'{symbol}_.parquet')
    df = pd.read_parquet(fn, engine="pyarrow", columns=['quote_datetime', 'low'])
    df.set_index('quote_datetime', inplace=True)
    df.sort_index(inplace=True)
    dfs[symbol] = df

portfolio = OptionPortfolio(cash=starting_cash, start_date=start_date,end_date=end_date, check_margin_on_open=False)
portfolio.bind(position_expired=on_expired)

for dt in dts:
    print(dt)
    df_sig_dt = df_signals[df_signals['effective_date'] == dt]
    symbols = df_sig_dt['symbol'].unique().tolist()
    portfolio.next(dt, symbols)

    open_positions = portfolio.positions.copy()
    for p in open_positions:
        print(p.instance_id)
        symbol = p.symbol
        spot_price = p.spot_price
        open_low = p.user_defined['lod']
        pnl_pct = p.get_profit_loss_percent()
        dte = p.get_dte()
        df_ = dfs[symbol]
        if dt in df_.index:
            row = df_.loc[dt]
            today_low = row['low']
        else:
            today_low = open_low

        exit_reason = ''
        if dte < time_exit_dte:
            exit_reason='time'
        elif pnl_pct >= profit_target_pct:
            exit_reason='profit'
        elif pnl_pct < stop_loss_pct:
            exit_reason='stop'
        elif today_low < open_low:
            exit_reason='entry_day_low'

        if exit_reason != '':
            portfolio.close_position(p, exit_reason=exit_reason)

    for ticker in symbols:
        #print(ticker)
        sig_row = df_sig_dt[df_sig_dt['symbol'] == ticker].iloc[0]
        bmo_amc = sig_row['BMO_AMC']
        low = sig_row['low']
        gap = sig_row['gap_pct']
        option_chain = portfolio.option_chains[ticker]

        # find expiration to trade
        expirations = option_chain.expirations
        if len(expirations) == 0:
            continue

        exp = min(expirations, key=lambda x: abs((x - dt.date()).days - target_dte))
        dt_diff = (exp - dt.date()).days
        if dt_diff < target_dte_min or dt_diff > target_dte_max:
            continue # cannot find expiration within the range

        strikes = option_chain.expiration_strikes[exp]
        if len(strikes) == 0:
            continue

        options = [x for x in option_chain.options if x['expiration'] == exp and x['option_type'] == 'put']
        deltas = [x['delta'] for x in options]
        short_delta = min(deltas, key=lambda x: abs(x - -target_delta))

        if abs(short_delta) < target_delta_min or abs(short_delta) > target_delta_max:
            continue

        short_leg_data = next(x for x in options if x['delta'] == short_delta)
        short_strike = short_leg_data['strike']

        # find long leg
        spot_price = options[0]['spot_price']
        spread_width = spot_price * 0.03
        long_strike_target = short_strike - spread_width
        long_strike = min(strikes, key=lambda x: abs(x - long_strike_target))

        long_leg_data = next(x for x in options if x['strike'] == long_strike)
        my_options = [short_leg_data, long_leg_data]

        if short_strike == long_strike:
            continue

        # can't sell if there is no bid
        if not all(o['bid'] > 0.0 for o in my_options):
            continue
        if not all(o['ask'] > 0.0 for o in my_options):
            continue
        if not all(o['ask'] > o['bid'] for o in my_options):
            continue

        # liquidity - make sure bid/ask spread < 0.15 for short leg
        if not ((short_leg_data['ask'] - short_leg_data['bid']) / short_leg_data['price'] <= 0.15):
            continue

        vertical = Vertical.create(option_chain=option_chain, expiration=exp, option_type='put', long_strike=long_strike, short_strike=short_strike)
        spread_width = vertical.short_option.strike - vertical.long_option.strike
        price = vertical.short_option.get_open_price() - vertical.long_option.get_open_price()
        credit_pct = abs(vertical.price) / spread_width
        if credit_pct < 0.25:
            continue # not enough credit

        max_position_risk = portfolio.current_value * 0.02
        spread_width = vertical.short_option.strike - vertical.long_option.strike
        risk_per_contract = (spread_width - abs(vertical.price)) * 100
        shares = max(1, int(round((max_position_risk / risk_per_contract), 0)))

        portfolio.open_position(vertical, quantity=shares, lod=low, when=bmo_amc, gap=gap)

closed_positions = portfolio.closed_positions.copy()

trades = [{
        'id': x.instance_id,
        'symbol': x.symbol,
        'entry_date': x.get_open_datetime(),
        'exit_date': x.get_close_datetime(),
        'open_premium': x.get_trade_premium(),
        'expiration': x.expiration,
        'short_strike': x.short_option.strike,
        'long_strike': x.long_option.strike,
        'open_spot_price': x.short_option.trade_open_info.spot_price,
        'close_spot_price': x.spot_price,
        'vertical_open_price': x.get_trade_price(),
        'gross_pnl': x.get_profit_loss(),
        'net_pnl': (x.get_profit_loss() - x.get_fees()),
        'pnl_pct': x.get_profit_loss_percent(),
        'days_in_trade': x.get_days_in_trade(),
        'fees': x.get_fees(),
        'exit_reason': x.user_defined['exit_reason'],
        'when': x.user_defined['when'],
        'gap': x.user_defined['gap'],}
        for x in portfolio.closed_positions]

df_trades = pd.DataFrame(trades)
stats = trade_stats(df_trades)
print(stats)
output_folder = Path(r'D:\test_data\basic\pead')
fn = output_folder.joinpath('results_1.csv')
df_trades.to_csv(fn, index=False)
stats.to_csv(output_folder.joinpath('results_1_stats.csv'), index=True)



