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

def max_drawdown_stats(equity: pd.Series):
    peak = equity.cummax()
    dd = equity / peak - 1.0
    max_dd = float(dd.min())  # negative

    underwater = dd < 0
    grp = (underwater != underwater.shift(1)).cumsum()
    run_lengths = underwater.groupby(grp).sum()
    max_dd_dur = int(run_lengths.max()) if len(run_lengths) else 0
    return dd, max_dd, max_dd_dur

def cagr_from_equity(equity: pd.Series):
    equity = equity.dropna()
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return np.nan
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)

def sharpe_sortino(daily_rets: pd.Series, ann_factor=252, rf_daily=0.0):
    r = daily_rets.dropna()
    ex = r - rf_daily
    mu = ex.mean()
    sigma = ex.std(ddof=0)
    sharpe = np.nan if sigma == 0 else float(mu / sigma * np.sqrt(ann_factor))

    downside = ex[ex < 0]
    d_sigma = downside.std(ddof=0)
    sortino = np.nan if d_sigma == 0 else float(mu / d_sigma * np.sqrt(ann_factor))
    return sharpe, sortino

def omega_ratio(daily_rets: pd.Series, threshold=0.0):
    r = daily_rets.dropna()
    gains = (r - threshold).clip(lower=0).sum()
    losses = (threshold - r).clip(lower=0).sum()
    return np.nan if losses == 0 else float(gains / losses)

def position_coverage(trades: pd.DataFrame, index: pd.DatetimeIndex) -> float:
    in_pos = pd.Series(False, index=index)
    for _, r in trades.iterrows():
        start = pd.to_datetime(r["entry_dt"]).normalize()
        end = pd.to_datetime(r["exit_dt"]).normalize()
        if start in in_pos.index or end in in_pos.index:
            in_pos.loc[start:end] = True
    return float(in_pos.mean() * 100.0)

def trade_stats(trades: pd.DataFrame) -> pd.Series:
    t = trades.copy()

    if "net_pnl" not in t.columns:
        t["net_pnl"] = t["pnl"] - t.get("fees", 0.0)

    t["duration_days"] = (t["exit_date"] - t["entry_date"]).dt.total_seconds() / 86400.0

    wins = t[t["net_pnl"] > 0]
    losses = t[t["net_pnl"] < 0]

    gross_win = wins["net_pnl"].sum()
    gross_loss = losses["net_pnl"].sum()  # negative

    profit_factor = np.nan if gross_loss == 0 else float(gross_win / abs(gross_loss))
    win_rate = np.nan if len(t) == 0 else float(len(wins) / len(t))

    out = {
        "Total Trades": int(len(t)),
        "Win Rate [%]": win_rate * 100.0,
        "Profit Factor": profit_factor,
        "Expectancy (avg net pnl / trade)": float(t["net_pnl"].mean()) if len(t) else np.nan,
        "Best Trade [$]": float(t["net_pnl"].max()) if len(t) else np.nan,
        "Worst Trade [$]": float(t["net_pnl"].min()) if len(t) else np.nan,
        "Avg Winning Trade [$]": float(wins["net_pnl"].mean()) if len(wins) else np.nan,
        "Avg Losing Trade [$]": float(losses["net_pnl"].mean()) if len(losses) else np.nan,
        "Avg Winning Duration [days]": float(wins["duration_days"].mean()) if len(wins) else np.nan,
        "Avg Losing Duration [days]": float(losses["duration_days"].mean()) if len(losses) else np.nan,
        "Total Fees Paid": float(t.get("fees", 0.0).sum()) if "fees" in t.columns else 0.0,
    }
    return pd.Series(out)

