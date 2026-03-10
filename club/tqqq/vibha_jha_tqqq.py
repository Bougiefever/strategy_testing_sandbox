import pandas as pd
import numpy as np
from pathlib import Path
import talib
from helpers import *


"""
=====================================================
SECTION 1: MARKET STATE (runs on Nasdaq Composite)
=====================================================
Two states:
    CORRECTION — sitting in cash, watching for entry signal
    UPTREND — in a TQQQ position, watching for exit signal
    
    * A distribution day is any day where the IXIC (Nasdaq Composite Index) drops 0.2% or more in a day in higher volume
    * Stalling days count as distribution days: 
        - Index is up 0.4% or less on volume greater than or equal to 95% of the previous day
"""
def market_state(df: pd.DataFrame):
    in_uptrend = False
    ftd_low = np.nan
    rally_active = False
    rally_count = 0
    rally_low = np.inf
    active_ddays = []

    # constants
    ftd_min_gain = 0.01
    ftd_min_day = 4
    dd_threshold = -0.002
    decay_window = 25
    rally_pct = 0.06
    dday_exit = 5
    max_high_window = 25
    stall_pct_gain = 0.004

    df = df.copy()
    dts = df.index.tolist()

    df['pct_change'] = df['close'].pct_change()
    df['rolling_high'] = df['high'].rolling(window=max_high_window).max()

    # state variables for trading
    df['ftd_low'] = np.nan
    df['in_uptrend'] = False
    df['entry_signal'] = ''
    df['dday_count'] = 0
    df['exit_reason'] = ''

    for dt in dts:
        i = df.index.get_loc(dt)
        today = df.loc[dt]
        yesterday = df.iloc[i-1]
        two_days_ago = df.iloc[i-2]
        ftd_day = False

        if in_uptrend:
            # add new distribution days if index drops dd_threshold on higher volume
            if today['pct_change'] <= dd_threshold and today['volume'] > yesterday['volume']:
                active_ddays.append((i, today['close']))

            # check for stalling day
            if (0 < today['pct_change'] <= stall_pct_gain) \
                    and (today['volume'] >= yesterday['volume'] * 0.95) \
                    and (today['close'] < ((today['high'] + today['low']) / 2)) \
                    and (today['close'] >= 0.97 * today['rolling_high']):
                active_ddays.append((i, today['close']))

            # remove expired d-days
            active_ddays = [(idx, c) for idx, c in active_ddays if (i - idx) <= decay_window]
            # remove big rally days (6% rule)
            active_ddays = [(idx, c) for idx, c in active_ddays if (today['high'] - c) / c < rally_pct]

            if today['close'] < ftd_low:
                in_uptrend = False
                ftd_low = np.nan
                active_ddays = [] # reset d-days
                rally_active = False
                rally_count = 0
                rally_low = today['low']
                df.loc[dt, 'exit_reason'] = 'FTD_LOW'
                # print(f'FALSE,{dt},{today['close']},FTD_LOW')
            elif len(active_ddays) >= dday_exit:
                in_uptrend = False
                ftd_low = np.nan
                active_ddays = []
                rally_active = False
                rally_count = 0
                rally_low = today['low']
                df.loc[dt, 'exit_reason'] = 'DDAY_COUNT'
                # print(f'FALSE,{dt},{today['close']},DDAY_COUNT')

        """
        — track rally attempt (3+ days off a low without undercutting that low)
            — on day 4+ of rally attempt, IF pct_change >= 0.01
               AND today.volume > prev.volume:
                 market_status = "CONFIRMED UPTREND"
                 CLEAR active_ddays[]
                 in_uptrend = TRUE
                
        Day 1 of rally close > yesterday close, rally_low is lesser of today and yesterday low
        Subsequent days are counted towards the rally goal of 4 days if the low does not go past the recorded rally low
        """
        if not in_uptrend:
            if not rally_active:
                if today['close'] > yesterday['close']:
                    rally_count = 1
                    rally_active = True
                    rally_low = min(today['low'], yesterday['low'])
                else:
                    rally_low = min(today['low'], rally_low)

            elif rally_active:
                if today['low'] < rally_low:
                    rally_active = False
                    rally_count = 0
                    rally_low = today['low']
                else:
                    rally_count += 1
                    if rally_count >= ftd_min_day \
                            and (today['pct_change'] >= ftd_min_gain) \
                            and today['volume'] > yesterday['volume']:
                        ftd_low = today['low']
                        ftd_day = True
                        in_uptrend = True
                        active_ddays = []
                        rally_active = False
                        rally_count = 0
                        df.loc[dt, 'entry_signal'] = 'FTD'
                        # print(f'TRUE,{dt},{today['close']},FTD')

            if not ftd_day:
                if (today['high'] > yesterday['high'] > two_days_ago['high']) \
                        and (today['low'] > yesterday['low'] > two_days_ago['low']):
                    ftd_low = min(today['low'], yesterday['low'], two_days_ago['low'])
                    in_uptrend = True
                    active_ddays = []
                    rally_active = False
                    rally_count = 0
                    df.loc[dt, 'entry_signal'] = '3WK'
                    # print(f'TRUE,{dt},{today['close']},3WK')

        df.loc[dt, 'ftd_low'] = ftd_low
        df.loc[dt, 'in_uptrend'] = in_uptrend
        df.loc[dt, 'dday_count'] = len(active_ddays)

    return df

