import datetime
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.single import Single
import pandas as pd
import talib


from pathlib import Path

options_file = Path(r'D:\options_data\daily\GLD\data\GLD.parquet')
stock_file = Path(r'D:\stock_data\daily_stock_prices\GLD_.parquet')



starting_cash = 100_000
ticker = 'GLD'
ma_timeframe = 200
target_delta = 0.15
target_dte = 90
profit_target = 0.50
loss_limit = 2.0
risk_per_position = 0.05

def on_expired(expired_position):
    print(f'expired: {expired_position} {expired_position.get_profit_loss():.2f}')

def on_closed(close_position):
    print(f'closed: {close_position} {close_position.get_profit_loss():.2f}')


if __name__ == '__main__':


    df_stocks = pd.read_parquet(stock_file, engine='pyarrow')
    df_stocks.set_index('quote_datetime', inplace=True)


    dts = df_stocks.index.tolist()
    dts.sort()
    start_date = dts[0]
    end_date = dts[-1]
    df_stocks['200_MA'] = talib.SMA(df_stocks['close'], timeperiod=ma_timeframe)

    portfolio = OptionPortfolio(cash=starting_cash, start_date=start_date, end_date=end_date)
    portfolio.bind(position_expired=on_expired)
    portfolio.bind(position_closed=on_closed)

    dts = [x.to_pydatetime() for x in dts]

    for dt in dts:
        #print(dt, portfolio.current_value)
        portfolio.next(dt, ticker, portfolio.cash, portfolio.portfolio_margin_allocation)
        option_chain = portfolio.option_chains[ticker]
        if len(option_chain.options) == 0:
            continue
        df_dt = df_stocks.loc[dt]
        stock_price = df_dt['close']
        sma = df_dt['200_MA']

        for option in portfolio.positions:
            premium = option.get_trade_premium()
            pnl = option.get_profit_loss()
            if pnl >= (premium * -1) * 0.5 or pnl <= premium * 2:
                portfolio.close_position(option.instance_id)

        if stock_price > sma:

            target_exp = (dt + datetime.timedelta(days=target_dte)).date()
            expiration = min(option_chain.expirations, key=lambda x: abs(target_exp - x))

            options = option_chain.options.copy()
            deltas = [abs(x['delta']) for x in options if x['option_type'] == 'put']
            put_delta = min(deltas, key=lambda x: abs(x - target_delta))
            put_data = next(x for x in options if x['option_type'] == 'put' and x['delta'] == -(put_delta))

            try:
                option = Single.create(option_chain=option_chain, expiration=expiration, strike=put_data['strike'], option_type='put')
                margin = option.get_required_margin(-1)
                allowed_risk = portfolio.cash * risk_per_position
                quantity = int(allowed_risk // margin * -1)
                portfolio.open_position(option, quantity=quantity, margin_percent=0.50)
            except Exception as e:
                continue
                #print(e)

    print(portfolio.current_value)