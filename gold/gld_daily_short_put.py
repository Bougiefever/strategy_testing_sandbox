import datetime
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.single import Single
import pandas as pd
import talib
from helpers import *

from pathlib import Path

options_file = Path(r'D:\options_data\daily\GLD\data\GLD.parquet')
stock_file = Path(r'D:\stock_data\daily\GLD.parquet')

start_date = datetime.datetime(2022, 12, 1)
end_date = datetime.datetime(2026, 4, 3)

starting_cash = 100_000
ticker = 'GLD'
ma_timeframe = 200
target_delta = 0.15
target_dte = 90
profit_target = 0.75
loss_limit = 2.0
risk_per_position = 0.10

def on_expired(expired_position):
    print(f'expired: {expired_position} {expired_position.get_profit_loss():.2f}')

def on_closed(close_position):
    print(f'closed: {close_position} {close_position.get_profit_loss():.2f}')


if __name__ == '__main__':

    df_stocks = pd.read_parquet(stock_file, engine='pyarrow')
    df_stocks = df_stocks.drop_duplicates(subset='quote_datetime', keep='first')
    df_stocks.set_index('quote_datetime', inplace=True)
    df_stocks['200_MA'] = talib.SMA(df_stocks['close'], timeperiod=ma_timeframe)
    df_stocks = df_stocks.loc[start_date:]

    dts = df_stocks.index.tolist()
    dts.sort()
    start_date = dts[0]
    end_date = dts[-1]


    portfolio = OptionPortfolio(cash=starting_cash, start_date=start_date, end_date=end_date)
    portfolio.bind(position_expired=on_expired)
    portfolio.bind(position_closed=on_closed)

    dts = [x.to_pydatetime() for x in dts]

    daily_records = []
    for dt in dts:
        print(dt, portfolio.current_value)
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
            pnl_pct = option.get_profit_loss_percent()
            exit_reason = ''
            close_trade = False
            if pnl_pct >= 0.5:
                exit_reason = 'profit'
                close_trade = True
            if pnl <= premium * 2:
                exit_reason = 'stop loss'
                close_trade = True
            if close_trade:
                portfolio.close_position(option, exit_reason=exit_reason)
                history = option.get_price_history()
                max_pct = max(h[3] for h in history)
                min_pct = min(h[3] for h in history)
                option.user_defined['peak_gain_pct'] = max_pct
                option.user_defined['max_drawdown_pct'] = min_pct

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
                pass
            except Exception as e:
                continue
                #print(e)
        daily_records.append({
            'date': dt,
            'close': stock_price,
            'portfolio_value': portfolio.current_value,
            'open_options': len(portfolio.positions),
            'in_trade': len(portfolio.positions) > 0,
        })

    if len(portfolio.positions) > 0:
        for option in portfolio.positions:
            portfolio.close_position(option, exit_reason='end of test')
            history = option.get_price_history()
            max_pct = max(h[3] for h in history)
            min_pct = min(h[3] for h in history)
            option.user_defined['peak_gain_pct'] = max_pct
            option.user_defined['max_drawdown_pct'] = min_pct

    traded_options = portfolio.closed_positions.copy()
    trades = []
    for option in traded_options:
        entry_dt = option.get_open_datetime()
        exit_dt = option.get_close_datetime()
        trades.append({
            'id': option.instance_id,
            'symbol': option.symbol,
            'expiration': option.expiration,
            'strike': option.strike,
            'option_type': option.option_type,
            'entry_dt': option.get_open_datetime(),
            'exit_dt': option.get_close_datetime(),
            'open_premium': option.get_trade_premium(),
            'open_spot_price': option.option.trade_open_info.spot_price,
            'close_spot_price': option.spot_price,
            'entry_px': option.get_trade_price(),
            'exit_px': option.get_closed_price(),
            'pnl': option.get_profit_loss(),
            'pnl_pct': option.get_profit_loss_percent(),
            'qty': option.option.trade_open_info.quantity,
            'fees': option.get_fees(),
            'exit_reason': option.user_defined['exit_reason'],
            'holding_period': int((option.get_close_datetime() - option.get_open_datetime()).days),
            'peak_gain_pct': option.user_defined['peak_gain_pct'],
            'max_drawdown_pct': option.user_defined['max_drawdown_pct'],
        })

    print(portfolio.current_value)

    trades_df = pd.DataFrame(trades)
    daily_df = pd.DataFrame(daily_records)

    portfolio_stats, trade_stats = print_report(ticker, trades_df, daily_df, 'daily')
    pass