"""
Gold -

30 min EMA - above: sell ATM put  sell $1 OTM call
             below: sell ATM call sell $1 OTM put

Enter 15 min after market open
Exit 15 min before market close

0 DTE

"""
import datetime
from pathlib import Path
import pandas as pd
import numpy as np
from matplotlib import pyplot as plt
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.strangle import Strangle
from options_framework.config import settings
from options_framework.utils.helpers import get_market_dates
import talib

options_root = Path(r'D:\options_data\intraday')
stock_data_folder = Path(r'E:\_data\thetadata\stock_data\data')

gld_stock_data = stock_data_folder.joinpath('GLD.parquet')
starting_cash = 100_000
risk_per_position = 0.50
start_date = datetime.datetime(2022, 1, 1)
end_date = datetime.datetime(2026, 3, 31)
enter_time = datetime.time(9,45)
exit_time = datetime.time(15,45)
profit_target = 0.5

settings['data_frequency'] = "intraday"
settings['minute_granularity'] = 1
portfolio = OptionPortfolio(cash=starting_cash, start_date=start_date, end_date=end_date)
df = pd.read_parquet(gld_stock_data, engine='pyarrow')
df.set_index('quote_datetime', inplace=True)
df['ema'] = talib.EMA(df['close'], timeperiod=30)
df = df[(df.index >= start_date) & (df.index <= end_date)]


ticker = 'GLD'
spread_width = 2

if __name__ == '__main__':
    dts = [x.date() for x in get_market_dates(start_date, end_date)]  #df.index.normalize().unique().tolist()

    for dt in dts:
        print(dt) # dt.to_pydatetime() == datetime.datetime(2020, 3, 9)
        df_dt = df[df.index.normalize() == pd.to_datetime(dt)]
        if df_dt.empty:
            continue

        entry_tm = pd.Timestamp(f"{dt} {enter_time}")
        exit_tm = pd.Timestamp(f"{dt} {exit_time}")

        # open option at 9:45
        row = df.loc[entry_tm]
        close = row['close']
        ema = row['ema']
        portfolio.next(entry_tm.to_pydatetime(), ticker)
        option_chain = portfolio.option_chains[ticker]
        options = option_chain.options
        if len(options) == 0:
            continue

        # only trade on 0DTE days
        expiration = option_chain.expirations[0]
        if dt != expiration:
            continue

        strikes = option_chain.expiration_strikes[expiration]

        atm_strike = min(strikes, key=lambda x: abs(x - close))

        if close >= ema:
            put_strike = atm_strike
            call_strike = min(strikes, key=lambda x: abs(x - (atm_strike + spread_width)))

        if close < ema:
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
        except Exception as e:
            print(f'{tm}: cannot open position', e)
            continue

        # Exit at 15 min before market close
        portfolio.next(exit_tm.to_pydatetime(), ticker)
        portfolio.close_position(strangle)
        pass

    print(portfolio.current_value)
    #print(portfolio.close_values)




