import pandas as pd
import numpy as np
from pathlib import Path
import datetime
import talib
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.vertical import Vertical
from collections import defaultdict
from utility import *

options_root = Path(r'D:\options_data\daily')
stocks_folder = Path(r'D:\stock_data\daily')
calcs_folder = Path(r'D:\stock_data\calcs')
output_folder = Path(r'D:\test_data\basic')
tickers = ['SPY', 'QQQ', 'IWM', 'DIA']
start_date = datetime.datetime(2022, 1, 1)
end_date = datetime.datetime(2024, 12, 31)
starting_cash = 100_000
target_dte = 45
iv_rv_limit = 1.5
short_delta_target = 0.30
long_delta_target = 0.15
tp_pnl = 0.50
exit_dte = 21
stop_pnl = -1.0
position_risk = 0.02
portfolio_risk = 0.25
ma_timeframe = 50
spread_width_target = 10

options_folders = [options_root.joinpath(x) for x in tickers]
stock_files = [stocks_folder.joinpath(f'{x}_.parquet') for x in tickers]

dfs = defaultdict(pd.DataFrame)
atm_iv_dfs = defaultdict(pd.DataFrame)
for stock_file in stock_files:
    ticker = stock_file.stem[:-1]
    calc_file = calcs_folder.joinpath(f'{stock_file.stem[:-1]}_calcs.parquet')
    df = pd.read_parquet(stock_file, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume'], engine='pyarrow')
    df['ma'] = talib.SMA(df['close'].to_numpy(float), timeperiod=ma_timeframe)
    df_calcs = pd.read_parquet(calc_file, engine='pyarrow')
    df = df.merge(df_calcs, on=['symbol', 'quote_datetime'], how='inner')
    df.set_index('quote_datetime', inplace=True)
    df = df.loc[start_date:end_date]
    df.sort_index(inplace=True)
    dfs[ticker] = df
    iv_file = options_root.joinpath(f'{ticker}', 'data', f'{ticker}_iv.parquet')
    df_iv = pd.read_parquet(iv_file, engine='pyarrow')
    df_iv.set_index('quote_datetime', inplace=True)
    df_iv = df_iv.loc[start_date:end_date]
    atm_iv_dfs[ticker] = df_iv

dts = [d.to_pydatetime() for d in dfs['SPY'].index.tolist()]
portfolio = OptionPortfolio(cash=starting_cash, start_date=start_date, end_date=end_date, check_margin_on_open=False)

if __name__ == '__main__':
    for dt in dts:
        portfolio.next(dt, tickers)
        print(dt)
        check_positions = portfolio.positions.copy()
        for p in check_positions:
            #print(p.instance_id)
            try:
                sp = p.short_option.get_closing_price()
                lp = p.long_option.get_closing_price()
                pp = (lp - sp) * p.quantity
            except ValueError:
                pp = p.price * p.quantity
            entry_price = p.get_trade_price()

            dte = p.get_dte()
            pnl = p.get_profit_loss()
            pnl_pct = p.get_profit_loss_percent()
            reason = None
            if dte < exit_dte:
                reason = 'time stop'
            elif pnl_pct >= tp_pnl:
                reason = 'profit stop'
            # elif pp <= entry_price * 2:
            #     reason = 'stop loss'
            if reason:
                portfolio.close_position(p, reason=reason)

            pass
        for ticker in tickers:
            df = dfs[ticker]
            if dt not in df.index:
                continue
            df_dt = df.loc[dt]
            ma = df_dt['ma']
            close = df_dt['close']
            if close < ma:
                continue

            rv = df_dt['rv20']

            # get options info for trade
            iv_df = atm_iv_dfs[ticker]
            df_iv_dt = iv_df.loc[dt]
            option_chain = portfolio.option_chains[ticker]
            expirations = option_chain.expirations
            exp_target_dt = dt + datetime.timedelta(days=target_dte)
            exp = min(expirations, key=lambda x: abs(x - exp_target_dt.date()).days)
            strikes = option_chain.expiration_strikes[exp]

            iv30 = df_iv_dt[df_iv_dt['expiration'] == pd.to_datetime(exp)].iloc[0]
            atm_iv = iv30['atm_iv']
            iv_rv = atm_iv / rv
            if iv_rv < iv_rv_limit:
                continue
            options = [x for x in option_chain.options if x['expiration'] == exp and x['option_type'] == 'put']
            deltas = [x['delta'] for x in options]

            short_delta = min(deltas, key=lambda x: abs(x - -short_delta_target))
            short_option_data = next(x for x in options if x['delta'] == short_delta)
            short_strike = short_option_data['strike']

            long_strike_target = short_strike - spread_width_target
            long_strike = min(strikes, key=lambda x: abs(x - long_strike_target))

            if long_strike == short_strike:
                continue

            long_option_data = next(x for x in options if x['strike'] == long_strike)
            if short_option_data['bid'] - long_option_data['ask'] < 0.20:
                continue


            vertical = Vertical.create(option_chain, exp, 'put', long_strike=long_strike, short_strike=short_strike)


            available_cash = portfolio.cash * portfolio_risk
            max_position_risk = portfolio.current_value * position_risk
            spread_width = vertical.short_option.strike - vertical.long_option.strike
            risk_per_contract = (spread_width - abs(vertical.price)) * 100
            shares = max(1, int(round((max_position_risk / risk_per_contract), 0)))

            try:
                portfolio.open_position(vertical, quantity=shares, iv_rv=iv_rv)
                premium = vertical.get_trade_premium()
            except ValueError as ve:
                print(ve)
            except Exception as ex:
                print(ex)

    # check_positions = portfolio.positions.copy()
    # for p in check_positions:
    #     # print(p.instance_id)
    #     reason = 'end_of_test'
    #     portfolio.close_position(p, reason=reason)

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
        'iv_rv_ratio': x.user_defined['iv_rv'],
        'exit_reason': x.user_defined['reason'],}
        for x in portfolio.closed_positions]

    df_trades = pd.DataFrame(trades)
    stats = trade_stats(df_trades)
    print(stats)
    fn = output_folder.joinpath(f'results_3.csv')
    df_trades.to_csv(fn, index=False)
    stats.to_csv(output_folder.joinpath('results_3_stats.csv'), index=True)
