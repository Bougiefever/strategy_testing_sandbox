from __future__ import annotations

import datetime
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.vertical import Vertical
from options_framework.config import settings
import pandas as pd
import talib
import numpy as np
from pathlib import Path

def trade_stats(trades: pd.DataFrame) -> dict:
    # Summary stats
    if trades_df.empty:
        stats = {"n_trades": 0}
        return trades_df, stats

    r = trades_df["return"].to_numpy(float)
    wins = r[r > 0]
    losses = r[r < 0]

    gross_profit = wins.sum() if wins.size else 0.0
    gross_loss = -losses.sum() if losses.size else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.inf

    stats = {
        "n_trades": int(len(trades_df)),
        "win_rate": float((r > 0).mean()),
        "avg_return": float(r.mean()),
        "median_return": float(np.median(r)),
        "profit_factor": float(profit_factor),
        "avg_hold_days": float(trades_df["hold_days"].mean()),
        "median_hold_days": float(trades_df["hold_days"].median()),
        "best_trade": float(r.max()),
        "worst_trade": float(r.min()),
    }

    return stats

stock_folder = Path(r'D:\stock_data\daily_stock_prices')
stock_calcs_folder = Path(r'D:\stock_data\calcs')

stock_files = list(stock_folder.glob('*.parquet'))
stock_calc_files = list(stock_calcs_folder.glob('*.parquet'))

min_close = 5
vol_ma_min = 1_000_000
max_days_since_high = 20
crsi_open = 15
limit_pct_lower = 0.05
ot = 'put'
short_delta_target = 0.25
long_delta_target = 0.10
dte_target = 21
lo_dte_target = 7
hi_dte_target = 30
pnl_profit_target = 0.50
pnl_loss_limit = -2.0

# only one of these can be used
hold_dte = 10
close_dte = 4

def on_expired(expired_position):
    print(f'expired: {expired_position} {expired_position.get_profit_loss():.2f}')
    pass

def on_closed(close_position):
    pass

trades = []

for stock_file in stock_files:
    ticker = stock_file.stem[:-1]
    stock_fn = stock_folder.joinpath(f'{ticker}_.parquet')
    calc_fn = stock_calcs_folder.joinpath(f'{ticker}_calcs.parquet')
    if not calc_fn.exists():
        continue

    stock_fn = stock_folder.joinpath(f'{ticker}_.parquet')
    calc_fn = stock_calcs_folder.joinpath(f'{ticker}_calcs.parquet')

    print(ticker)

    df = pd.read_parquet(stock_fn, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume', 'close_orig'], engine='pyarrow')
    df_calc = pd.read_parquet(calc_fn, columns=['symbol', 'quote_datetime','days_since_hi', 'crsi'],  engine='pyarrow')

    df = df.merge(df_calc, how='inner', on=['symbol','quote_datetime'])
    df.set_index('quote_datetime', inplace=True)
    df.sort_index(inplace=True)

    df['vol_ma'] = talib.SMA(df['volume'].to_numpy(float), timeperiod=21)

    df['cond_true'] = (df["close_orig"] >= min_close) & \
            (df["vol_ma"] >= vol_ma_min) & \
            (df["days_since_hi"] <= max_days_since_high) & \
            (df["crsi"] < crsi_open)
    df['cond_true'] = df['cond_true'].fillna(False)
    df['cond_true_shift'] = df['cond_true'].shift(1, fill_value=False)
    df['limit_px'] = df['close'].shift(1) * (1.0 - limit_pct_lower)
    df['price_pass'] = df['low'] <= df['limit_px']
    df['signal'] = (df['cond_true_shift'] & df['price_pass'])

    signals = df['signal'].to_numpy(bool)
    if not any(signals):
        continue
    entry_idx = np.flatnonzero(signals)


    start_date = (df.iloc[entry_idx[0]].name).to_pydatetime()
    end_date = (df.iloc[-1].name).to_pydatetime()

    portfolio = OptionPortfolio(cash=100_000, start_date=start_date, end_date=end_date)
    portfolio.bind(position_expired=on_expired)
    portfolio.bind(position_closed=on_closed)

    dt = df.iloc[0].name

    for i in entry_idx:
        df_trade = df.iloc[i:]
        if df_trade.iloc[0].name < dt:
            continue
        for dt, row in df_trade.iterrows():
            dt = row.name.to_pydatetime()
            portfolio.next(dt, ticker)

            if len(portfolio.positions) > 0:
                credit_spread = portfolio.positions[0]
                pnl = credit_spread.get_profit_loss_percent()
                dte = credit_spread.get_dte()
                days_in_trade = credit_spread.get_days_in_trade()
                if days_in_trade >= 5: # pnl >= pnl_profit_target or pnl <= pnl_loss_limit or dte <= close_dte:
                    portfolio.close_position(credit_spread.instance_id)
                    print(credit_spread, credit_spread.get_profit_loss())
                    break
            else:
                option_chain = portfolio.option_chains[ticker]
                expiration_target = dt + datetime.timedelta(days=dte_target)
                if len(option_chain.expirations) == 0:
                    print(ticker, 'no expirations available')
                    break

                expiration = min(option_chain.expirations, key=lambda x: abs((x - expiration_target.date()).days))
                days_diff = (expiration - dt.date()).days
                if days_diff < lo_dte_target or days_diff > hi_dte_target:
                    print(ticker, 'no expiration close enough', days_diff)
                    break

                options = [x for x in option_chain.options.copy() if
                           x['option_type'] == ot and x['expiration'] == expiration]
                if len(options) == 0:
                    print(ticker, 'no options available')
                    break

                deltas = [x['delta'] for x in options]

                short_delta = min(deltas, key=lambda x: abs(x - -(short_delta_target)))
                put_data = next(x for x in options if x['delta'] == short_delta)
                if put_data['bid'] == 0:
                    print(ticker, "bid is zero for short strike")
                    break

                short_strike = put_data['strike']
                long_delta = min(deltas, key=lambda x: abs(x - (long_delta_target)))
                put_data = next(x for x in options if x['delta'] == long_delta)
                long_strike = put_data['strike']

                if short_strike <= long_strike:
                    print(ticker, 'long and short strikes are the same or crossed', short_strike, long_strike)
                    break

                put_credit = Vertical.create(option_chain=option_chain, expiration=expiration, option_type=ot, long_strike=long_strike, short_strike=short_strike)
                if put_credit.price == 0.0:
                    print(ticker, 'price is zero')
                    break

                portfolio.open_position(put_credit, quantity=-1)

    for pos in portfolio.closed_positions:
        trades.append(pos)

trades_index = [f'{o.symbol}_{o.instance_id}' for o in trades]
trades_data = [[o.symbol, o.get_open_datetime(), o.get_close_datetime(), o.get_trade_price(), o.price,(o.get_close_datetime() - o.get_open_datetime()).days, o.get_profit_loss_percent()] for o in trades]
trades_df = pd.DataFrame(data=trades_data, index=trades_index,
                         columns=['symbol','entry_date','exit_date','entry_price','exit_price','hold_days','return'])

output = trade_stats(trades_df)
output_s = pd.Series(output)
print(output_s)