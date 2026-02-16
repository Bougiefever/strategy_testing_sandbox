import sys
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
import datetime
import talib
import math
from utility import *
from glob import glob

# settings
open_time = datetime.time(9, 30)
close_time = datetime.time(15, 59)
last_entry = datetime.time(15,30)
position_risk = 0.01
starting_equity = 100_000
equity = starting_equity

# get the earnings data
earn_data_fn = Path(r'D:\stock_data\earnings_data.csv')
stock_data_folder = Path(r'D:\stock_data\intraday')
daily_stock_folder = Path(r'D:\stock_data\daily_stock_prices')
intra_calcs_folder = Path(r'D:\stock_data\intraday\calcs')
df_earn = pd.read_csv(earn_data_fn, index_col='Earnings_Date', parse_dates=True)
df_earn.sort_values(by=['Earnings_Date', 'Symbol'], inplace=True)
start_date = pd.to_datetime(datetime.datetime(2021, 5, 11))
end_date = pd.to_datetime(datetime.datetime(2024, 12, 1))
df_earn = df_earn[start_date:end_date]

# get stock market open days from SPY daily
spy_daily_fn = Path(r'D:\stock_data\daily_stock_prices\SPY_.parquet')
_spy = pd.read_parquet(spy_daily_fn, engine="pyarrow")
_spy.set_index('quote_datetime', inplace=True)
_spy.sort_index(inplace=True)
dts = _spy.loc[start_date:].index.values.tolist()

# get all the stock data
symbols = df_earn['Symbol'].unique()
symbols.sort()

symbols=  ['AFRM',	'ALGN',	'APP',	'ARLO',	'ARRY',	'AXON',	'AYX',	'BBWI',	'BILL',	'BIRD',	'CFLT',	'CHPT',	'COIN',	'CPNG',	'CRUS',	'CTVA',	'CVNA',	'DDOG',	'DECK',	'DELL',	'DIS',	'DKNG',	'ESTC',	'EXPE',	'FLS',	'FSLR',	'GRPN',	'GTLB',	'HNST',	'HOOD',	'IFF',	'INTC',	'INTU',	'IOT',	'LC',	'LCID',	'LUMN',	'LYFT',	'LYV',	'MDB',	'MU',	'NKE',	'NTNX',	'NTR',	'NWSA',	'OKTA',	'OPRA',	'PATH',	'PINS',	'PLUG',	'PODD',	'PSTG',	'PVH',	'RDDT',	'RGR',	'RKT',	'ROKU',	'RUN',	'S',	'SDIG',	'SEDG',	'SIVB',	'SMCI',	'SNAP',	'SNOW',	'SONO',	'STNE',	'SWBI',	'TOST',	'TWLO',	'UPST',	'UPWK',	'VFC',	'WOLF',	'YELP',	'ZEUS',	'ZG',	'ZS',	'ZUO',	'TRUE',]
df_earn = df_earn[df_earn['Symbol'].isin(symbols)]

df = df_earn.copy()

c1 = df["ROC_100D_SMA"].notna() & df["Earnings_Gap_Pct"].notna() & df["Earnings_Surprise_Pct"].notna()
print("has core fields:", c1.sum())

c2 = c1 & (df["ROC_100D_SMA"] > -10)
print("roc > -10:", c2.sum())

c3 = c2 & (df["Earnings_Gap_Pct"] > 10)
print("gap > 10:", c3.sum())

rev_ok = df["Revenue_Surprise_Pct"].notna() & (df["Revenue_Surprise_Pct"] > 20)
eps_ok = df["Earnings_Surprise_Pct"] > 100
eps_rev_ok = (df["Earnings_Surprise_Pct"] > 50) & (df["Revenue_Surprise_Pct"] > 5)

c4 = c3 & (eps_ok | rev_ok | eps_rev_ok)
print("surprise logic:", c4.sum())

# find the stock data file for each ticker
mkt_files = glob(str(stock_data_folder.joinpath('market', '**', '*.parquet')), recursive=True)
stk_files = glob(str(stock_data_folder.joinpath('stocks', '**', '*.parquet')), recursive=True)
stock_files = stk_files + mkt_files
stock_files = [Path(x) for x in stock_files]
#calc_files = calcs_folder.glob('*.parquet')
pass

