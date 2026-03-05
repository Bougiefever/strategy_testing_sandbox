import pandas as pd
import numpy as np
import datetime
from pathlib import Path
from ibd_utility import *
from dataclasses import dataclass
from typing import Optional

output_folder = Path(r'D:\test_data\club\vibha_tqqq')
comp_fn = Path(r'D:\projects\data\nasdaq_composite.csv')
df_comp = pd.read_csv(comp_fn, parse_dates=['date'])
df_comp.set_index('date', inplace=True)
df_comp.sort_index(inplace=True)

tqqq_fn = Path(r'D:\stock_data\daily\TQQQ.parquet')
df = pd.read_parquet(tqqq_fn, engine='pyarrow')
df.set_index('quote_datetime', inplace=True)
df.sort_index(inplace=True)

market_signals = run_market_state(df_comp)

def calculate_tqqq_signals(df):
    """
    Calculate Vibha's quantifiable TQQQ sell signals.
    Runs on TQQQ price data.

    Signals calculated:
        sell_1: 52-week high (awareness, not hard sell)
        sell_2: new high on declining volume (3-day volume trend)
        sell_4: close below 10-day MA on rising volume
        sell_5: three consecutive down days
        sell_6: three consecutive down days + rising volume + lower lows + lower highs
        sell_7: triple rejection at resistance (3 touches of same level, each rejected)
        sell_9: close below 10-week (50-day) MA on rising volume in lower half of range
        sell_10: two consecutive closes below 21 EMA

    Returns:
        DataFrame with sell signal columns and moving averages added
    """
    df = df.copy()
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    volumes = df['volume'].values
    n = len(df)

    # Moving averages
    df['ma_10'] = df['close'].rolling(10).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ma_50'] = df['close'].rolling(50).mean()
    df['high_52w'] = df['high'].rolling(252).max()
    df['vol_ma_10'] = df['volume'].rolling(10).mean()

    ma_10 = df['ma_10'].values
    ema_21 = df['ema_21'].values
    ma_50 = df['ma_50'].values
    high_52w = df['high_52w'].values
    vol_ma_10 = df['vol_ma_10'].values

    # Signal arrays
    sell_1 = np.zeros(n, dtype=bool)   # 52-week high
    sell_2 = np.zeros(n, dtype=bool)   # new high, declining volume
    sell_4 = np.zeros(n, dtype=bool)   # below 10-day MA on rising volume
    sell_5 = np.zeros(n, dtype=bool)   # 3 consecutive down days
    sell_6 = np.zeros(n, dtype=bool)   # 3 down days + volume + lower lows/highs
    sell_7 = np.zeros(n, dtype=bool)   # triple rejection
    sell_9 = np.zeros(n, dtype=bool)   # below 50-day MA, rising vol, lower half
    sell_10 = np.zeros(n, dtype=bool)  # 2 closes below 21 EMA

    # Track resistance level for signal 7
    resistance_level = 0.0
    resistance_touches = 0
    resistance_tolerance = 0.005  # within 0.5% counts as same level

    for i in range(3, n):
        # --- SELL 1: 52-week high ---
        if highs[i] >= high_52w[i] and not np.isnan(high_52w[i]):
            sell_1[i] = True

        # --- SELL 2: new high on declining volume ---
        if (sell_1[i]
                and volumes[i] < volumes[i - 1]
                and volumes[i - 1] < volumes[i - 2]):
            sell_2[i] = True

        # --- SELL 4: close below 10-day MA on rising volume ---
        if (not np.isnan(ma_10[i])
                and closes[i] < ma_10[i]
                and volumes[i] > volumes[i - 1]):
            sell_4[i] = True

        # --- SELL 5: three consecutive down closes ---
        if (closes[i] < closes[i - 1]
                and closes[i - 1] < closes[i - 2]
                and closes[i - 2] < closes[i - 3]):
            sell_5[i] = True

        # --- SELL 6: three down days + rising volume + lower lows + lower highs ---
        if (sell_5[i]
                and volumes[i] > volumes[i - 1]
                and lows[i] < lows[i - 1] < lows[i - 2]
                and highs[i] < highs[i - 1] < highs[i - 2]):
            sell_6[i] = True

        # --- SELL 7: triple rejection at resistance ---
        if highs[i] >= highs[i - 1] and closes[i] < highs[i]:
            current_high = highs[i]
            if resistance_level == 0.0:
                resistance_level = current_high
                resistance_touches = 1
            elif abs(current_high - resistance_level) / resistance_level <= resistance_tolerance:
                resistance_touches += 1
                if resistance_touches >= 3:
                    sell_7[i] = True
            else:
                resistance_level = current_high
                resistance_touches = 1
        # Reset resistance tracking if price breaks decisively above
        if resistance_level > 0 and closes[i] > resistance_level * (1 + resistance_tolerance):
            resistance_level = 0.0
            resistance_touches = 0

        # --- SELL 9: close below 50-day MA, rising volume, lower half of range ---
        day_range_mid = (highs[i] + lows[i]) / 2
        if (not np.isnan(ma_50[i])
                and closes[i] < ma_50[i]
                and volumes[i] > volumes[i - 1]
                and closes[i] < day_range_mid):
            sell_9[i] = True

        # --- SELL 10: two consecutive closes below 21 EMA ---
        if (not np.isnan(ema_21[i])
                and closes[i] < ema_21[i]
                and closes[i - 1] < ema_21[i - 1]):
            sell_10[i] = True

    df['sell_1_52w_high'] = sell_1
    df['sell_2_high_low_vol'] = sell_2
    df['sell_4_below_10ma'] = sell_4
    df['sell_5_3_down_days'] = sell_5
    df['sell_6_severe_decline'] = sell_6
    df['sell_7_triple_reject'] = sell_7
    df['sell_9_below_50ma'] = sell_9
    df['sell_10_below_21ema'] = sell_10

    # Count total active sell signals on each day
    sell_cols = [c for c in df.columns if c.startswith('sell_')]
    df['sell_signal_count'] = df[sell_cols].sum(axis=1).astype(int)

    return df

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


