import pandas as pd
import numpy as np
from pathlib import Path
import datetime
import pyarrow as pa
from pyarrow import parquet as pq
from pyarrow import compute as pc
import math
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.single import Single
from utility import *
from collections import defaultdict
import talib

stock_folder = Path(r'D:\stock_data\daily')
signals_fn = Path(r'D:\test_data\basic\pead\signals.csv')

# start_date = datetime.datetime(2022, 1, 3)
# end_date = datetime.datetime(2024, 12, 29)
start_date = datetime.datetime(2025, 1, 2)
end_date = datetime.datetime(2026, 2, 20)

# Define strategy parameters
# target_delta_min = 0.20
target_delta = 0.35
# target_delta_max = 0.40
# spread_width = 10           # dollars, or nearest available
target_dte_min = 90
target_dte = 105
target_dte_max = 120
# profit_target_pct = 0.50
stop_loss_pct = -.50
time_exit_dte = 40
starting_cash = 100_000
ma_filter = 200
filter_name = f'{ma_filter}ma'

spy_daily_fn = stock_folder.joinpath('SPY_.parquet')
_spy = pd.read_parquet(spy_daily_fn, engine="pyarrow")
_spy.set_index('quote_datetime', inplace=True)
_spy[filter_name] = talib.SMA(_spy['close'].to_numpy(float), timeperiod=ma_filter)
_spy[filter_name] = _spy[filter_name].shift(1)
_spy.sort_index(inplace=True)

dts = _spy.loc[start_date:end_date].index.values.tolist()

vix_fn = stock_folder.joinpath('VIX_.parquet')
_vix = pd.read_parquet(vix_fn, engine="pyarrow")
_vix.set_index('quote_datetime', inplace=True)
_vix.sort_index(inplace=True)
_vix = _vix.loc[start_date:end_date]
vix = 0

def on_expired(expired_position):
    expired_position.user_defined['exit_reason'] = 'expired'

df_signals = pd.read_csv(signals_fn, parse_dates=['effective_date'])
# only trade calls
df_signals = df_signals[df_signals['gap_pct'] > 0]
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
        #print(p.instance_id)
        symbol = p.symbol
        spot_price = p.spot_price
        pnl_pct = p.get_profit_loss_percent()
        open_spot = p.option.trade_open_info.spot_price
        price_chg = (spot_price - open_spot) / spot_price
        days_in_trade = p.get_days_in_trade()

        exit_reason = ''
        to_close = False
        if price_chg <= -0.02 and days_in_trade == 1:
            exit_reason = 'price'
            to_close = True
        elif pnl_pct < stop_loss_pct:
            exit_reason='stop'
            to_close = True
        elif p.get_dte() <= time_exit_dte:
            exit_reason='time'
            to_close = True

        if to_close:
            portfolio.close_position(p, exit_reason=exit_reason)

    if dt in _vix.index:
        vix = _vix.loc[dt, 'close']
    if vix >= 20:
        continue

    for ticker in symbols:
        #print(ticker)
        sig_row = df_sig_dt[df_sig_dt['symbol'] == ticker].iloc[0]
        bmo_amc = sig_row['BMO_AMC']
        low = sig_row['low']
        gap = sig_row['gap_pct']
        option_type = 'call' if gap > 0 else 'put'
        option_chain = portfolio.option_chains[ticker]

        # find expiration to trade
        expirations = option_chain.expirations
        if len(expirations) == 0:
            continue

        exp = min(expirations, key=lambda x: abs((x - dt.date()).days - target_dte))
        dt_diff = (exp - dt.date()).days
        if dt_diff <= target_dte_min or dt_diff >= target_dte_max:
            continue # cannot find expiration within the range

        strikes = option_chain.expiration_strikes[exp]
        if len(strikes) == 0:
            continue

        options = [x for x in option_chain.options if x['expiration'] == exp and x['option_type'] == option_type]
        if len(options) == 0:
            continue
        deltas = [x['delta'] for x in options]
        target = target_delta if option_type == 'call' else -target_delta
        delta = min(deltas, key=lambda x: abs(x - target))

        # if abs(delta) < target_delta_min or abs(delta) > target_delta_max:
        #     continue

        option_data = next(x for x in options if x['delta'] == delta)
        strike = option_data['strike']

        # find long leg
        spot_price = options[0]['spot_price']

        # can't sell if there is no bid
        if not all(o['bid'] > 0.0 for o in [option_data]):
            continue
        if not all(o['ask'] > 0.0 for o in [option_data]):
            continue
        if not all(o['ask'] > o['bid'] for o in [option_data]):
            continue

        # liquidity - make sure bid/ask spread < 0.15 for short leg
        if not ((option_data['ask'] - option_data['bid']) / option_data['price'] <= 0.15):
            continue

        option_position = Single.create(option_chain=option_chain, expiration=exp, strike=strike, option_type=option_type)
        #print(option_position.instance_id)

        max_position_risk = portfolio.current_value * 0.02
        risk_per_contract = option_position.price * 100
        shares = max(1, int(round((max_position_risk / risk_per_contract), 0)))

        portfolio.open_position(option_position, quantity=shares, lod=low, when=bmo_amc, gap=gap)

open_positions = portfolio.positions.copy()
for p in open_positions:
    portfolio.close_position(p, exit_reason='end')

closed_positions = portfolio.closed_positions.copy()

trades = [{
        'id': x.instance_id,
        'symbol': x.symbol,
        'entry_date': x.get_open_datetime(),
        'exit_date': x.get_close_datetime(),
        'open_premium': x.get_trade_premium(),
        'expiration': x.expiration,
        'strike': x.option.strike,
        'open_spot_price': x.option.trade_open_info.spot_price,
        'close_spot_price': x.spot_price,
        'open_price': x.get_trade_price(),
        'gross_pnl': x.get_profit_loss(),
        'net_pnl': (x.get_profit_loss() - x.get_fees()),
        'pnl_pct': x.get_profit_loss_percent(),
        'qty': x.option.trade_open_info.quantity,
        'days_in_trade': x.get_days_in_trade(),
        'fees': x.get_fees(),
        'when': x.user_defined['when'],
        'gap': x.user_defined['gap'],}
        for x in portfolio.closed_positions]

df_trades = pd.DataFrame(trades)
stats = trade_stats(df_trades)
print(stats)
output_folder = Path(r'D:\test_data\basic\pead')
fn = output_folder.joinpath('long_trades_201.csv')
df_trades.to_csv(fn, index=False)
stats.to_csv(output_folder.joinpath('stats_201.csv'), index=True)


trade_updates = []
for p in closed_positions:
    symbol = p.symbol
    history  = p.option.history
    entry_price = history[0][1]
    option_type = p.option_type

    for h in history:
        quote_date = h[0]
        price = h[1]
        spot_price = h[2]
        dte = h[3]
        pct_of_entry = price / entry_price
        update = {'symbol': symbol,
                  'option_type': option_type,
                  'dte': dte,
                  'date': quote_date,
                  'spot_price': spot_price,
                  'price': price,
                  'pct_of_entry': pct_of_entry,
                  }
        trade_updates.append(update)

df_updates = pd.DataFrame(trade_updates)
fn = output_folder.joinpath('updates_201.csv')
df_updates.to_csv(fn, index=False)