end_date = end_date + pd.Timedelta(days=31)
dfs = defaultdict(pd.DataFrame)
for symbol in symbols:

    try:
        fn = next(x for x in stock_files if x.stem == symbol)
    except StopIteration:
        continue
    #print(symbol)
    intra_calc_fn = intra_calcs_folder.joinpath(f'{symbol}.parquet')
    daily_fn = daily_stock_folder.joinpath(f'{symbol}_.parquet')
    if not intra_calc_fn.exists() or not daily_fn.exists():
        continue

    # intra day prices
    df = pd.read_parquet(fn, engine="pyarrow")
    df.set_index('quote_datetime', inplace=True)
    df.sort_index(inplace=True)
    df = df[(df.index >= start_date) & (df.index <= end_date)]

    # intra day calcs
    df_calc_intra = pd.read_parquet(intra_calc_fn, columns=['quote_datetime', 'vol_5', 'rvol_5'], engine="pyarrow")
    df_calc_intra = df_calc_intra[df_calc_intra['quote_datetime'] >= start_date]

    # daily prices
    df_daily = pd.read_parquet(daily_fn, columns=['quote_datetime', 'open', 'high', 'low', 'close', 'volume'], engine="pyarrow")
    df_daily['ema10'] = talib.EMA(df_daily['close'].to_numpy(float), timeperiod=10)
    df_daily['ema20'] = talib.EMA(df_daily['close'].to_numpy(float), timeperiod=20)
    df_daily['adv20'] = talib.SMA(df_daily['volume'].to_numpy(float), timeperiod=20)
    df_daily['atr'] = talib.ATR(df_daily['high'].to_numpy(float), df_daily['low'].to_numpy(float), df_daily['close'].to_numpy(float), timeperiod=14)

    # move back one day so we only have info that is available at the beginning of the day
    df_daily['ema10'] = df_daily['ema10'].shift(1)
    df_daily['ema20'] = df_daily['ema20'].shift(1)
    df_daily['adv20'] = df_daily['adv20'].shift(1)
    df_daily['atr'] = df_daily['atr'].shift(1)

    # get previous closes to calculate consecutive red days
    df_daily['close_2'] = df_daily['close'].shift(2)
    df_daily['close_1'] = df_daily['close'].shift(1)

    df_daily = df_daily[['quote_datetime', 'ema10', 'ema20', 'adv20', 'atr', 'close_1','close_2']]

    df_daily = df_daily.merge(df_calc_intra, on=['quote_datetime'], how='inner')
    df_daily.set_index('quote_datetime', inplace=True)
    df_daily.sort_index(inplace=True)
    df_daily = df_daily.loc[start_date:end_date]
    df_mrg = pd.merge_asof(df, df_daily, left_index=True, right_index=True, direction="backward")
    dfs[symbol] = df_mrg

def close_trade(trade, direction, shares, exit_dt, px, exit_reason):
    trade['remaining_shares'] = trade['remaining_shares'] - shares
    entry_px = trade['entry_px']
    if direction == "long":
        pnl = (px - entry_px) * shares
    else:
        pnl = (entry_px - px) * shares
    trade['gross_pnl'] += pnl
    trade['net_pnl'] = trade['gross_pnl']
    trade['exit_dt'] = exit_dt
    trade['exit_px'] = px
    trade['exit_reason'] = exit_reason
    return trade

def get_stop_price(direction, current_stop_px, proposed_stop_px) -> float:
    if direction == "long":
        stop_px = proposed_stop_px if proposed_stop_px > current_stop_px else current_stop_px
    else:
        stop_px = proposed_stop_px if proposed_stop_px < current_stop_px else current_stop_px

    return stop_px

def check_stop(df_dt, direction, stop_px):
    stop_dt = None
    if direction == "long":
        stop_pass = df_dt['low'] <= stop_px
        stop_dt = first_true_ts(stop_pass)
    if direction == "short":
        stop_pass = df_dt['high'] >= stop_px
        stop_dt = first_true_ts(stop_pass)
    stop_dt = None if pd.isna(stop_dt) else stop_dt
    return stop_dt

