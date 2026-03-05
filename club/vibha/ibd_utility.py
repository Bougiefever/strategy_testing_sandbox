import pandas as pd
import numpy as np
import datetime
from pathlib import Path



def get_distribution_days(df_comp: pd.DataFrame):

    decay_window = 25
    rally_pct = 0.06
    dd_threshold = -0.002
    stall_max_gain = 0.004
    stall_vol_pct = 0.95
    lookback_high = 25

    df_comp['pct_chg'] = df_comp['close'].pct_change()
    df_comp['prev_volume'] = df_comp['volume'].shift(1)
    df_comp['rolling_high'] = df_comp['high'].rolling(window=lookback_high, min_periods=1).max()
    df_comp['range_midpoint'] = (df_comp['high'] + df_comp['low']) / 2

    # Standard Distribution Days
    df_comp['is_distribution'] = (df_comp['pct_chg'] <= dd_threshold) & (df_comp['volume'] > df_comp['prev_volume'])

    # Stalling days
    df_comp['is_stalling'] = (~df_comp['is_distribution']) \
                               & (df_comp['close'] >= 0.97 * df_comp['rolling_high']) \
                               & (df_comp['close'] < df_comp['range_midpoint']) \
                               & (df_comp['pct_chg'] > 0) \
                               & (df_comp['pct_chg'] <= stall_max_gain) \
                               & (df_comp['volume'] >= stall_vol_pct * df_comp['prev_volume'])

    active_dd_days = []
    dd_day_counts = []

    dts = df_comp.index.tolist()

    for dt in dts:
        df_dt = df_comp.loc[dt]
        i = df_comp.index.get_loc(dt)
        is_distribution = df_dt['is_distribution']
        is_stalling = df_dt['is_stalling']

        if is_distribution or is_stalling:
            active_dd_days.append((i, df_dt['close']))

            # remove any from more than 25 trading days in the past
            active_dd_days = [(idx, close) for idx, close in active_dd_days if (i - idx) <= decay_window]

            # Remove any where the high of the current date is greater than 6% of the close
            active_dd_days = [(idx, close) for idx, close in active_dd_days if (df_dt['high'] - close) / close < rally_pct]

        dd_day_counts.append(len(active_dd_days))

    df_comp['dd_day_count'] = dd_day_counts
    df_comp = df_comp.drop(columns=['prev_volume','rolling_high', 'range_midpoint'])

    return df_comp

def get_follow_through_days(df_comp: pd.DataFrame):

    df_comp['pct_chg'] = df_comp['close'].pct_change()
    df_comp['prev_close'] = df_comp['close'].shift(1)
    df_comp['prev_low'] = df_comp['low'].shift(1)
    df_comp['prev_volume'] = df_comp['volume'].shift(1)
    df_comp['is_ftd'] = False
    df_comp['ftd_low'] = np.nan
    df_comp['in_uptrend'] = False
    df_comp['rally_day_count'] = 0

    uptrend = False
    current_ftd_low = float('nan')
    rally_active = False
    rally_count = 0
    rally_low = float('inf')
    ftd_min_day = 4
    ftd_min_gain = 0.01

    dts = df_comp.index.tolist()

    for dt in dts:
        df_dt = df_comp.loc[dt]

        if uptrend:
            # check for FTD failure
            if df_dt['close'] < current_ftd_low:
                uptrend = False
                rally_active = False
                rally_count = 0
                rally_low = df_dt['low']
                current_ftd_low = float('nan')

        if not uptrend:
            if not rally_active:
                # Waiting for day 1: an up close
                if df_dt['close'] > df_dt['prev_close']:
                    rally_active = True
                    rally_count = 1
                    rally_low = min(df_dt['low'], df_dt['prev_low'])
                else:
                    rally_low = min(rally_low, df_dt['low'])

            else:
                if df_dt['low'] < rally_low:
                    # rally failed, reset
                    rally_active = False
                    rally_count = 0
                    rally_low = df_dt['low']
                else:
                    rally_count += 1

                    # Check for FTD on day 4+
                    if (rally_count >= ftd_min_day and df_dt['pct_chg'] >= ftd_min_gain and df_dt['volume'] > df_dt['prev_volume']):
                        df_comp.loc[dt, 'is_ftd'] = True
                        current_ftd_low = df_dt['low']
                        uptrend = True
                        rally_active = True
                        rally_count = 0

        df_comp.loc[dt, 'in_uptrend'] = uptrend
        df_comp.loc[dt, 'ftd_low'] = current_ftd_low
        df_comp.loc[dt, 'rally_day_count'] = rally_count if rally_active else 0
        return df_comp


