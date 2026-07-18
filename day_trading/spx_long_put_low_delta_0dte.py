"""
Option Alpha

SPX Long Put Low Delta Trade

Expiration: 0DTE
Delta: -0.03
Time: 10:30 ET
DOW: Wed/Thu/Fri
Skip: 3x Witching, Monthly Expiration

Many Rules:

1-minute timeframe

VIX >= 20
VIX Change -0.03
Change % > 0
Open Change % >= 0.55 %
SPX intraday ADX(14)  >= 10
SPX intraday CCI(20) <= 160
MACD (12,26,9) in range -25 to 90
Momentum (10) -50 to 247
RSI (14) >= 45
Stoch (14, 3, 3) >= 32
Stoch RSI (14, 14, 3, 3) >= 50
price > 50-day SMA
price > 200-day SMA
"""

import pandas as pd
import numpy as np
from pathlib import Path
import talib
from datetime import datetime, time, timedelta
from options_framework import Single, OptionPortfolio, get_market_dates, get_day_times, is_monthly_expiration, settings, OptionPositionType

from utility import snap

settings['exclude_witching'] = True

# daily SPX prices
daily_stock_dir = Path(r'D:\stock_data\daily\SPX.parquet')
df_daily = pd.read_parquet(daily_stock_dir, engine='pyarrow', columns=['quote_datetime', 'symbol', 'open', 'high', 'low', 'close'])
df_daily = df_daily.drop_duplicates(subset='quote_datetime', keep='last')
df_daily.set_index('quote_datetime', inplace=True)
df_daily.sort_index(inplace=True)

# intraday SPX prices
spx_prices = Path(r'D:\stock_data\intraday\market\indices\SPX.parquet')
df1 = pd.read_parquet(spx_prices, engine='pyarrow', columns=['quote_datetime', 'symbol', 'open', 'high', 'low', 'close'])
spx_prices2 = Path(r'E:\_data\thetadata\index_data\data\SPX.parquet')
df2 = pd.read_parquet(spx_prices2, engine='pyarrow', columns=['quote_datetime', 'symbol', 'open', 'high', 'low', 'close'])
df = pd.concat([df1, df2], ignore_index=True)
df = df.drop_duplicates(subset='quote_datetime', keep='last')
df.set_index('quote_datetime', inplace=True)
df.sort_index(inplace=True)

# Get VIX prices
vix_daily_fn = Path(r'D:\stock_data\daily\VIX.parquet')
df_vix_daily = pd.read_parquet(vix_daily_fn, engine='pyarrow', columns=['quote_datetime', 'symbol', 'open', 'high', 'low', 'close'])
df_vix_daily.set_index('quote_datetime', inplace=True)
df_vix_daily.sort_index(inplace=True)

vix_prices = Path(r'E:\_data\thetadata\index_data\data\VIX.parquet')
df_vix = pd.read_parquet(vix_prices, engine='pyarrow',columns=['quote_datetime', 'symbol', 'open', 'high', 'low', 'close'])
df_vix.set_index('quote_datetime', inplace=True)
df_vix.sort_index(inplace=True)

sg_levels_fn = Path(r'D:\projects\data\SPX_levels_historical.csv')
df_sg = pd.read_csv(sg_levels_fn, parse_dates=['Trade Date', 'Data Release'])
df_sg = df_sg.drop_duplicates(subset='Data Release', keep='last')
df_sg.set_index('Data Release', inplace=True)
df_sg.sort_index(inplace=True)

option_stats_fn = Path(r'D:\options_data\daily\SPX\SPX_optionstats.parquet')
df_stats = pd.read_parquet(option_stats_fn, engine='pyarrow')
df_stats = df_stats.drop_duplicates(subset='quote_datetime', keep='last')
df_stats.set_index('quote_datetime', inplace=True)
df_stats.sort_index(inplace=True)

start_date = datetime(2022, 1, 1)
end_date = datetime(2023, 12, 31)

starting_cash = 100_000
ticker = 'SPXW'
open_trade_time = time(10, 30)

# indicator thresholds
vix_max = 20
vix_chg_max = -0.03
chg_from_close_min = 0
chg_from_open_max = 0.0055
adx_min = 10
cci_max = 160
macd_min = -25
macd_max = 90
mom_min = -50
mom_max = 247
rsi_min = 45
stoch_min = 32
stoch_max = 90
stoch_rsi_min = 50
target_delta = -0.03
max_risk_pct = 0.02


def calculate_stoch_rsi(df, rsi_period=14, stoch_period=14, k_period=3, d_period=3, source='close'):
   # 1. Calculate RSI
   delta = df[source].diff()
   gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
   loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()

   rs = gain / loss
   rsi = 100 - (100 / (1 + rs))

   # 2. Stochastic of RSI
   lowest_rsi = rsi.rolling(window=stoch_period).min()
   highest_rsi = rsi.rolling(window=stoch_period).max()

   stoch_rsi = (rsi - lowest_rsi) / (highest_rsi - lowest_rsi) * 100

   # 3. Smooth %K and %D (TradingView default settings)
   k = stoch_rsi.rolling(window=k_period).mean()
   d = k.rolling(window=d_period).mean()

   return k, d

