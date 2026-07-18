"""
0DTE Options trading - 5-min ORB range breakout
https://options.cafe/blog/0dte-opening-range-breakout-strategy-spy-backtested-results/

Testing with SPX

FOR each trading day:

    # Check if a 0DTE option exists expiring today
    IF no SPX options expire today: SKIP

    yesterday  = daily_signals[prior_trading_day]
    stretch    = yesterday.Stretch

    # Opening Range: 9:30:00 - 9:34:00
    or_bars    = 1-min bars from 9:30 through 9:34
    OR_High    = max(High) of or_bars
    OR_Low     = min(Low) of or_bars
    OR_Width   = OR_High - OR_Low

    # OR width filter: skip if above 20-day MA of OR width
    IF OR_Width > moving_avg_20(OR_Width): SKIP

    # Entry levels on the underlying
    long_entry  = OR_High + stretch
    short_entry = OR_Low  - stretch

    state = FLAT
    entry_cutoff = 10:30

    FOR each 1-min bar from 9:35 to 15:59:

        IF state == FLAT:
            IF bar.time > entry_cutoff: CONTINUE

            IF bar.High >= long_entry:
                # Buy a 0DTE call
                # Select the call closest to 30-delta at this moment
                # Use the ASK price for entry (you're buying)
                option_entry = call.ask
                underlying_fill = max(bar.Open, long_entry)
                state = LONG_CALL
                record: entry_time, strike, delta, option_entry

            ELSE IF bar.Low <= short_entry:
                # Buy a 0DTE put
                # Select the put closest to 30-delta at this moment
                # Use the ASK price for entry (you're buying)
                option_entry = put.ask
                underlying_fill = min(bar.Open, short_entry)
                state = LONG_PUT
                record: entry_time, strike, delta, option_entry

        ELSE IF state == LONG_CALL:
            # Calculate underlying stop/target from fill
            stop_level   = underlying_fill - stretch
            target_level = underlying_fill + stretch * 2.0

            IF bar.Low <= stop_level:
                # Exit: sell the call at BID at this moment
                option_exit = call.bid
                result = "stop"
                state = FLAT

            ELSE IF bar.High >= target_level:
                option_exit = call.bid
                result = "target"
                state = FLAT

        ELSE IF state == LONG_PUT:
            stop_level   = underlying_fill + stretch
            target_level = underlying_fill - stretch * 2.0

            IF bar.High >= stop_level:
                option_exit = put.bid
                result = "stop"
                state = FLAT

            ELSE IF bar.Low <= target_level:
                option_exit = put.bid
                result = "target"
                state = FLAT

    # EOD: option expires, value is intrinsic or zero
    IF state != FLAT:
        IF LONG_CALL:
            option_exit = max(0, underlying_close - strike)
        ELSE:
            option_exit = max(0, strike - underlying_close)
        result = "expiry"

    IF trade was taken:
        pnl = option_exit - option_entry   # per contract
        record: date, direction, strike, delta,
                option_entry, option_exit, result, pnl
"""
import options_framework.utils.helpers
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime
from pathlib import Path
from collections import deque
import talib
from utility import *
import argparse
import time
from collections import defaultdict

from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.single import Single
from options_framework.option_types import OptionStatus

def on_expired(expired_position):
    expired_position.user_defined['exit_reason'] = 'expired'

def get_day_times(dt: datetime.datetime, granularity: int) -> list[datetime.datetime]:
    tm = start_time
    today = []
    while tm <= end_time:
        new_dt = datetime.datetime.combine(dt, tm)
        today.append(new_dt)
        new_dt += datetime.timedelta(minutes=granularity)
        tm = new_dt.time()
    return today

def get_entry(long_entry_dt, short_entry_dt, long_entry_px, short_entry_px, stretch):
    if pd.notna(long_entry_dt):
        if pd.isna(short_entry_dt) or long_entry_dt < short_entry_dt:
            entry_px = long_entry_px
            entry_dt = long_entry_dt
            stop_px = entry_px - stretch
            target_px = entry_px + stretch * 2.0
            return entry_px, entry_dt, stop_px, target_px, 'long'

    if pd.notna(short_entry_dt):
        entry_px = short_entry_px
        entry_dt = short_entry_dt
        stop_px = entry_px + stretch
        target_px = entry_px - stretch * 2.0
        return entry_px, entry_dt, stop_px, target_px, 'short'
    return None, None, None, None, None