def check_exit_trade(dt, trade):
    symbol = trade['symbol']
    trade_dt = trade['date']
    stop_px = trade['stop_px']
    if dt <= trade_dt:
        return trade
    df = dfs[symbol]
    df_dt = df[df.index.normalize() == dt]
    direction = trade['direction']

    ema_20_px = df_dt.iloc[0]['ema20']
    stop_px = get_stop_price(direction, stop_px, ema_20_px) # always check
    if stop_px == ema_20_px:
        trade["stop_type"] = "20 ema"

    if not trade['exit_10_ema']: # we have not already exited half because of breaching 10-ema, so check
        ema_10_px = df_dt.iloc[0]['ema10']
        stop_px = get_stop_price(direction, stop_px, ema_10_px)
        if stop_px == ema_10_px:
            trade["stop_type"] = "10 ema"

    trade['stop_px'] = stop_px

    stop_dt = check_stop(df_dt, direction, stop_px)
    check_dt = pd.to_datetime(f"{dt.date()} {last_entry}")
    if stop_dt is None:
        if check_dt in df_dt.index:

            today = df_dt.loc[check_dt, 'close']
            entry_px = trade['entry_px']

            # check for 2% of risk
            target_equity_risk = equity * 0.02
            current_risk = abs(today - stop_px) * trade['remaining_shares']
            if current_risk > target_equity_risk:
                current_per_share_risk = abs(today - stop_px)
                target_per_share_risk = target_equity_risk / trade['remaining_shares']
                target_stop_px = today - target_per_share_risk
                trade['stop_px'] = target_stop_px
                trade['stop_type'] = "2%"

            # check for 2 red days
            # close 1/3
            # move stop to be
            # only one time
            if not trade['early_exit_done']:
                close_2 = df_dt.loc[check_dt,'close_2']
                close_1 = df_dt.loc[check_dt,'close_1']
                if direction == "long":
                    if close_2 > close_1 > today:
                        stop_px = entry_px if entry_px > stop_px else stop_px
                        trade['early_exit_done'] = True

                elif direction == "short":
                    if close_2 < close_1 < today:
                        stop_px = entry_px if entry_px < stop_px else stop_px
                        trade['early_exit_done'] = True

                if trade['early_exit_done']:
                    shares = math.ceil(trade['remaining_shares'] * 0.3)
                    trade['stop_px'] = stop_px
                    trade = close_trade(trade, direction, shares, check_dt, today, "red_day")
    else:
        stop_type = trade['stop_type']
        if stop_type == "10 ema":
            exit_reason = "10ema"
            shares = math.ceil(trade["remaining_shares"] * 0.50)
            trade["stop_px"] = ema_20_px # move next stop to 20-ema - that is our new stop after closing 1/2
            trade["exit_10_ema"] = True
        elif stop_type == "20 ema":
            exit_reason = "20ema"
            shares = trade["remaining_shares"]
        else:
            exit_reason = stop_type
            shares = trade["remaining_shares"]
        trade = close_trade(trade, direction, shares, stop_dt, stop_px, exit_reason)

    return trade

def position_sizing(entry_px: float, exit_px: float) -> int:
    dollar_risk = equity * position_risk
    risk_per_share = abs(entry_px - stop_px)
    shares = max(0, int(np.floor(dollar_risk / risk_per_share)))
    return shares

def orb_trade(trade_dt, df_dt, first_candle_minutes,):
    open_dt = pd.Timestamp(f"{trade_dt.date()} {open_time}")
    last_entry_dt = pd.Timestamp(f"{trade_dt.date()} {last_entry}")
    orb_dt = open_dt + pd.Timedelta(minutes=first_candle_minutes)

    first_window = df_dt.loc[open_dt: open_dt + pd.Timedelta(minutes=first_candle_minutes) - pd.Timedelta(minutes=1)]
    o1 = first_window['open'].iloc[0]
    c1 = first_window['close'].iloc[-1]
    h1 = first_window['high'].max()
    l1 = first_window['low'].min()

    scan_window = df_dt[orb_dt:last_entry_dt]
    if direction == "long":
        entry_px = h1 * 1.0025
        stop_px = l1
        valid_entries = scan_window['high'] >= entry_px
        entry_dt = first_true_ts(valid_entries)
        if pd.isna(entry_dt):
            return None
        scan_window = df_dt[entry_dt:last_entry_dt]
        valid_entries = scan_window['low'] <= stop_px
        stop_dt = first_true_ts(valid_entries)

    elif direction == "short":
        entry_px = l1 * 1.0025
        stop_px = h1
        valid_entries = scan_window['low'] <= entry_px
        entry_dt = first_true_ts(valid_entries)
        if pd.isna(entry_dt):
            return None

        scan_window = df_dt[entry_dt:last_entry_dt]
        valid_entries = scan_window['high'] >= stop_px
        stop_dt = first_true_ts(valid_entries)
    return entry_dt, entry_px, stop_px, stop_dt

trades = []
daily_balance = []
active_trades = []
daily_risk = []

