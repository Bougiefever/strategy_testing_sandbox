"""
No FOMC, NO CPI. 30% TP and 40% SL. Stop loss only happens on 1DTE. Entry time is either 11.00 a.m. or 2:30 pm. 60 WIDE 1 DTE.
"""
import pandas as pd
import numpy as np
import datetime
from pathlib import Path
from utility import *

from options_framework.option_types import OptionPositionType
from options_framework.utils.helpers import get_market_dates
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.butterfly import Butterfly

def my_position_expired(position):
    pnl = position.get_profit_loss()
    holding_period = p.get_days_in_trade()
    print(position.expiration, position, 'expired', pnl)
    position.user_defined['exit_reason'] = 'expired'
    position.user_defined['holding_period'] = holding_period

options_root = Path(r'D:\options_data\daily')
output_folder = Path(r'D:\test_data\spx_ic\spx1dte')

start_date = datetime.datetime(2016, 1, 1)
end_date = datetime.datetime(2022, 12, 31)

starting_cash = 100_000
wing = 60
ticker = 'SPXW'
target_dte = 1
tp = 0.30
sl = -0.40

start_time = datetime.time(9,30)
entry_time1 = datetime.time(11,0)
entry_time2 = datetime.time(14,30)
end_time = datetime.time(16, 0)

dts = get_market_dates(start_date=start_date, end_date=end_date)
portfolio = OptionPortfolio(cash=starting_cash, start_date = start_date, end_date = end_date, check_margin_on_open=False)
portfolio.bind(position_expired=my_position_expired)

def get_day_times(dt: datetime.datetime, granularity: int) -> list[datetime.datetime]:
    tm = start_time
    today = []
    while tm <= end_time:
        new_dt = datetime.datetime.combine(dt, tm)
        today.append(new_dt)
        new_dt += datetime.timedelta(minutes=granularity)
        tm = new_dt.time()
    return today

if __name__ == "__main__":
    daily_records = []
    for dt in dts:
        times = get_day_times(dt, 5)
        if len(portfolio.positions) == 0:
            times = [x for x in times if x.time() >= entry_time1]
        for i in range(len(times)):
            dtt = times[i]
            portfolio.next(dtt, ticker)
            open_positions = portfolio.positions.copy()
            for p in open_positions:
                pnl = p.get_profit_loss()
                pnl_pct = p.get_profit_loss_percent()
                peak_gain_pct = max(p.user_defined['max_drawdown_pct'], pnl_pct)
                max_drawdown_pct = min(p.user_defined['max_drawdown_pct'], pnl_pct)
                dte = p.get_dte()
                holding_period = p.get_days_in_trade()
                exit_trade = False
                if pnl_pct <= sl and dte == 0:
                    exit_trade = True
                    exit_reason = 'stop loss'
                elif pnl_pct >= tp:
                    exit_trade = True
                    exit_reason = 'profit'
                if exit_trade:
                    portfolio.close_position(p, exit_reason=exit_reason, holding_period=holding_period,
                                             peak_gain_pct=peak_gain_pct, max_drawdown_pct=max_drawdown_pct)
                    print(dt, p, exit_reason, pnl)

            if dtt.time() == entry_time1 or dtt.time() == entry_time2:
                option_chain = portfolio.option_chains[ticker]
                expirations = option_chain.expirations
                if len(expirations) == 0:
                    continue
                exp = min(expirations, key=lambda x: abs((x - dt.date()).days - target_dte))
                dt_diff = (exp - dt.date()).days
                if dt_diff != target_dte:
                    continue

                options = option_chain.options
                if len(options) == 0:
                    continue

                entry_type = 'entry_1' if dtt.time() == entry_time1 else 'entry_2'

                strikes = option_chain.expiration_strikes[exp]
                spot_price = options[0]['spot_price']
                atm_strike = min(strikes, key=lambda x: abs(x-spot_price))
                upper_wing_target = atm_strike + wing
                upper_wing = min(strikes, key=lambda x: abs(x-upper_wing_target))
                lower_wing_target = atm_strike - wing
                lower_wing = min(strikes, key=lambda x: abs(x-lower_wing_target))

                butterfly = Butterfly.create(option_chain=option_chain, expiration=exp, option_type='call',
                                             center_strike=atm_strike, lower_strike=lower_wing, upper_strike=upper_wing,
                                             position_type=OptionPositionType.LONG)

                portfolio.open_position(butterfly, quantity=1, entry_type=entry_type, spread_width=wing,
                                        peak_gain_pct=0.0, max_drawdown_pct=0.0)

        option_chain = portfolio.option_chains[ticker]
        options = option_chain.options
        if len(options) == 0:
            continue
        spot_price = options[0]['spot_price']
        in_trade = len(portfolio.positions) > 0
        daily_record = {
            'date': dt,
            'close': spot_price,
            'portfolio_value': portfolio.current_value,
            'in_trade': in_trade,
        }
        daily_records.append(daily_record)

    open_positions = portfolio.positions.copy()
    for p in open_positions:
        portfolio.close_position(p, exit_reason='end_of_data')

    trades = [{
        'id': x.instance_id,
        'symbol': x.symbol,
        'option_type': x.option_type,
        'entry_date': x.get_open_datetime(),
        'exit_date': x.get_close_datetime(),
        'open_premium': x.get_trade_premium(),
        'expiration': x.expiration,
        'open_spot_price': x.lower_option.trade_open_info.spot_price,
        'close_spot_price': x.spot_price,
        'entry_price': x.get_trade_price(),
        'exit_price': x.get_closed_price(),
        'pnl': x.get_profit_loss(),
        'pnl_pct': x.get_profit_loss_percent(),
        'qty': x.lower_option.trade_open_info.quantity,
        'fees': x.get_fees(),
        'center_strike': x.center_option.strike,
        'upper_strike': x.upper_option.strike,
        'lower_strike': x.lower_option.strike,
        'intrinsic_value': max(0, x.user_defined['spread_width'] - abs(x.spot_price - x.center_option.strike)),
        'exit_reason': x.user_defined['exit_reason'],
        'holding_period': x.user_defined['holding_period'],
        'peak_gain_pct': x.user_defined['peak_gain_pct'],
        'max_drawdown_pct': x.user_defined['max_drawdown_pct'],
        'entry_type': x.user_defined['entry_type'],}
        for x in portfolio.closed_positions]

    df_trades = pd.DataFrame(trades)
    df_daily = pd.DataFrame(daily_records)
    df_daily.set_index('date', inplace=True)

    p_stats, t_stats = print_report(ticker, df_trades, df_daily, strategy='SPX 1DTE Butterfly')

    df_trades.to_csv(output_folder.joinpath('trades_2.csv'), index=False)
    df_daily.to_csv(output_folder.joinpath('daily_record_2.csv'), index=False)
    p_stats.to_csv(output_folder.joinpath('port_stats_2.csv'), index=True)
    t_stats.to_csv(output_folder.joinpath('trade_stats_2.csv'), index=True)