def get_exit(profit_dt, stop_dt, eod_dt, profit_px, stop_px, eod_px):
    if pd.notna(profit_dt):
        if pd.isna(stop_dt) or profit_dt < stop_dt:
            exit_px = profit_px
            exit_dt = profit_dt
            exit_reason = 'profit'
            return exit_px, exit_dt, exit_reason
    if pd.notna(stop_dt):
        exit_px = stop_px
        exit_dt = stop_dt
        exit_reason = 'stopped'
        return exit_px, exit_dt, exit_reason

    return eod_px, eod_dt, 'eod close'

def append_ticker_pnl(dt, rt, pnl):
    current_pnl = pnl[-1][1] + rt
    pnl.append((dt, rt))

def get_daily_record(ticker, dt, close, portfolio_value, in_record):
    record = {
        'symbol': ticker,
        'date': dt,
        'close': close,
        'portfolio_value': portfolio_value,
        'in_trade': in_record,
    }
    return record


if __name__ == '__main__':

    tickers = ["SPY"] #, ["SPY", "QQQ", "GLD", "NVDA", "IWM", "SLV"]
    start = "2022-01-01"
    end = "2026-04-30"
    target_delta = 0.30
    iv_ratio_threshold = 1.2
    risk_per_trade = 0.05
    cut_off_time = datetime.time(10, 30)
    orb_minutes = 5
    output_folder = Path(rf"D:\test_data\day_trading\orb_buy_options\SPY")
    stretch_lookback = 10
    orb_ranges_ma_lookback = 20
    trade_id = 0
    equity = 100_000
    start_date = datetime.datetime.strptime(start, '%Y-%m-%d')
    end_date = datetime.datetime.strptime(end, '%Y-%m-%d')
    run_number = 1

    output_folder.mkdir(parents=True, exist_ok=True)
    intra_stock_folder = Path(r'E:\_data\thetadata\stock_data\data')


    daily_data_folder = Path(r'D:\stock_data\daily')
    dfs = {}
    df_ivs = {}
    df_intras = {}
    for ticker in tickers:
        print(f'get data for {ticker}')
        intra_fn = intra_stock_folder.joinpath(f'{ticker}.parquet')
        df_intra = pd.read_parquet(intra_fn, engine='pyarrow')
        df_intra = df_intra[(df_intra['quote_datetime'] >= start_date) & (df_intra['quote_datetime'] <= end_date)]
        df_intra.set_index('quote_datetime', inplace=True)
        df_intra.sort_index(inplace=True)
        df_intras[ticker] = df_intra

        daily_fn = daily_data_folder.joinpath(f'{ticker}.parquet')
        df_daily = pd.read_parquet(daily_fn)
        df_daily.set_index('quote_datetime', inplace=True)
        df_daily.sort_index(inplace=True)
        df_daily = df_daily[~df_daily.index.duplicated(keep='first')]

        df_daily['range'] = df_daily['high'] - df_daily['low']
        df_daily['hi-open'] = df_daily['high'] - df_daily['open']
        df_daily['open-lo'] = df_daily['open'] - df_daily['low']
        df_daily['closest_extreme'] = df_daily.apply(lambda x: min(x['hi-open'], x['open-lo']), axis=1)
        #df_daily['stretch'] = df_daily['closest_extreme'].rolling(stretch_lookback, min_periods=stretch_lookback).mean()
        df_daily['up_stretch'] = (df_daily['high'] - df_daily['open']).rolling(stretch_lookback, min_periods=stretch_lookback).mean()
        df_daily['dn_stretch'] = (df_daily['open'] - df_daily['low']).rolling(stretch_lookback, min_periods=stretch_lookback).mean()
        df_daily['stretch'] = (abs((df_daily['up_stretch'] - df_daily['dn_stretch'])) / 2)
        df_daily['atr'] = talib.ATR(df_daily['high'].to_numpy(float), df_daily['low'].to_numpy(float), df_daily['close'].to_numpy(float), timeperiod=14)
        #df_daily.reset_index(drop=False, inplace=True)
        dfs[ticker] = df_daily = df_daily

        iv_fn = Path(rf'D:\options_data\daily\{ticker}\{ticker}_iv.parquet')
        df_iv = pd.read_parquet(iv_fn, engine='pyarrow')
        df_iv.set_index('quote_datetime', inplace=True)
        df_iv.sort_index(inplace=True)

        df_ivs[ticker] = df_iv

    open_time = datetime.time(9, 30)
    orb_time = datetime.time(open_time.hour, open_time.minute + orb_minutes)
    open_trade_end_time = datetime.time(int(cut_off_time.hour), int(cut_off_time.minute))
    close_time = datetime.time(15, 45)

    dts = options_framework.utils.helpers.get_market_dates(start_date, end_date)

    portfolio = OptionPortfolio(cash=equity, start_date=start_date, end_date=end_date, check_margin_on_open=False)
    portfolio.bind(position_expired=on_expired)

    orb_ranges = deque()
    daily_records = []
    pnls = defaultdict(list)
    rt = defaultdict(lambda: 100_000)
    daily_records_t = defaultdict(list)
    for dt in dts:

        in_trade = False
        for ticker in tickers:
            print(ticker, dt, portfolio.current_value)
            df_daily = dfs[ticker]
            df_iv = df_ivs[ticker]
            df_intra = df_intras[ticker]
            if not dt in df_daily.index:
                pnls[ticker].append(rt[ticker])
                rec = {"date": dt, "close": np.nan, "portfolio_value": rt[ticker], "in_trade": False}
                daily_records_t[ticker].append(rec)
                continue
            i = df_daily.index.get_loc(dt)

            yesterday_ = df_daily.iloc[i - 1]
            if dt in df_iv.index:
                iv_ = df_iv.loc[dt]
            df_dt = df_intra.loc[df_intra.index.normalize() == dt]
            if df_dt.empty:
                print(f'no intraday data for {dt}')
                pnls[ticker].append(rt[ticker])
                rec = {"date": dt, "close": df_daily.iloc[i]['close'], "portfolio_value": rt[ticker], "in_trade": False}
                daily_records_t[ticker].append(rec)

                continue

            # get orb values
            open_dt = pd.Timestamp(f"{dt.date()} {open_time}")
            orb_dt = pd.Timestamp(f"{dt.date()} {orb_time}")
            open_trade_end_dt = pd.Timestamp(f"{dt.date()} {open_trade_end_time}")
            eod_dt = df_dt.iloc[-15].name
            if orb_dt not in df_dt.index:
                orb_dt = df_dt.iloc[5].name

            orb_window = df_dt.loc[open_dt: open_dt + pd.Timedelta(minutes=orb_minutes) - pd.Timedelta(minutes=1)]
            o1 = float(orb_window["open"].iloc[0])
            c1 = float(orb_window["close"].iloc[-1])
            h1 = float(orb_window["high"].max())
            l1 = float(orb_window["low"].min())
            orb_range = h1 - l1
            orb_ranges.append(orb_range)

            # orb_ranges.append(orb_range)
            if len(orb_ranges) < orb_ranges_ma_lookback:
                print('warmup for orb range')
                pnls[ticker].append(rt[ticker])
                rec = {"date": dt, "close": df_daily.iloc[i]['close'], "portfolio_value": rt[ticker], "in_trade": False}
                daily_records_t[ticker].append(rec)
                continue
            elif len(orb_ranges) == orb_ranges_ma_lookback:
                range_ma = sum(orb_ranges) / orb_ranges_ma_lookback
                orb_ranges.popleft()

            # find out if today is a 0DTE day
            portfolio.next(open_dt, ticker)
            # find the expiration for today. If not an expiration day, skip
            option_chain = portfolio.option_chains[ticker]
            expirations = option_chain.expirations

            try:
                exp = next(x for x in expirations if x == dt.date())
            except StopIteration:
                pnls[ticker].append(rt[ticker])
                rec = {"date": dt, "close": df_daily.iloc[i]['close'], "portfolio_value": rt[ticker], "in_trade": False}
                daily_records_t[ticker].append(rec)
                continue

            stretch = yesterday_['stretch']

            skip = orb_range > range_ma
            #print(f'{dt} orb range: {orb_range:.2f} range_ma {range_ma:.2f} stretch {stretch:.2f} skip: {skip}')
            if skip:
                pnls[ticker].append(rt[ticker])
                rec = {"date": dt, "close": df_daily.iloc[i]['close'], "portfolio_value": rt[ticker], "in_trade": False}
                daily_records_t[ticker].append(rec)
                continue

            long_entry_px = h1 + stretch
            short_entry_px = l1 - stretch

            open_trade_window = df_dt.loc[orb_dt:open_trade_end_dt]
            long_entry_scan = open_trade_window['high'] >= long_entry_px
            long_entry_dt = first_true_ts(long_entry_scan)
            short_entry_scan = open_trade_window['low'] <= short_entry_px
            short_entry_dt = first_true_ts(short_entry_scan)

            # determine if long or short or no trade today
            # get entry, profit,and stop prices
            entry_px, entry_dt, stop_px, target_px, direction = get_entry(long_entry_dt, short_entry_dt, long_entry_px,
                                                                          short_entry_px, stretch)
            if entry_px is None:
                pnls[ticker].append(rt[ticker])
                rec = {"date": dt, "close": df_daily.iloc[i]['close'], "portfolio_value": rt[ticker], "in_trade": False}
                daily_records_t[ticker].append(rec)
                continue

            trade_close_window = df_dt[entry_dt + pd.Timedelta(minutes=1):eod_dt]
            if direction == 'long':
                profit_scan = trade_close_window['high'] >= target_px
                stop_scan = trade_close_window['low'] <= stop_px

            elif direction == 'short':
                profit_scan = trade_close_window['low'] <= target_px
                stop_scan = trade_close_window['high'] >= stop_px
            profit_dt = first_true_ts(profit_scan)
            stop_dt = first_true_ts(stop_scan)

            eod_px = df_dt.loc[eod_dt]['close']
            exit_px, exit_dt, exit_reason = get_exit(profit_dt, stop_dt, eod_dt, target_px, stop_px, eod_px)

            # Now that we have all the trade times, trade the options
            portfolio.next(entry_dt.to_pydatetime(), ticker)

            option_type = 'call' if direction == 'long' else 'put'
            options = [x for x in option_chain.options if x['option_type'] == option_type and x['expiration'] == exp]

            # find option with the closest delta to the target
            deltas = [x['delta'] for x in options]
            target = target_delta if option_type == 'call' else -target_delta
            delta = min(deltas, key=lambda x: abs(x - target))
            option_data = next(x for x in options if x['delta'] == delta)
            strike = option_data['strike']
            iv_today = iv_.iloc[0]['atm_iv']
            dte = min(iv_['dte'].tolist(), key=lambda x: abs(x - 30)) # find closest to 30 dte expiration
            iv_30 = iv_.loc[iv_['dte'] == dte].squeeze()['atm_iv']
            iv_ratio = iv_today / iv_30
            option = Single.create(option_chain=option_chain, expiration=exp, strike=strike, option_type=option_type,
                                   stretch=stretch,orb_range=orb_range, buy_delta=option_data['delta'])

            quantity = int(np.floor((portfolio.current_value * risk_per_trade) / (option.price * 100)))

            # if option.price >= 8:
            #     daily_records.append({
            #         'date': dt,
            #         'close': df_daily.iloc[i]['close'],
            #         'portfolio_value': portfolio.current_value,
            #         'in_trade': False,
            #     })
            #     continue

            portfolio.open_position(option, quantity=quantity, iv_ratio=iv_ratio)
            print(f'{ticker} opening option {option.instance_id} for {option.get_trade_premium()}')
            # retrieve option chain for closing time
            dt = exit_dt.to_pydatetime()
            portfolio.next(quote_datetime=dt)
            portfolio.close_position(option, exit_reason=exit_reason)
            print(f'{ticker} close option {option.instance_id} pnl: {option.get_profit_loss()}')
            pnl = option.get_profit_loss()
            rt[ticker] += pnl
            in_trade = True

            pnls[ticker].append(rt[ticker])
            rec = {"date": dt, "close": df_daily.iloc[i]['close'], "portfolio_value": rt[ticker], "in_trade": True}
            daily_records_t[ticker].append(rec)

        daily_records.append({"date": dt, "close": np.nan, "portfolio_value": portfolio.current_value, "in_trade": in_trade})


    closed_positions = portfolio.closed_positions.copy()

    trades = [{
            'id': x.instance_id,
            'symbol': x.symbol,
            'expiration': x.expiration,
            'strike': x.strike,
            'option_type': x.option_type,
            'entry_dt': x.get_open_datetime(),
            'exit_dt': x.get_close_datetime(),
            'open_premium': x.get_trade_premium(),
            'open_spot_price': x.option.trade_open_info.spot_price,
            'close_spot_price': x.spot_price,
            'entry_px': x.get_trade_price(),
            'exit_px': x.get_closed_price(),
            'pnl': x.get_profit_loss(),
            'pnl_pct': x.get_profit_loss_percent(),
            'qty': x.option.trade_open_info.quantity,
            'fees': x.get_fees(),
            'exit_reason': x.user_defined['exit_reason'],
            'iv_ratio': x.user_defined['iv_ratio'],
            'holding_period': int(np.floor((x.get_close_datetime() - x.get_open_datetime()).total_seconds()/60)),
            'stretch': x.user_defined['stretch'],
            'orb_range': x.user_defined['orb_range']
            }
            for x in portfolio.closed_positions]

    df_trades = pd.DataFrame(trades)
    df_daily = pd.DataFrame(daily_records)
    df_daily.set_index('date', inplace=True)

    for ticker in tickers:
        fn = output_folder.joinpath(f'{ticker}_trades_{run_number}.csv')

        print(f'ending equity: {rt[ticker] + 100_000:.2f}')

        daily_fn = output_folder.joinpath(f'{ticker}_daily_{run_number}.csv')
        df_trades_t = df_trades[df_trades['symbol'] == ticker]
        df_daily_t = pd.DataFrame(daily_records_t[ticker])
        df_daily_t.set_index('date', inplace=True)

        stats = trade_stats(df_trades_t)
        print(stats)
        print(ticker)
        portfolio_stats, trades_stats = print_report(ticker, df_trades_t, df_daily_t,
                                                        f"{ticker} 5-min ORB Options Strategy", frequency='daily')

        df_trades_t.to_csv(fn, index=False)
        df_daily_t.to_csv(daily_fn, index=True)
        stats.to_csv(output_folder.joinpath(f'{ticker}trades_stats_{run_number}.csv'), index=True)
        portfolio_stats.to_csv(output_folder.joinpath(f'{ticker}_portfolio_stats_{run_number}.csv'), index=True)

        plt.figure(figsize=(12, 6))
        plt.plot(dts, pnls[ticker])
        plt.title(f'{ticker} ORB Equity Curve')
        plt.xlabel('Trade date')
        plt.ylabel('Cumulative pnl $')
        plt.axhline(y=0, color='gray', linestyle='--')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        pass

    # all tickers together
    ticker = 'ALL'
    fn = output_folder.joinpath(f'all_trades_{run_number}.csv')

    print(f'ending equity: {portfolio.current_value:.2f}')

    daily_fn = output_folder.joinpath(f'daily_{run_number}.csv')

    portfolio_stats, trades_stats = print_report(ticker, df_trades, df_daily,
                                                f"{ticker} 5-min ORB Options Strategy", frequency='daily')

    dts = dts[:len(df_daily)]
    daily_pnls = df_daily['portfolio_value'].tolist()

    plt.figure(figsize=(12, 6))
    plt.plot(dts, daily_pnls)
    plt.title('All Tickers ORB Equity Curve')
    plt.xlabel('Trade date')
    plt.ylabel('Cumulative pnl $')
    plt.axhline(y=0, color='gray', linestyle='--')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()

    df_trades.to_csv(fn, index=False)
    df_daily.to_csv(daily_fn, index=True)
    stats.to_csv(output_folder.joinpath(f'{ticker}_trades_stats_{run_number}.csv'), index=True)
    portfolio_stats.to_csv(output_folder.joinpath(f'{ticker}_portfolio_stats_{run_number}.csv'), index=True)