def portfolio_stats(nlv: pd.Series, trades: pd.DataFrame,
                            cash: pd.Series | None = None,
                            margin: pd.Series | None = None,
                            ann_factor=252, rf_daily=0.0, omega_threshold=0.0) -> pd.Series:
    aligned = _align_series(nlv, cash=cash, margin=margin)
    nlv = aligned["nlv"]

    daily_rets = nlv.pct_change().fillna(0.0)

    dd, max_dd, max_dd_dur = max_drawdown_stats(nlv)
    _cagr = cagr_from_equity(nlv)
    sharpe, sortino = sharpe_sortino(daily_rets, ann_factor=ann_factor, rf_daily=rf_daily)
    calmar = np.nan if max_dd == 0 else float(_cagr / abs(max_dd))
    omega = omega_ratio(daily_rets, threshold=omega_threshold)

    out = {
        "Start Index": nlv.index[0],
        "End Index": nlv.index[-1],
        "Total Duration": nlv.index[-1] - nlv.index[0],
        "Start Value": float(nlv.iloc[0]),
        "Min Value": float(nlv.min()),
        "Max Value": float(nlv.max()),
        "End Value": float(nlv.iloc[-1]),
        "Total Return [%]": float((nlv.iloc[-1] / nlv.iloc[0] - 1.0) * 100.0),
        "CAGR [%]": float(_cagr * 100.0),
        "Max Drawdown [%]": float(max_dd * 100.0),
        "Max Drawdown Duration [days]": int(max_dd_dur),
        "Sharpe Ratio": float(sharpe),
        "Calmar Ratio": float(calmar),
        "Omega Ratio": float(omega),
        "Sortino Ratio": float(sortino),
    }

    # "Position Coverage" from trades
    if trades is not None and len(trades):
        out["Position Coverage [%]"] = position_coverage(trades, nlv.index)

    # Margin utilization as "exposure" proxy
    if margin is not None:
        margin_aligned = aligned["margin"]
        util = (margin_aligned / nlv.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
        out["Max Margin Utilization [%]"] = float(util.max() * 100.0)
        out["Avg Margin Utilization [%]"] = float(util.mean() * 100.0)

    # Cash utilization (optional sanity checks)
    if cash is not None:
        cash_aligned = aligned["cash"]
        out["Min Cash"] = float(cash_aligned.min())
        out["Avg Cash"] = float(cash_aligned.mean())

    # Trade stats block
    if trades is not None and len(trades):
        out.update(trade_stats(trades).to_dict())

    return pd.Series(out)

@dataclass
class Trade:
    entry_date: str
    entry_price: float
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    shares: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    holding_days: int = 0
    max_drawdown_pct: float = 0.0
    peak_gain_pct: float = 0.0

def print_report(trades, daily):
    """Print comprehensive backtest results."""

    if not trades:
        print("No trades generated.")
        return

    print("=" * 70)
    print("TQQQ SWING TRADING BACKTEST RESULTS")
    print("Vibha Jha Strategy")
    print("=" * 70)

    # --- Portfolio summary ---
    start_val = daily['portfolio_value'].iloc[0]
    end_val = daily['portfolio_value'].iloc[-1]
    total_return = (end_val - start_val) / start_val
    start_date = str(daily.index[0])[:10]
    end_date = str(daily.index[-1])[:10]
    years = len(daily) / 252

    # CAGR
    cagr = (end_val / start_val) ** (1 / years) - 1 if years > 0 else 0

    # Max drawdown on portfolio
    running_max = daily['portfolio_value'].cummax()
    drawdown = (daily['portfolio_value'] - running_max) / running_max
    max_dd = drawdown.min()
    max_dd_date = str(drawdown.idxmin())[:10]

    # Time in market
    days_in_trade = daily['in_trade'].sum()
    pct_in_market = days_in_trade / len(daily)

    print(f"\nPeriod:              {start_date} to {end_date} ({years:.1f} years)")
    print(f"Starting capital:    ${start_val:,.0f}")
    print(f"Ending capital:      ${end_val:,.0f}")
    print(f"Total return:        {total_return:+.1%}")
    print(f"CAGR:                {cagr:+.1%}")
    print(f"Max drawdown:        {max_dd:.1%} (on {max_dd_date})")
    print(f"Time in market:      {pct_in_market:.1%}")

    # --- Buy & hold comparison ---
    tqqq_start = daily['tqqq_close'].iloc[0]
    tqqq_end = daily['tqqq_close'].iloc[-1]
    bh_return = (tqqq_end - tqqq_start) / tqqq_start
    bh_cagr = (tqqq_end / tqqq_start) ** (1 / years) - 1 if years > 0 else 0

    print(f"\n--- Buy & Hold TQQQ Comparison ---")
    print(f"TQQQ B&H return:     {bh_return:+.1%}")
    print(f"TQQQ B&H CAGR:       {bh_cagr:+.1%}")

    # --- Trade statistics ---
    n_trades = len(trades)
    # Exclude end_of_data trade from win/loss stats if still open
    closed_trades = [t for t in trades if t.exit_reason != 'end_of_data']
    n_closed = len(closed_trades)

    winners = [t for t in closed_trades if t.pnl > 0]
    losers = [t for t in closed_trades if t.pnl <= 0]
    n_win = len(winners)
    n_loss = len(losers)
    win_rate = n_win / n_closed if n_closed > 0 else 0

    avg_win = np.mean([t.pnl_pct for t in winners]) if winners else 0
    avg_loss = np.mean([t.pnl_pct for t in losers]) if losers else 0
    avg_hold_win = np.mean([t.holding_days for t in winners]) if winners else 0
    avg_hold_loss = np.mean([t.holding_days for t in losers]) if losers else 0

    largest_win = max([t.pnl_pct for t in winners]) if winners else 0
    largest_loss = min([t.pnl_pct for t in losers]) if losers else 0

    total_pnl = sum(t.pnl for t in closed_trades)
    gross_wins = sum(t.pnl for t in winners) if winners else 0
    gross_losses = sum(t.pnl for t in losers) if losers else 0
    profit_factor = abs(gross_wins / gross_losses) if gross_losses != 0 else float('inf')

    avg_peak = np.mean([t.peak_gain_pct for t in closed_trades]) if closed_trades else 0
    avg_dd = np.mean([t.max_drawdown_pct for t in closed_trades]) if closed_trades else 0

    print(f"\n--- Trade Statistics ({n_closed} closed trades) ---")
    print(f"Total trades:        {n_trades} ({n_closed} closed, "
          f"{'1 open' if n_trades > n_closed else '0 open'})")
    print(f"Win rate:            {win_rate:.1%} ({n_win}W / {n_loss}L)")
    print(f"Avg winner:          {avg_win:+.1%} (held {avg_hold_win:.0f} days)")
    print(f"Avg loser:           {avg_loss:+.1%} (held {avg_hold_loss:.0f} days)")
    print(f"Largest winner:      {largest_win:+.1%}")
    print(f"Largest loser:       {largest_loss:+.1%}")
    print(f"Profit factor:       {profit_factor:.2f}")
    print(f"Avg peak gain:       {avg_peak:+.1%}")
    print(f"Avg max drawdown:    {avg_dd:.1%}")
    print(f"Total P&L:           ${total_pnl:+,.0f}")

    # --- Exit reason breakdown ---
    print(f"\n--- Exit Reasons ---")
    reasons = {}
    for t in closed_trades:
        r = t.exit_reason
        if r not in reasons:
            reasons[r] = {'count': 0, 'total_pnl': 0.0}
        reasons[r]['count'] += 1
        reasons[r]['total_pnl'] += t.pnl
    for reason, stats in sorted(reasons.items(), key=lambda x: -x[1]['count']):
        print(f"  {reason:35s}  {stats['count']:3d} trades  ${stats['total_pnl']:+12,.0f}")

    # --- Annual returns ---
    print(f"\n--- Annual Returns ---")
    daily_copy = daily.copy()
    daily_copy.index = pd.to_datetime(daily_copy.index)
    yearly = daily_copy['portfolio_value'].resample('YE').last()
    yearly_start = daily_copy['portfolio_value'].resample('YS').first()
    for end, start in zip(yearly.items(), yearly_start.items()):
        year_return = (end[1] - start[1]) / start[1]
        print(f"  {end[0].year}:  {year_return:+8.1%}    (${end[1]:>12,.0f})")

    # --- Trade log ---
    print(f"\n--- Trade Log ---")
    print(f"{'Entry':>12s} {'Exit':>12s} {'Entry$':>10s} {'Exit$':>10s} "
          f"{'Return':>8s} {'Days':>5s}  {'Reason'}")
    print("-" * 85)
    for t in trades:
        print(f"{t.entry_date:>12s} {t.exit_date:>12s} "
              f"${t.entry_price:>9.2f} ${t.exit_price:>9.2f} "
              f"{t.pnl_pct:>+7.1%} {t.holding_days:>5d}  {t.exit_reason}")

    print("=" * 70)