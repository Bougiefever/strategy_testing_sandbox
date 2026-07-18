from datetime import datetime
from pathlib import Path
import talib
from club.yellowbrick.utility import *
from collections import defaultdict
from options_framework import OptionPortfolio, Single, get_market_dates

output_folder = Path(r'D:\test_data\yellowbrick')

stock_data = Path(r'D:\stock_data\daily')
df_signals = pd.read_csv('yb_signals.csv', parse_dates=['trigger_dt', 'pitch_dt'])
df_signals.set_index('trigger_dt', inplace=True)
df_signals.sort_index(inplace=True)

#df_signals = df_signals.iloc[:50]

tickers = df_signals['ticker'].unique().tolist()
tickers.sort()

def on_option_expired(option_position):
    option_position.user_defined['exit_reason'] = 'expired'

dfs = defaultdict(pd.DataFrame)
for ticker in tickers:
    fn = stock_data.joinpath(f'{ticker}.parquet')
    if not fn.exists():
        continue
    df = pd.read_parquet(fn, engine='pyarrow', columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume'])
    df = df.drop_duplicates(subset='quote_datetime', keep='last')
    df.set_index('quote_datetime', inplace=True)

    # Get MACD calcs
    df['macd'], df['sig'], _ = talib.MACD(df['close'].to_numpy())
    df['macd_above_sig'] = df['macd'] > df['sig']
    df['macd_switched'] = df['macd_above_sig'] != df['macd_above_sig'].shift()

    # VWAP calcs
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    price_x_volume = typical_price * df['volume']
    cum_px_x_vol = price_x_volume.cumsum()
    cum_vol = df['volume'].cumsum()
    df['vwap'] = cum_px_x_vol / cum_vol
    df['vwap_rank'] = df['vwap'].rolling(window=252).rank() / 252

    # Calculate 20-day MA of volume
    df['vol_20_ma'] = talib.SMA(df['volume'], timeperiod=20)
    dfs[ticker] = df

starting_cash = 100_000
target_delta = 0.90
target_dte = 180
risk_pct = 0.02
min_stock_price = 10
min_vol_ma = 500_000
start_date = datetime(2024, 1,1)
end_date = datetime(2026,6,30)

portfolio = OptionPortfolio(cash=starting_cash, start_date=start_date, end_date=end_date)
portfolio.bind(position_expired=on_option_expired)

dates = get_market_dates(start_date, end_date)

comp_fn = Path(r'D:\projects\data\ndq_d.csv')
df_comp = pd.read_csv(comp_fn, parse_dates=['date'])
df_comp['volume'] = df_comp['volume'].astype('int64')
df_comp = df_comp[df_comp['date'] >= start_date]
df_comp.set_index('date', inplace=True)
df_comp.sort_index(inplace=True)

df_state = market_state(df_comp)
in_uptrend = False
daily_records = []
for dt in dates:
    print(dt)
    if dt in df_state.index:
      state = df_state.loc[dt]
      in_uptrend = state['in_uptrend']
    #Check open positions to see if we need to close anything
    open_positions = portfolio.positions.copy()
    for position in open_positions:
        exit_reason = ''
        exit_trade = False
        trade_price = position.get_trade_price()
        pnl = position.get_profit_loss()
        pnl_pct = position.get_profit_loss_percent()
        df = dfs[position.symbol]

        # if pnl_pct <= -0.50:
        #     exit_trade = True
        #     exit_reason = '50% loss'

        # if pd.Timestamp(dt) in df.index:
        #     df_dt = df.loc[pd.Timestamp(dt)]
        #     macd_switched = df_dt['macd_switched']
        # else:
        #     macd_switched = False
        # if macd_switched == True:
        #     exit_reason = 'macd switched'
        #     exit_trade = True
        # if position.price >= trade_price * 2:
        #     exit_reason = '2x'
        #     exit_trade = True

        if exit_trade:
            portfolio.close_position(position, exit_reason=exit_reason)


    # Open new positions that have a signal today
    if not dt in df_signals.index:
        continue
    today_signals = df_signals.loc[dt:dt]
    today_tickers = today_signals['ticker'].unique().tolist()
    portfolio.next(quote_datetime=dt, symbols=today_tickers)

    for _, row in today_signals.iterrows():
        ticker = row['ticker']
        sentiment = row['sentiment']
        if in_uptrend and sentiment == 'bearish':
          continue
        elif not in_uptrend and sentiment == 'bullish':
          continue
        print(ticker, sentiment)

        # Get stock data dataframe. If there isn't one, skip
        df = dfs.get(ticker, None)
        if df is None:
            continue

        df_dt = df.loc[pd.Timestamp(dt)]
        open = df_dt['open']
        vol_ma = df_dt['vol_20_ma']
        if open < min_stock_price or vol_ma < min_vol_ma:
            continue
        macd = df_dt['macd']
        macd_sig = df_dt['sig']
        vwap = df_dt['vwap']
        vwap_rank = df_dt['vwap_rank']

        # select only in the bottom 10% ranking of vwap
        # if vwap_rank > 10:
        #     continue

        option_chain = portfolio.option_chains.get(ticker)

        # if there are no options - maybe none for this date, maybe stock has no options, skip it
        if option_chain is None or len(option_chain.expirations) == 0:
            continue

        # Find expiration nearest to the target dte
        expiration = min(option_chain.expirations, key=lambda x: abs((x - dt.date()).days - target_dte))
        option_type = 'call' if sentiment == 'bullish' else 'put'
        options = [x for x in option_chain.options if x['expiration'] == expiration and x['option_type'] == option_type]

        # Find nearest delta option
        deltas = [x['delta'] for x in options]
        t_delta = target_delta if sentiment == 'bullish' else -target_delta
        delta = min(deltas, key=lambda x: abs(x - t_delta))
        option_data = next(x for x in options if x['delta'] == delta)
        strike = option_data['strike']

        try:
            # create option object and open position in the portfolio
            single_option = Single.create(option_chain=option_chain, expiration=expiration, strike=strike, option_type=option_type)
            max_amount = portfolio.current_value * risk_pct
            quantity = max(1,int(np.floor(max_amount / (single_option.price * 100))))
            portfolio.open_position(single_option, quantity=quantity, macd=macd, vwap=vwap, vwap_rank=vwap_rank, vol_ma=vol_ma)
        except Exception as e:
            print(e)

    in_trade = len(portfolio.positions) > 0
    open_positions = len(portfolio.positions)
    daily_records.append({"date": dt, "close": np.nan, "portfolio_value": portfolio.current_value, "in_trade": in_trade,
                          "open_positions": open_positions})

open_positions = portfolio.positions.copy()
for position in open_positions:
    portfolio.close_position(position, exit_reason='end of run')

closed_positions = portfolio.closed_positions.copy()
# for x in closed_positions:
#     history = x.get_price_history()
#     pass

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
            'last_data_px': [x['price'] for x in x.get_price_history()][-1],
            'pnl': x.get_profit_loss(),
            'pnl_pct': x.get_profit_loss_percent(),
            'peak_gain_pct': max([x['pnl_pct'] for x in x.get_price_history()]),
            'max_drawdown_pct': min([x['pnl_pct'] for x in x.get_price_history()]),
            'qty': x.option.trade_open_info.quantity,
            'fees': x.get_fees(),
            'exit_reason': x.user_defined['exit_reason'],
            'holding_period': int(np.floor((x.get_close_datetime() - x.get_open_datetime()).days)),
            'macd': x.user_defined['macd'],
            'vwap': x.user_defined['vwap'],
            'vwap_rank': x.user_defined['vwap_rank'],
            'vol_ma': x.user_defined['vol_ma']
            }
            for x in closed_positions]

run = 4
print(f'{portfolio.current_value:,.2f}')
df_trades = pd.DataFrame(trades)
df_daily = pd.DataFrame(daily_records)
df_daily.set_index('date', inplace=True)

p_stats, t_stats = print_report('YellowBrick', df_trades, df_daily, strategy='YellowBrick MACD entry to Expiration')

df_portfolio_stats = pd.DataFrame(p_stats)
df_trade_stats = pd.DataFrame(t_stats)

df_daily.to_csv(output_folder.joinpath(f'daily_record_{run}.csv'))
df_trades.to_csv(output_folder.joinpath(f'trades_{run}.csv'), index=False)
df_portfolio_stats.to_csv(output_folder.joinpath(f'portfolio_stats_{run}.csv'))
df_trade_stats.to_csv(output_folder.joinpath(f'trade_stats_{run}.csv'))