def run_market_state(df, decay_window=25, rally_pct=0.06,
                     dd_threshold=-0.002, stall_max_gain=0.004,
                     stall_vol_pct=0.95, lookback_high=25,
                     ftd_min_gain=0.01, ftd_min_day=4,
                     dday_exit_threshold=5):
    """
    Integrated IBD market state tracker combining distribution day counting
    and Follow-Through Day detection for TQQQ swing trading.

    Parameters:
        df: DataFrame with columns [open, high, low, close, volume], date as index

        Distribution day parameters:
            decay_window: trading days before a d-day expires (default 25)
            rally_pct: % rally from d-day close that removes it (default 6%)
            dd_threshold: min decline to count as distribution (default -0.2%)
            stall_max_gain: max gain for a stalling day (default +0.4%)
            stall_vol_pct: volume must be >= this fraction of prior day (default 95%)
            lookback_high: window for "near recent highs" stalling check (default 25)

        Follow-Through Day parameters:
            ftd_min_gain: minimum daily gain to qualify as FTD (default 1%)
            ftd_min_day: earliest rally day an FTD can occur (default day 4)

        Market state parameters:
            dday_exit_threshold: d-day count that triggers correction (default 5)

    Returns:
        DataFrame with added columns:
            pct_change: daily close-to-close return
            is_distribution: bool
            is_stalling: bool
            is_ftd: bool
            dday_count: active distribution day count
            in_uptrend: bool, current market state
            ftd_low: intraday low of most recent FTD (NaN during correction)
            rally_day_count: days into current rally attempt (0 if none)
            exit_reason: string describing why uptrend ended (empty otherwise)
    """
    df = df.copy()
    df.columns = df.columns.str.lower()

    closes = df['close'].values
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    volumes = df['volume'].values
    n = len(df)

    # Precompute rolling high for stalling detection
    rolling_high = pd.Series(highs).rolling(window=lookback_high, min_periods=1).max().values

    # Output arrays
    pct_change_arr = np.full(n, np.nan)
    is_distribution = np.zeros(n, dtype=bool)
    is_stalling = np.zeros(n, dtype=bool)
    is_ftd = np.zeros(n, dtype=bool)
    dday_count_arr = np.zeros(n, dtype=int)
    in_uptrend_arr = np.zeros(n, dtype=bool)
    ftd_low_arr = np.full(n, np.nan)
    rally_day_arr = np.zeros(n, dtype=int)
    exit_reason_arr = [''] * n

    # State variables
    uptrend = False
    current_ftd_low = float('nan')
    rally_active = False
    rally_count = 0
    rally_low = float('inf')
    active_ddays = []  # list of (index_position, close_on_that_day)

    for i in range(1, n):
        pct = (closes[i] - closes[i - 1]) / closes[i - 1]
        pct_change_arr[i] = pct

        # ======================
        # UPTREND: check exits
        # ======================
        if uptrend:

            # --- Detect distribution day ---
            if pct <= dd_threshold and volumes[i] > volumes[i - 1]:
                is_distribution[i] = True
                active_ddays.append((i, closes[i]))

            # --- Detect stalling day ---
            elif (closes[i] >= 0.97 * rolling_high[i]
                  and closes[i] < (highs[i] + lows[i]) / 2
                  and pct > 0
                  and pct <= stall_max_gain
                  and volumes[i] >= stall_vol_pct * volumes[i - 1]):
                is_stalling[i] = True
                active_ddays.append((i, closes[i]))

            # --- Remove expired d-days (25 trading days) ---
            active_ddays = [(idx, cl) for idx, cl in active_ddays
                            if (i - idx) <= decay_window]

            # --- Remove d-days exceeded by 6% rally ---
            active_ddays = [(idx, cl) for idx, cl in active_ddays
                            if (highs[i] - cl) / cl < rally_pct]

            dday_count_arr[i] = len(active_ddays)

            # --- EXIT CHECK 1: close below FTD low ---
            if closes[i] < current_ftd_low:
                uptrend = False
                active_ddays = []
                rally_active = False
                rally_count = 0
                rally_low = lows[i]
                current_ftd_low = float('nan')
                exit_reason_arr[i] = 'ftd_low_undercut'

            # --- EXIT CHECK 2: d-day count hits threshold ---
            elif len(active_ddays) >= dday_exit_threshold:
                uptrend = False
                active_ddays = []
                rally_active = False
                rally_count = 0
                rally_low = lows[i]
                current_ftd_low = float('nan')
                exit_reason_arr[i] = f'dday_count_{dday_exit_threshold}'

        # ======================
        # CORRECTION: look for FTD
        # ======================
        if not uptrend:
            dday_count_arr[i] = 0

            if not rally_active:
                # Waiting for day 1: an up close
                if closes[i] > closes[i - 1]:
                    rally_active = True
                    rally_count = 1
                    rally_low = min(lows[i], lows[i - 1])
                else:
                    rally_low = min(rally_low, lows[i])
            else:
                # Rally attempt is active — check for undercut
                if lows[i] < rally_low:
                    rally_active = False
                    rally_count = 0
                    rally_low = lows[i]
                else:
                    rally_count += 1

                    # Check for FTD on day 4+
                    if (rally_count >= ftd_min_day
                            and pct >= ftd_min_gain
                            and volumes[i] > volumes[i - 1]):
                        is_ftd[i] = True
                        current_ftd_low = lows[i]
                        uptrend = True
                        active_ddays = []
                        rally_active = False
                        rally_count = 0

        # Record state
        in_uptrend_arr[i] = uptrend
        ftd_low_arr[i] = current_ftd_low
        rally_day_arr[i] = rally_count if rally_active else 0

    # Attach to dataframe
    df['pct_change'] = pct_change_arr
    df['is_distribution'] = is_distribution
    df['is_stalling'] = is_stalling
    df['is_ftd'] = is_ftd
    df['dday_count'] = dday_count_arr
    df['in_uptrend'] = in_uptrend_arr
    df['ftd_low'] = ftd_low_arr
    df['rally_day_count'] = rally_day_arr
    df['exit_reason'] = exit_reason_arr

    return df
