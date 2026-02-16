import pandas as pd
import numpy as np
from pathlib import Path
import datetime
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.calendar import Calendar
import pyarrow as pa
from pyarrow import parquet as pq


start_date = datetime.datetime(2023, 1, 1)
end_date = datetime.datetime(2025, 1, 1)

output_folder = Path(r'D:\test_data\forward_factor\test1')
options_root = Path(r'D:\options_data\daily')
option_dirs = list(options_root.glob('*'))

def on_expired(expired_position):
    print(f'expired {expired_position}')

names = [o.name for o in option_dirs]
for od in option_dirs:
    ticker = od.name
    print(ticker)
    data_fn = od.joinpath('data', f'{ticker}.parquet')
    ff_fn = od.joinpath('data', f'{ticker}_ff_pairs.parquet')
    if not ff_fn.exists():
        continue
    df = pd.read_parquet(data_fn, engine='pyarrow')
    df.set_index('quote_datetime', inplace=True)
    df = df[(df.index >= start_date) & (df.index <=end_date)]
    df_ff = pd.read_parquet(ff_fn, engine='pyarrow')
    df_ff.set_index('quote_datetime', inplace=True)
    df_ff = df_ff.loc[start_date:end_date]
    df_ff = df_ff.sort_values(by=['quote_datetime', 'forward_factor'], ascending=[True,False])
    portfolio = OptionPortfolio(cash=0.0, start_date=start_date, end_date=end_date, check_margin_on_open=False)
    portfolio.bind(position_expired=on_expired)

    dts = df.index.unique().tolist()

    for dt in dts:
        #print(dt)
        portfolio.next(dt.to_pydatetime(), ticker)
        # check to see if we need to close
        check_positions = portfolio.positions.copy()
        for p in check_positions:
            if p.front_option.expiration <= dt.date():
                #print(p.instance_id)
                portfolio.close_position(p)
                # # close back option, let front option expire
                # p.back_option.close_trade(quantity=p.quantity)

        if not dt in df_ff.index:
            continue
        ff_dt = df_ff.loc[dt:dt]
        row = ff_dt.iloc[0] # sorted by ff
        front_exp = row['front_exp'].date()
        back_exp = row['back_exp'].date()

        # Find closest strike to spot price that exists for both expirations
        option_chain = portfolio.option_chains[ticker]
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
                   and x['expiration'] >= front_exp
                   and x['expiration'] <= back_exp
                   and x['strike'] == strike]

        # can't sell if there is no bid
        if any(o['bid'] == 0.0 for o in options):
            continue

        if any(o['price'] == 0.0 for o in options):
            continue

        # liquidity - make sure bid/ask spread < 0.15 of spot price
        if not all(((o['ask'] - o['bid']) / o['price'] / spot_price) <= 0.15 for o in options):
            # print(f'{dt} cannot open: {strangle} - bid/ask spread > 0.15 of spot')
            continue

        calendar = Calendar.create(option_chain=option_chain, strike=strike, front_expiration=front_exp,
                                   back_expiration=back_exp, option_type='call')
        if calendar.price == 0.0:
            continue

        portfolio.open_position(calendar, 1)

    check_positions = portfolio.positions.copy()
    for p in check_positions:
        p.close_trade()

    current_trades = [{'ticker': x.symbol, 'exp': x.front_option.expiration, 'pnl': x.get_profit_loss(),
                       'pnl_pct':x.get_profit_loss_percent(), 'open_dt': x.get_open_datetime(),
                       'close_dt': x.get_close_datetime(), 'days_in_trade': x.get_days_in_trade(),
                       'spot_price': x.front_option.spot_price, 'price': x.price,
                       'strike': x.front_option.strike} for x in portfolio.closed_positions]



    df_trades = pd.DataFrame(current_trades)
    if df_trades.empty:
        continue
    ta = pa.Table.from_pandas(df_trades)
    schema = ta.schema.remove_metadata()
    ta = ta.replace_schema_metadata(schema.metadata)
    fn = output_folder.joinpath(f'{ticker}_ff_pairs.parquet')
    pq.write_table(ta, fn)