def trades_to_dataframe(trades):
    """Convert trade list to a DataFrame for further analysis."""
    return pd.DataFrame([{
        'entry_date': t.entry_date,
        'exit_date': t.exit_date,
        'entry_price': t.entry_price,
        'exit_price': t.exit_price,
        'pnl': t.pnl,
        'pnl_pct': t.pnl_pct,
        'holding_days': t.holding_days,
        'max_drawdown_pct': t.max_drawdown_pct,
        'peak_gain_pct': t.peak_gain_pct,
        'exit_reason': t.exit_reason,
        'shares': t.shares,
    } for t in trades])


df = calculate_tqqq_signals(df)

dts = market_signals.index.intersection(df.index)
mkt = market_signals.loc[dts]
tqqq = df.loc[dts]

dts = dts.tolist()

decay_window=25,
rally_pct=0.06,
dd_threshold=-0.002,
stall_max_gain=0.004,
stall_vol_pct=0.95,
lookback_high=25,
ftd_min_gain=0.01,
ftd_min_day=4,
dday_exit_threshold=5,

# TQQQ sell signal parameters
sell_signal_exit_threshold=2,

# Position sizing
position_pct=1.0

# Arrays for fast access
tqqq_opens = tqqq['open'].values
tqqq_closes = tqqq['close'].values
tqqq_highs = tqqq['high'].values
tqqq_lows = tqqq['low'].values
mkt_is_ftd = mkt['is_ftd'].values
mkt_in_uptrend = mkt['in_uptrend'].values
mkt_exit_reason = mkt['exit_reason'].values
sell_counts = tqqq['sell_signal_count'].values
n = len(dts)

# Trade tracking
trades = []
current_trade = None
capital = 100_000
position_value = 0.0

# Daily tracking
portfolio_value = np.full(n, np.nan)
in_trade = np.zeros(n, dtype=bool)
signal_arr = [''] * n

# State
pending_entry = False    # buy at next open
pending_exit = False     # sell at next open
pending_exit_reason = ''