def on_expired(position):
   position.user_defined['exit_reason'] = 'expired'
   position.user_defined['option_spot_close'] = position.spot_price
   pnl = position.get_profit_loss()
   print(f'expired {position} pnl: {pnl:.2f}')

# Add indicators for SPX daily prices
df_daily['50SMA'] = talib.SMA(df_daily['close'].to_numpy(), timeperiod=50)
df_daily['200SMA'] = talib.SMA(df_daily['close'].to_numpy(), timeperiod=200)
df_daily['prev_close'] = df_daily['close'].shift(-1)
df_daily['adx'] = talib.ADX(df_daily['high'].to_numpy(), df_daily['low'].to_numpy(), df_daily['close'].to_numpy(), timeperiod=14)
df_daily['cci'] = talib.CCI(df_daily['high'].to_numpy(), df_daily['low'].to_numpy(), df_daily['close'].to_numpy(), timeperiod=20)
df_daily['macd'], signal, hist = talib.MACD(df_daily['close'].to_numpy(), fastperiod=12, slowperiod=26, signalperiod=9)
df_daily['mom'] = talib.MOM(df_daily['close'].to_numpy(), timeperiod=10)
df_daily['rsi'] = talib.RSI(df_daily['close'].to_numpy(), timeperiod=14)
df_daily['stoch'], _ = talib.STOCH(high=df_daily['high'].to_numpy(),
                          low=df_daily['low'].to_numpy(),
                          close=df_daily['close'].to_numpy(),
                          fastk_period=14,
                          slowk_period=3,
                          slowk_matype=talib.MA_Type.SMA,
                          slowd_period=3,
                          slowd_matype=talib.MA_Type.SMA)
stoch_rsi, _ = calculate_stoch_rsi(df_daily, 14, 14, 3, 3)
df_daily['stoch_rsi'] = stoch_rsi
df_daily['atr_10'] = talib.ATR(df_daily['high'].to_numpy(), df_daily['low'].to_numpy(), df_daily['close'].to_numpy(), timeperiod=10)
df_daily['atr_60'] = talib.ATR(df_daily['high'].to_numpy(), df_daily['low'].to_numpy(), df_daily['close'].to_numpy(), timeperiod=60)
df_daily['atr_ratio'] = df_daily['atr_10'] / df_daily['atr_60']
df_daily['direction'] = np.sign(df_daily['close'].diff())
df_daily['streak_id'] = (df_daily['direction'] != df_daily['direction'].shift()).cumsum()
df_daily['streak_ct'] = df_daily.groupby('streak_id').cumcount() + 1
df_daily['streak_count'] = df_daily['streak_ct'] * df_daily['direction']


df_stats['put_call_skew'] = df_stats['iv_30_put'] / df_stats['iv_30_call']


df_daily = df_daily.loc[(df_daily.index >= start_date) & (df_daily.index <= end_date)]
df = df[(df.index >= start_date) & (df.index <= end_date+timedelta(days=1))]

df_dates = pd.Series(df_daily.index.date, index=df_daily.index)
df['50MA'] = df.index.normalize().map(df_daily['50SMA'])
df['200MA'] = df.index.normalize().map(df_daily['200SMA'])
df['daily_prev_close'] = df.index.normalize().map(df_daily['prev_close'])
df['adx']  = df.index.normalize().map(df_daily['adx'] )
df['cci'] = df.index.normalize().map(df_daily['cci'])
df['macd'] = df.index.normalize().map(df_daily['macd'])
df['mom'] = df.index.normalize().map(df_daily['mom'])
df['rsi'] = df.index.normalize().map(df_daily['rsi'])
df['stoch'] = df.index.normalize().map(df_daily['stoch'])
df['stoch_rsi'] = df.index.normalize().map(df_daily['stoch_rsi'])
df['net_gamma'] = df.index.normalize().map(df_sg['Net Gamma'])
df['atr_ratio'] = df.index.normalize().map(df_daily['atr_ratio'])
df['put_call_skew'] = df.index.normalize().map(df_stats['put_call_skew'])

df_vix = df_vix[(df_vix.index >= start_date) & (df_vix.index <= end_date+timedelta(days=1))]

portfolio = OptionPortfolio(cash=starting_cash, start_date=start_date, end_date=end_date)
portfolio.bind(position_expired=on_expired)

dts = get_market_dates(start_date=start_date, end_date=end_date)

