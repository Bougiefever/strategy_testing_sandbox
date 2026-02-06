import datetime
from pathlib import Path
import pandas as pd
import numpy as np
from matplotlib import pyplot as plt
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.strangle import Strangle
import talib

options_root = Path(r'D:\options_data\daily')
stock_data_folder = Path(r'D:\stock_data\intraday\market\etfs')

gld_stock_data = stock_data_folder.joinpath('GLD.parquet')
starting_cash = 100_000
risk_per_position = 0.50
start_date = datetime.datetime(2015, 1, 1)
end_date = datetime.datetime(2025, 1, 3)
profit_target = 0.5

portfolio = OptionPortfolio(cash=starting_cash, start_date=start_date, end_date=end_date)
df = pd.read_parquet(gld_stock_data, engine='pyarrow')
df.set_index('quote_datetime', inplace=True)
df = df[(df.index >= start_date) & (df.index <= end_date)]
df['ema'] = talib.EMA(df['close'], timeperiod=30)

ticker = 'GLD'
spread_width = 2

if __name__ == '__main__':
    dts = df.index.normalize().unique().tolist()

    for dt in dts:
        #print(dt) # dt.to_pydatetime() == datetime.datetime(2020, 3, 9)
        df_dt = df[df.index.normalize() == dt]

        # make sure this is a normal day - not a half day
        last_dt = df_dt.iloc[-1].name
        if last_dt.hour != 15:
            continue

        for tm, row in df_dt.iterrows():
            tm = tm.to_pydatetime()
            ema_tm = row['ema']
            portfolio.next(tm, ticker)
            if np.isnan(ema_tm):
                continue
            if tm.time() >= datetime.time(9, 45) and (len(portfolio.positions) == 0):

                option_chain = portfolio.option_chains[ticker]
                if len(option_chain.options) == 0:
                    continue
                expiration = option_chain.expirations[0]

                # only want to trade 0-dte options
                if expiration != dt.date():
                    break


                spot_price = row['close']

                # if stock price is above ema, sell atm put and $1 otm call
                # if stock price is below ema, sell atm call and $1 otm put
                strikes = option_chain.expiration_strikes[expiration] # get all the strikes available for this expiration
                atm_strike = min(strikes, key=lambda x: abs(x - spot_price)) # find closest to atm strike

                if spot_price > ema_tm:
                    put_strike = atm_strike
                    call_strike = min(strikes, key=lambda x: abs(x - (atm_strike + spread_width)))
                else:
                    call_strike = atm_strike
                    put_strike = min(strikes, key=lambda x: abs(x - (atm_strike - spread_width)))

                try:
                    strangle = Strangle.create(option_chain=option_chain,
                                               expiration=expiration,
                                               call_strike=call_strike,
                                               put_strike=put_strike)
                    margin = strangle.get_required_margin(-1)
                    allowed_risk = portfolio.cash * risk_per_position
                    quantity = int(allowed_risk // margin * -1)
                    portfolio.open_position(strangle, quantity=quantity)
                    continue
                except Exception as e:
                    #print(f'{tm}: cannot open position', e)
                    continue

            if tm.time() > datetime.time(9, 45) and (len(portfolio.positions) == 1):

                open_strangle = portfolio.positions[0]
                quantity = open_strangle.quantity
                premium = open_strangle.get_trade_premium()
                pnl = open_strangle.get_profit_loss()
                pnl_pct = open_strangle.get_profit_loss_percent()

                if pnl <= premium * 2 or pnl_pct >= 0.5 or tm.time() >= datetime.time(15,45):
                    portfolio.close_position(open_strangle.instance_id)
                    call_pnl = open_strangle.call.trade_close_info.profit_loss
                    put_pnl = open_strangle.put.trade_close_info.profit_loss
                    fees = open_strangle.get_fees()
                    print(f'{open_strangle.instance_id}, {dt}, {portfolio.current_value:.2f}, {quantity}, {open_strangle.get_profit_loss():.2f}, {call_pnl:.2f}, {put_pnl:.2f}, {fees:.2f}')
                    break

    print(portfolio.current_value)
    #print(portfolio.close_values)