for i in range(n):
    # ---- EXECUTE PENDING ENTRY ----
    if pending_entry and current_trade is None:
        entry_price = tqqq_opens[i]
        shares = (capital * position_pct) / entry_price
        current_trade = Trade(
            entry_date=str(dts[i])[:10],
            entry_price=entry_price,
            shares=shares,
        )
        capital -= shares * entry_price
        signal_arr[i] = 'BUY'
        pending_entry = False

    # ---- EXECUTE PENDING EXIT ----
    elif pending_exit and current_trade is not None:
        exit_price = tqqq_opens[i]
        current_trade.exit_date = str(dts[i])[:10]
        current_trade.exit_price = exit_price
        current_trade.exit_reason = pending_exit_reason
        current_trade.pnl = (exit_price - current_trade.entry_price) * current_trade.shares
        current_trade.pnl_pct = (exit_price - current_trade.entry_price) / current_trade.entry_price
        capital += current_trade.shares * exit_price
        trades.append(current_trade)
        signal_arr[i] = f'SELL ({pending_exit_reason})'
        current_trade = None
        pending_exit = False
        pending_exit_reason = ''

    # ---- UPDATE TRADE STATS ----
    if current_trade is not None:
        current_trade.holding_days += 1
        unrealized_pct = (tqqq_closes[i] - current_trade.entry_price) / current_trade.entry_price
        current_trade.peak_gain_pct = max(current_trade.peak_gain_pct, unrealized_pct)
        current_trade.max_drawdown_pct = min(current_trade.max_drawdown_pct, unrealized_pct)
        position_value = current_trade.shares * tqqq_closes[i]
        in_trade[i] = True
    else:
        position_value = 0.0

    portfolio_value[i] = capital + position_value

    # ---- GENERATE SIGNALS FOR NEXT DAY ----

    # Entry signal: FTD fires today, buy tomorrow's open
    if mkt_is_ftd[i] and current_trade is None and not pending_entry:
        pending_entry = True

    # Exit signals (only if in a trade)
    if current_trade is not None and not pending_exit:

        # Exit 1: market state leaves uptrend
        if mkt_exit_reason[i] != '':
            pending_exit = True
            pending_exit_reason = f'market_{mkt_exit_reason[i]}'

        # Exit 2: TQQQ sell signal count hits threshold
        elif sell_counts[i] >= sell_signal_exit_threshold:
            pending_exit = True
            pending_exit_reason = f'sell_signals_{sell_counts[i]}'

# Close any open trade at last bar
if current_trade is not None:
    exit_price = tqqq_closes[-1]
    current_trade.exit_date = str(dates[-1])[:10]
    current_trade.exit_price = exit_price
    current_trade.exit_reason = 'end_of_data'
    current_trade.pnl = (exit_price - current_trade.entry_price) * current_trade.shares
    current_trade.pnl_pct = (exit_price - current_trade.entry_price) / current_trade.entry_price
    capital += current_trade.shares * exit_price
    trades.append(current_trade)

# Build daily output
daily = pd.DataFrame({
    'date': dts,
    'tqqq_close': tqqq_closes,
    'nasdaq_close': mkt['close'].values,
    'portfolio_value': portfolio_value,
    'in_trade': in_trade,
    'in_uptrend': mkt_in_uptrend,
    'dday_count': mkt['dday_count'].values,
    'sell_signal_count': sell_counts,
    'signal': signal_arr,
})
daily.set_index('date', inplace=True)
daily.to_csv(output_folder.joinpath('daily_1.csv'), index=False)
print_report(trades, daily)
df_trades  = pd.DataFrame([{
        'entry_date': t.entry_date,
        'exit_date': t.exit_date,
        'entry_price': t.entry_price,
        'exit_price': t.exit_price,
        'pnl': t.pnl,
        'pnl_pct': t.pnl_pct,
        'holding_days': t.holding_days,
        'max_drawdown_pct': t.max_drawdown_pct,
        'peak_gain_pct': t.peak_gain_pct,
        'exit_reason': t.exit_reason,
        'shares': t.shares,
    } for t in trades])

df_trades.to_csv(output_folder.joinpath('trades_1.csv'), index=False)

pass