for dt in dts:
    # check on active trades
    check_trades = active_trades.copy()
    for trade in check_trades:
        trade = check_exit_trade(dt, trade)
        if trade['remaining_shares'] == 0:
            active_trades.remove(trade)
            equity += trade['net_pnl']
            trade['equity_after'] = equity
            trades.append(trade)

    #caculate mark-to-market for active trades
    today_unrealized = 0
    today_risk = 0
    for trade in active_trades:
        if dt <= trade['date']:
            continue
        current_pnl = trade['net_pnl']
        ticker = trade['symbol']
        df = dfs.get(ticker)
        if df is None:
            continue
        px = df.loc[df.index.normalize() == dt].iloc[0]['close_1'] # yesterday close
        direction = trade['direction']
        entry_px = trade['entry_px']
        shares = trade['remaining_shares']
        unrealized_per_share = (px - entry_px) if direction == "long" else (entry_px - px)
        unrealized = unrealized_per_share * shares + current_pnl
        today_unrealized += unrealized
        risk_per_share = (px - trade['stop_px']) if direction == "long" else (trade['stop_px'] - px)
        risk = risk_per_share * shares
        today_risk += abs(risk)

    daily_balance.append([dt, today_unrealized + equity])
    daily_risk.append([dt, today_risk])


    dt_earn = df_earn.loc[dt:dt]
    for row in dt_earn.itertuples():
        ticker = row.Symbol
        when = row.BMO_AMC
        trade_dt = pd.to_datetime(row.trade_date)
        if pd.isna(trade_dt):
            #print(f'{dt}, {ticker} ***********************************************************  no trade date')
            continue
        #print(dt, ticker, equity)

        df = dfs.get(ticker)
        if df is None:
            continue
        if not trade_dt in df.index.normalize():
            continue
        df_dt = df[df.index.normalize() == trade_dt]
        adv = df_dt.iloc[0]['adv20']
        vol5 = df_dt.iloc[0]['vol_5']
        rvol = df_dt.iloc[0]['rvol_5']

        roc_ma = row.ROC_100D_SMA
        gap = row.Earnings_Gap_Pct
        earn_surprise = row.Earnings_Surprise_Pct
        rev_surprise = row.Revenue_Surprise_Pct

        long_ok = (roc_ma >= -10) & (gap >= 10)
        if long_ok:
            if earn_surprise >= 100 or rev_surprise >= 20:
                long_ok = True
            elif earn_surprise >= 50 and rev_surprise >= 5:
                long_ok = True
            else:
                long_ok = False

        short_ok = (roc_ma <= 0) & (gap <= -5) & (earn_surprise <= -20) & (rev_surprise <= -5)

        if long_ok or short_ok:
            direction = "short" if short_ok else "long"
            print(trade_dt, ticker, direction)
            trade = None
            for k in [5]: #, 60]:
                open_dt = pd.Timestamp(f"{trade_dt.date()} {open_time}")
                orb_dt = open_dt + pd.Timedelta(minutes=k)
                if trade is not None: # first trade was stopped out
                    exit_dt = trade['exit_dt']
                    if exit_dt >= orb_dt: # try again with 1 hour orb
                        continue

                trade_info = orb_trade(trade_dt, df_dt, first_candle_minutes=k)
                if trade_info is None:
                    continue

                entry_dt, entry_px, stop_px, stop_dt = trade_info
                shares = position_sizing(entry_px, stop_px)

                if pd.isna(stop_dt):
                    # not stopped out on entry day
                    trade = {
                        "symbol": ticker,
                        "date": trade_dt,
                        "direction": direction,
                        "entry_dt": entry_dt,
                        "entry_px": entry_px,
                        "stop_px": stop_px,
                        "exit_dt": pd.NaT,
                        "exit_px": pd.NaT,
                        "shares": shares,
                        "gross_pnl": 0,
                        "net_pnl": 0,
                        "fees": 0.0,
                        "exit_reason": "stop",
                        "equity_after": pd.NaT,
                        "remaining_shares": shares,
                        "stop_type": "initial stop",
                        "exit_10_ema": False,
                        "early_exit_done": False,
                    }
                    active_trades.append(trade)
                    break

                # stopped out today
                exit_reason = f'stopout {k}'
                if direction == "long":
                    pnl = (stop_px - entry_px) * shares
                else:
                    pnl = (entry_px - stop_px) * shares

                equity = equity + pnl

                trade = {
                    "symbol": ticker,
                    "date": trade_dt,
                    "direction": direction,
                    "entry_dt": entry_dt,
                    "entry_px": entry_px,
                    "stop_px": stop_px,
                    "exit_dt": stop_dt,
                    "exit_px": stop_px,
                    "shares": shares,
                    "gross_pnl": pnl,
                    "net_pnl": pnl,
                    "fees": 0.0,
                    "exit_reason": exit_reason,
                    "equity_after": equity,
                }
                trades.append(trade)


trades_df = pd.DataFrame(trades)
stats = trade_stats(trades_df)
print(stats)

# dates = [x[0] for x in daily_balance]
# nlv = pd.Series([x[1] for x in daily_balance], index=dates, name='nlv')
# cash = pd.Series([x[1] for x in daily_cash], index=dates, name='cash')
# margin = pd.Series([x[1] for x in daily_risk], index=dates, name='margin')
#
# trade_stats = portfolio_stats_options(nlv, trades_df, cash, margin)
# print(trade_stats)

trades_df.to_csv(r'D:\test_data\earnings\trades_intra_6.csv')
