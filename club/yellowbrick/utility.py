import pandas as pd
import numpy as np

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
    df['dday_count'] = 0

    for dt in dts:
        i = df.index.get_loc(dt)
        today = df.loc[dt]
        yesterday = df.iloc[i - 1]
        two_days_ago = df.iloc[i - 2]
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
                active_ddays = []  # reset d-days
                rally_active = False
                rally_count = 0
                rally_low = today['low']
            elif len(active_ddays) >= dday_exit:
                in_uptrend = False
                ftd_low = np.nan
                active_ddays = []
                rally_active = False
                rally_count = 0
                rally_low = today['low']

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


            if not ftd_day:
                if (today['high'] > yesterday['high'] > two_days_ago['high']) \
                        and (today['low'] > yesterday['low'] > two_days_ago['low']):
                    ftd_low = min(today['low'], yesterday['low'], two_days_ago['low'])
                    in_uptrend = True
                    active_ddays = []
                    rally_active = False
                    rally_count = 0


        df.loc[dt, 'ftd_low'] = ftd_low
        df.loc[dt, 'in_uptrend'] = in_uptrend
        df.loc[dt, 'dday_count'] = len(active_ddays)

    return df

def first_true_ts(s: pd.Series):
    """Return timestamp of first True in a boolean Series, else NaT."""
    return s.index[s].min() if s.any() else pd.NaT