def generate_sell_signals(df):
    resistance_tolerance = 0.005
    resistance_level = 0.0
    resistance_touches = 0
    resistance_started = 0
    resistance_max_window = 20

    df = df.copy()
    df['ma_10'] = talib.SMA(df['close'].to_numpy(float), timeperiod=10)
    df['ema_21'] = talib.EMA(df['close'].to_numpy(float), timeperiod=21)
    df['yesterday_ema_21'] = df['ema_21'].shift(1)
    df['ma_50'] = talib.MA(df['close'].to_numpy(float), timeperiod=50)
    df['52_wk_high'] = df['high'].rolling(252, min_periods=252).max()
    df['yesterday_volume'] = df['volume'].shift(1)
    df['two_days_ago_volume'] = df['volume'].shift(2)
    df['yesterday_close'] = df['close'].shift(1)
    df['two_days_ago_close'] = df['close'].shift(2)
    df['three_days_ago_close'] = df['close'].shift(3)
    df['yesterday_high'] = df['high'].shift(1)
    df['two_days_ago_high'] = df['high'].shift(2)
    df['yesterday_low'] = df['low'].shift(1)
    df['two_days_ago_low'] = df['low'].shift(2)

    df['signal_1'] = df['high'] >= df['52_wk_high']
    df['signal_2'] = df['signal_2'] = df['signal_1'] & (df['volume'] < df['yesterday_volume']) & (df['yesterday_volume'] < df['two_days_ago_volume'])
    df['signal_4'] = (df['close'] < df['ma_10']) & (df['volume'] > df['yesterday_volume'])
    df['signal_5'] = df.apply(lambda x: (x['close'] < x['yesterday_close'] < x['two_days_ago_close'] < x['three_days_ago_close']), axis=1)
    df['signal_6'] = df.apply(lambda x: x['signal_5'] & (x['volume'] > x['yesterday_volume']) \
                                        & (x['low'] < x['yesterday_low'] < x['two_days_ago_low']) \
                                        & (x['high'] < x['yesterday_high'] < x['two_days_ago_high']), axis=1)
    df['signal_9'] = (df['close'] < df['ma_50']) \
                        & (df['volume'] > df['yesterday_volume']) \
                        & (df['close'] < (df['high'] + df['low'])/2)
    df['signal_10'] = (df['close'] < df['ema_21']) & (df['yesterday_close'] < df['yesterday_ema_21'])

    # signal 7 - rejects 3x off of resistance within 20 days
    df['signal_7'] = False
    dts = df.index.tolist()

    for dt in dts[1:]:
        i = df.index.get_loc(dt)
        today = df.loc[dt]
        yesterday = df.iloc[i-1]

        if resistance_level > 0:
            if today['close'] > resistance_level * (1 + resistance_tolerance):
                resistance_level = 0.0
                resistance_touches = 0
            elif (i - resistance_started) > resistance_max_window:
                resistance_level = 0.0
                resistance_touches = 0

        if resistance_level == 0.0:
            if (today['high'] >= yesterday['high']) and (today['close'] < today['high']):
                resistance_level = today['high']
                resistance_touches = 1
                resistance_started = i

        elif (today['high'] >= resistance_level * (1 - resistance_tolerance)
                    and (today['high'] <= resistance_level * (1 + resistance_tolerance))
                    and (today['close'] < resistance_level)):
            resistance_touches += 1
            if resistance_touches >= 3:
                df.loc[dt, 'signal_7'] = True

    df['sell_signal_count'] = df['signal_1'].astype(int) + df['signal_2'].astype(int) + df['signal_4'].astype(int) \
                                    + df['signal_5'].astype(int) + df['signal_6'].astype(int) + df['signal_9'].astype(int) \
                                    + df['signal_10'].astype(int) + df['signal_7'].astype(int)

    """
      Awareness tier:
        Signal 1:  52-week high                     0.5
        Signal 2:  new high on declining volume      1.0
    
      Caution tier:
        Signal 5:  three consecutive down days       1.5
        Signal 7:  triple rejection at resistance    1.5
        Signal 10: two closes below 21 EMA           2.0
    
      Danger tier:
        Signal 4:  close below 10-day MA on volume   2.5
        Signal 9:  close below 50-day MA, bad action 3.0
        Signal 6:  severe decline                    3.0
    
      OVERLAP RULES (don't double count):
        If signal 6 is true, don't also count signal 5
        If signal 2 is true, don't also count signal 1
    """

    for t in df.itertuples():
        score = 0.0
        signals_fired = []

        if t.signal_6:
            score += 3.0
            signals_fired.append('S6')
        elif t.signal_5:
            score += 1.5
            signals_fired.append('S5')

        if t.signal_2:
            score += 1.0
            signals_fired.append('S2')
        elif t.signal_1:
            score += 0.5
            signals_fired.append('S1')

        if t.signal_4:
            score += 2.5
            signals_fired.append('S4')
        if t.signal_7:
            score += 1.5
            signals_fired.append('S7')
        if t.signal_9:
            score += 3.0
            signals_fired.append('S9')
        if t.signal_10:
            score += 2.0
            signals_fired.append('S10')

        df.loc[t[0], 'signal_score'] = score
        df.loc[t[0], 'signals_fired'] = '|'.join(signals_fired) if signals_fired else ''

    return df[['signal_1', 'signal_2', 'signal_4',
       'signal_5', 'signal_6', 'signal_7', 'signal_9', 'signal_10',
       'sell_signal_count', 'signal_score', 'signals_fired']]