consecutive_streak = 0
for dt in dts[1:]:
   print(dt)
   dt_yesterday = dts[dts.index(dt)-1]
   yesterday = df_daily.loc[dt_yesterday]
   yesterday_close = yesterday['close']
   today = df_daily.loc[dt]
   vix_yesterday = df_vix_daily.loc[dt_yesterday]

   # find out if today is a 0dte day
   dt_tm = datetime.combine(dt, open_trade_time)
   portfolio.next(dt_tm, ticker)
   option_chain = portfolio.option_chains.get(ticker)
   expirations = option_chain.expirations
   if len(expirations) == 0:
      continue
   expiration = snap(dt.date(), expirations)

   # Check if this is a 0DTE day
   if expiration != dt.date():
      continue

   df_tm = df.loc[dt_tm]
   close = df_tm['close']
   df_vix_tm = df_vix.loc[dt_tm]

   # check that price is above the 50-day and 200-day MA
   yesterday_50MA = yesterday['50SMA']
   yesterday_200MA = yesterday['200SMA']
   cond_gt_50ma = close > yesterday_50MA
   cond_gt_200ma =  close > yesterday_200MA

   # check vix maximum rule: VIX <= 20 (vix_max)
   vix = df_vix_tm['close']
   cond_vix_lt_20 = vix < vix_max

   # check vix change rule: VIX Change -0.03
   vix_prev_close = vix_yesterday['close']
   vix_idx = df_vix.index.get_loc(dt_tm)
   vix_prev = df_vix.iloc[vix_idx - 1]['close']

   vix_chg = vix_prev - vix
   cond_vix_chg_lt_max = vix_chg <= vix_chg_max

   # check spx change from yesterday close: Change % > 0

   chg_from_close = round((close - yesterday_close ) / yesterday_close, 2)
   cond_chg_gt_zero = chg_from_close >= chg_from_close_min

   # check spx change from open today: Open Change % >= 0.55 %
   open_px = today['open']
   chg_from_open = round((close - open_px) / open_px, 2)
   cond_chg_from_open = chg_from_open <= chg_from_open_max

   # check adx level: SPX intraday ADX(14)  >= 10
   adx = today['adx']
   cond_adx = adx > adx_min

   # check cci level: SPX intraday CCI(20) <= 160
   cci = today['cci']
   cond_cci = cci < cci_max

   # check macd level: MACD (12,26,9) in range -25 to 90
   macd = today['macd']
   cond_macd = macd > macd_min

   # check momentum level: Momentum (10) -50 to 247
   mom = today['mom']
   cond_mom = mom_min < mom < mom_max

   # check rsi level: RSI (14) >= 45
   rsi = today['rsi']
   cond_rsi = rsi > rsi_min

   # check stochastic level: Stoch (14, 3, 3) >= 32
   stoch = today['stoch']
   cond_stoch = stoch < stoch_max

   # check stochastic rsi level: Stoch RSI (14, 14, 3, 3) >= 50
   stoch_rsi = today['stoch_rsi']
   cond_stoch_rsi = stoch_rsi > stoch_rsi_min

   net_gamma = df_tm['net_gamma']
   cond_net_gamma = df_tm['net_gamma'] < 2

   atr_ratio = df_tm['atr_ratio']

   put_call_skew = df_tm['put_call_skew']

   # check all conditions
   if True: #cond_gt_200ma & cond_vix_lt_20 & cond_macd & cond_stoch & cond_net_gamma:

      # all conditions are true, find option at this expiration with the closest delta, and open a position
      options = [x for x in option_chain.options if x['option_type'] == 'put' and x['expiration'] == expiration]
      options = sorted(options, key=lambda x: x['delta'], reverse=True)
      option_data = next(x for x in options if x['delta'] < target_delta)
      strike = option_data['strike']
      if strike >= close:
         raise ValueError("this is very bad.")

      option = Single.create(option_chain, expiration, strike, 'put')

      px = option.option.get_open_price(position_type=OptionPositionType.LONG)
      max_risk = 2_500 #portfolio.current_value * max_risk_pct
      qty = max(1, int(np.floor(max_risk / (px * 100))))
      spot_price = option.spot_price
      tm_spot_price = close

      exp_tm = datetime.combine(dt, time(16, 0))
      df_tm = df.loc[exp_tm]

      streak_count = yesterday['streak_count']

      portfolio.open_position(option, quantity=qty, option_spot_open=spot_price, tm_spot_open=tm_spot_price, tm_spot_close=df_tm['close'],
                              vix=vix, ma50=yesterday_50MA, ma200=yesterday_200MA, chg_from_close=chg_from_close,
                              spx_prev_close=yesterday_close, spx_open=open_px,
                              macd=macd,stoch=stoch,
                              net_gamma=net_gamma,
                              streak_count=streak_count)

      # Set time to EOD so the option expires

      portfolio.next(exp_tm)



closed_positions = portfolio.closed_positions.copy()

trades = []
for x in closed_positions:
   history = x.get_history()
   max_profit = max(x['pnl'] for x in history)
   max_pct = max(x['pnl_pct'] for x in history)
   trade = {
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
      'vix': x.user_defined['vix'],
      'ma50': x.user_defined['ma50'],
      'ma200': x.user_defined['ma200'],
      'spx_prev_close': x.user_defined['spx_prev_close'],
      'chg_from_close': x.user_defined['chg_from_close'],
      'spx_open': x.user_defined['spx_open'],
      'macd': x.user_defined['macd'],
      'stoch': x.user_defined['stoch'],
      'net_gamma': x.user_defined['net_gamma'],
      'streak_count': x.user_defined['streak_count'],
   }
   trades.append(trade)

df_trades = pd.DataFrame(trades)
df_trades.to_csv(r'D:\test_data\day_trading\spx_low_delta\unfiltered_trades_test2_3delta.csv', index=False)