def print_report(ticker, trades, daily, strategy, frequency = 'daily'):
    """Print comprehensive backtest results."""

    trading_periods = 252 if frequency == 'daily' else 52

    if trades.empty:
        print("No trades generated.")
        return

    print("=" * 70)
    print(f"{ticker} SWING TRADING BACKTEST RESULTS")
    print(strategy)
    print("=" * 70)

    # --- Portfolio summary ---
    start_val = daily['portfolio_value'].iloc[0]
    end_val = daily['portfolio_value'].iloc[-1]
    total_return = (end_val - start_val) / start_val
    start_date = daily.iloc[0].name
    end_date = daily.iloc[-1].name
    years = len(daily) / trading_periods

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

    # Calculate daily returns from portfolio value
    daily_returns = daily['portfolio_value'].pct_change().dropna()
    daily_in_trade = daily['in_trade'][-(len(daily_returns)):]
    invested_returns = daily_returns[daily_in_trade]
    trading_days = 252
    risk_free_rate = 0.04

    # Daily risk-free rate
    rf_daily = (1 + risk_free_rate) ** (1 / trading_days) - 1
    excess_returns = daily_returns - rf_daily
    invested_excess_returns = invested_returns - rf_daily

    # SHARPE RATIO
    sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(trading_periods)
    sharpe_invested = (invested_returns.mean() / invested_returns.std()) * np.sqrt(trading_periods)

    # SORTINO RATIO (only penalizes downside volatility)
    downside_returns = excess_returns[excess_returns < 0]
    downside_std = np.sqrt((downside_returns ** 2).mean())
    invested_downside_returns = invested_excess_returns[invested_excess_returns < 0]
    invested_downside_std = np.sqrt((np.minimum(invested_excess_returns, 0) ** 2).mean())
    sortino = (excess_returns.mean() / downside_std) * np.sqrt(trading_periods)
    sortino_invested = (invested_excess_returns.mean() / invested_downside_std) * np.sqrt(trading_periods)

    # CALMAR RATIO (CAGR / max drawdown)
    calmar = abs(cagr / max_dd) if max_dd != 0 else float('inf')

    # OMEGA RATIO (probability-weighted gains over losses vs threshold)
    threshold_daily = rf_daily
    gains = excess_returns[excess_returns > 0].sum()
    losses = abs(excess_returns[excess_returns < 0].sum())
    omega = gains / losses if losses != 0 else float('inf')

    invested_gains = invested_excess_returns[invested_excess_returns > 0].sum()
    invested_losses = abs(invested_excess_returns[invested_excess_returns < 0].sum())
    omega_invested = invested_gains / invested_losses

    print(f"\nPeriod:            {start_date} to {end_date} ({years:.1f} years)")
    print(f"Ticker:              {ticker}")
    print(f"Frequency:           {frequency}")
    print(f"Starting capital:    ${start_val:,.0f}")
    print(f"Ending capital:      ${end_val:,.0f}")
    print(f"Total return:        {total_return:+.1%}")
    print(f"CAGR:                {cagr:+.1%}")
    print(f"Sharpe ratio:        {sharpe:.2f}")
    print(f"Sortino ratio:       {sortino:.2f}")
    print(f"Calmar ratio:        {calmar:.2f}")
    print(f"Omega ratio:         {omega:.2f}")
    print(f"Sharpe Invested:     {sharpe_invested:.2f}")
    print(f"Sortino Invested:    {sortino_invested:.2f}")
    print(f"Omega Invested:      {omega_invested:.2f}")
    print(f"Max drawdown:        {max_dd:.1%} (on {max_dd_date})")
    print(f"Time in market:      {pct_in_market:.1%}")

    # --- Buy & hold comparison ---
    start = daily['close'].iloc[0]
    end = daily['close'].iloc[-1]
    bh_return = (end - start) / start
    bh_cagr = (end / start) ** (1 / years) - 1 if years > 0 else 0

    print(f"\n--- Buy & Hold {ticker} Comparison ---")
    print(f"{ticker} B&H return:     {bh_return:+.1%}")
    print(f"{ticker} B&H CAGR:       {bh_cagr:+.1%}")

    # --- Trade statistics ---
    trades_ = trades.to_dict('records')
    n_trades = len(trades)
    # Exclude end_of_data trade from win/loss stats if still open
    closed_trades = [t for t in trades_ if t['exit_reason'] != 'end_of_data']
    n_closed = len(closed_trades)

    winners = [t for t in closed_trades if t['pnl'] > 0]
    losers = [t for t in closed_trades if t['pnl'] <= 0]
    n_win = len(winners)
    n_loss = len(losers)
    win_rate = n_win / n_closed if n_closed > 0 else 0

    avg_win = np.mean([t['pnl_pct'] for t in winners]) if winners else 0
    avg_loss = np.mean([t['pnl_pct'] for t in losers]) if losers else 0
    avg_hold_win = np.mean([t['holding_period'] for t in winners]) if winners else 0
    avg_hold_loss = np.mean([t['holding_period'] for t in losers]) if losers else 0

    largest_win = max([t['pnl_pct'] for t in winners]) if winners else 0
    largest_loss = min([t['pnl_pct'] for t in losers]) if losers else 0

    total_pnl = sum(t['pnl'] for t in closed_trades)
    gross_wins = sum(t['pnl'] for t in winners) if winners else 0
    gross_losses = sum(t['pnl'] for t in losers) if losers else 0
    profit_factor = abs(gross_wins / gross_losses) if gross_losses != 0 else float('inf')

    avg_peak = np.mean([t['peak_gain_pct'] for t in closed_trades]) if closed_trades else 0
    avg_dd = np.mean([t['max_drawdown_pct'] for t in closed_trades]) if closed_trades else 0

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
        r = t['exit_reason']
        if r not in reasons:
            reasons[r] = {'count': 0, 'total_pnl': 0.0}
        reasons[r]['count'] += 1
        reasons[r]['total_pnl'] += t['pnl']
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
    print(f"{'Entry':>20s} {'Exit':>26s} {'Entry$':>18s} {'Exit$':>12s} {'Return':>12s} {'Days':>10s}  {'Reason':>10s}")
    print("-" * 125)
    for t in trades_:
        print(f"{t['entry_dt']}{'':>8s} {t['exit_dt']}{'':>12s}${t['entry_px']:>6.2f}      ${t['exit_px']:>6.2f}      {t['pnl_pct']:>+7.1%}      {t['holding_period']:>5d}       {t['exit_reason']}")


    print("=" * 125)

    portfolio_stats = {
        'Period': f'{start_date} to {end_date} ({years:.1f} years)',
        'Frequency': f'{frequency}',
        'Ticker': f'{ticker}',
        'Starting capital': f'${start_val:,.0f}',
        'Ending capital': f'${end_val:,.0f}',
        'Total return': f'{total_return:+.1%}',
        'CAGR': f'{cagr:+.1%}',
        'Sharpe ratio': f'{sharpe:.2f}',
        'Sortino ratio': f'{sortino:.2f}',
        'Calmar ratio': f'{calmar:.2f}',
        'Omega ratio': f'{omega:.2f}',
        'Sharpe Invested': f'{sharpe_invested:.2f}',
        'Sortino Invested': f'{sortino_invested:.2f}',
        'Omega Invested': f'{omega_invested:.2f}',
        'Max drawdown': f'{max_dd:.1%} (on {max_dd_date})',
        'Time in market': f'{pct_in_market:.1%}'
    }
    trade_stats = {
        'Frequency': frequency,
        'Closed_trades': f'{n_closed}',
        'Total trades':  f'{n_trades}',
        'Win rate': f'{win_rate:.1%}',
        'Wins': f'{n_win}',
        'Losses': f'{n_loss}',
        'Avg winner': f'{avg_win:+.1%}',
        'Avg Hold Time Winner': f'{avg_hold_win:.0f}',
        'Avg loser': f'{avg_loss:+.1%}',
        'Avg Hold Time Loser': f'{avg_hold_loss:.0f}',
        'Largest winner': f'{largest_win:+.1%}',
        'Largest loser': f'{largest_loss:+.1%}',
        'Profit factor': f'{profit_factor:.2f}',
        'Avg peak gain': f'{avg_peak:+.1%}',
        'Avg max drawdown': f'{avg_dd:.1%}',
        'Total P&L': f'${total_pnl:+,.0f}'
    }

    return pd.Series(portfolio_stats), pd.Series(trade_stats)