def perform_trades(df, df_state, df_signals):
    df = df.dropna()
    start_date = df.iloc[0].name.to_pydatetime()
    end_date = df_state.iloc[-1].name.to_pydatetime()

    df = df.loc[start_date:end_date]
    df_state = df_state.loc[start_date:end_date]
    df_signals = df_signals.loc[start_date:end_date]

    dts = df.index.tolist()

    equity = 100_000

    current_trade = None
    pending_entry = False
    pending_entry_type = ""
    pending_exit = False
    pending_exit_reason = ""
    ftd_confirm_pending = False
    ftd_confirm_close = np.nan
    ftd_low = np.nan
    sell_signal_count = 2

    full_position = 1.0
    half_position = 0.5

    trades = []
    daily_record = []
    for dt in dts:
        i = df.index.get_loc(dt)
        if dt not in df.index or dt not in df_state.index or dt not in df_signals.index:
            continue
        print(dt)
        #-------------------------------------------------
        # Execute Pending Entry
        #-------------------------------------------------
        if pending_entry and current_trade is None:
            if pending_entry_type == "FTD":
                size = full_position
            else:
                size = half_position

            entry_price = df.loc[dt, 'open']
            shares = int(np.floor((equity * size) / entry_price))
            current_trade = {
                'entry_date': dt,
                'entry_price': entry_price,
                'entry_type': pending_entry_type,
                'shares': shares,
                'peak_gain_pct': 0.0,
                'max_drawdown_pct': 0.0,
                'days_in_trade': 0,
                'signal_score': 0.0,
                'signals_fired': '',
                'signal_count': 0,
            }

            equity -= shares * entry_price
            pending_entry = False
            pending_entry_type = ""

        # -------------------------------------------------
        # Exit trade
        # -------------------------------------------------

        if pending_exit and current_trade is not None:
            exit_price = df.loc[dt, 'open']
            current_trade['pnl'] = (exit_price - current_trade['entry_price']) * current_trade['shares']
            current_trade['pnl_pct'] = (exit_price - current_trade['entry_price']) / current_trade['entry_price']
            equity += current_trade['shares'] * exit_price
            current_trade['exit_price'] = exit_price
            current_trade['exit_reason'] = pending_exit_reason
            current_trade['exit_date'] = dt
            trades.append(current_trade)

            current_trade = None
            pending_exit = False
            pending_exit_reason = ""

        # -------------------------------------------------
        # Update current trade
        # -------------------------------------------------
        if current_trade is not None:
            close = df.loc[dt, 'close']
            current_trade['days_in_trade'] += 1
            unrealized_pct = (close - current_trade['entry_price']) / current_trade['entry_price']
            current_trade['peak_gain_pct'] = max(current_trade['peak_gain_pct'], unrealized_pct)
            current_trade['max_drawdown_pct'] = min(current_trade['max_drawdown_pct'], unrealized_pct)

        #-------------------------------------------------
        # Generate Entry Signals
        #-------------------------------------------------

        if current_trade is None and not pending_entry:
            entry_signal = df_state.loc[dt, 'entry_signal']
            nasdaq_close = df_state.loc[dt, 'close']

            if entry_signal == 'FTD':
                ftd_confirm_pending = True
                ftd_confirm_close = nasdaq_close
                ftd_low = df_state.loc[dt, 'ftd_low']
            elif ftd_confirm_pending:
                if nasdaq_close > ftd_confirm_close:
                    pending_entry = True
                    pending_entry_type = "FTD"
                    ftd_confirm_pending = False
                elif nasdaq_close < ftd_low:
                    ftd_confirm_pending = False

            if entry_signal == '3WK':
                pending_entry = True
                pending_entry_type = "3WK"
                ftd_low = df_state['ftd_low']

        # -------------------------------------------------
        # Generate Exit Signals
        # -------------------------------------------------

        elif current_trade is not None and not pending_exit:
            exit_reason = df_state.loc[dt, 'exit_reason']
            signal_score = df_signals.loc[dt, 'signal_score']
            signal_count = df_signals.loc[dt, 'sell_signal_count']
            if exit_reason == 'FTD_LOW' or exit_reason == 'DDAY_COUNT':
                pending_exit = True
                pending_exit_reason = exit_reason
            elif signal_count >= 2:
                pending_exit = True
                pending_exit_reason = f'SCORE {signal_score:.1f}'
                current_trade['signal_score'] = signal_score
                current_trade['signals_fired'] = df_signals.loc[dt, 'signals_fired']
                current_trade['signal_count'] = df_signals.loc[dt, 'sell_signal_count']

        # record daily record
        daily_record.append({
            'date': dt,
            'tqqq_close': df.loc[dt, 'close'],
            'portfolio_value': equity + (current_trade['shares'] * df.loc[dt, 'close'] if current_trade else 0),
            'in_trade': current_trade is not None,
            'in_uptrend': df_state.loc[dt, 'in_uptrend'],
            'dday_count': df_state.loc[dt, 'dday_count'],
            'sell_signal_score': df_signals.loc[dt, 'signal_score'],
        })

    return daily_record, trades


if __name__ == "__main__":
    output_folder = Path(r'D:\test_data\club\vibha_tqqq')
    comp_fn = Path(r'D:\projects\data\nasdaq_composite.csv')
    df_comp = pd.read_csv(comp_fn, parse_dates=['date'])
    df_comp.set_index('date', inplace=True)
    df_comp.sort_index(inplace=True)

    tqqq_fn = Path(r'D:\stock_data\daily\TQQQ.parquet')
    df_tqqq = pd.read_parquet(tqqq_fn, engine='pyarrow')
    df_tqqq.set_index('quote_datetime', inplace=True)
    df_tqqq.sort_index(inplace=True)

    df_state = market_state(df_comp)
    df_sell_signals = generate_sell_signals(df_tqqq)
    daily_record, trades = perform_trades(df_tqqq, df_state, df_sell_signals)
    df_daily = pd.DataFrame(daily_record)
    df_trades = pd.DataFrame(trades)
    print_report(df_trades, df_daily, strategy="Vibha Jha Strategy")
    pass
    

