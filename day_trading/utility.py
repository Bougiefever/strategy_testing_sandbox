import pandas as pd
import numpy as np

def _align_series(nlv, cash=None, margin=None):
    nlv = nlv.sort_index().astype(float).dropna()
    idx = nlv.index
    out = {"nlv": nlv}
    if cash is not None:
        out["cash"] = cash.sort_index().reindex(idx).ffill().astype(float)
    if margin is not None:
        out["margin"] = margin.sort_index().reindex(idx).ffill().astype(float)
    return out

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
        start = pd.to_datetime(r["entry_date"]).normalize()
        end = pd.to_datetime(r["exit_date"]).normalize()
        if start in in_pos.index or end in in_pos.index:
            in_pos.loc[start:end] = True
    return float(in_pos.mean() * 100.0)


def trade_stats(trades: pd.DataFrame) -> pd.Series:
    t = trades.copy()

    if "net_pnl" not in t.columns:
        t["net_pnl"] = t["pnl"] - t.get("fees", 0.0)

    t["duration_minutes"] = (t["exit_dt"] - t["entry_dt"]).dt.total_seconds() / 60.0

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
        "Avg Winning Duration [minutes]": float(wins["duration_minutes"].mean()) if len(wins) else np.nan,
        "Avg Losing Duration [minutes]": float(losses["duration_minutes"].mean()) if len(losses) else np.nan,
        "Total Fees Paid": float(t.get("fees", 0.0).sum()) if "fees" in t.columns else 0.0,
    }
    return pd.Series(out)

def portfolio_stats_options(nlv: pd.Series, trades: pd.DataFrame,
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
    invested_returns = daily_returns[daily['in_trade']]
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

    # avg_peak = np.mean([t['peak_gain_pct'] for t in closed_trades]) if closed_trades else 0
    # avg_dd = np.mean([t['max_drawdown_pct'] for t in closed_trades]) if closed_trades else 0

    print(f"\n--- Trade Statistics ({n_closed} closed trades) ---")
    print(f"Total trades:        {n_trades} ({n_closed} closed, "
          f"{'1 open' if n_trades > n_closed else '0 open'})")
    print(f"Win rate:            {win_rate:.1%} ({n_win}W / {n_loss}L)")
    print(f"Avg winner:          {avg_win:+.1%} (held {avg_hold_win:.0f} days)")
    print(f"Avg loser:           {avg_loss:+.1%} (held {avg_hold_loss:.0f} days)")
    print(f"Largest winner:      {largest_win:+.1%}")
    print(f"Largest loser:       {largest_loss:+.1%}")
    print(f"Profit factor:       {profit_factor:.2f}")
    # print(f"Avg peak gain:       {avg_peak:+.1%}")
    # print(f"Avg max drawdown:    {avg_dd:.1%}")
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
    print(f"{'Entry':>12s} {'Exit':>12s} {'Entry$':>10s} {'Exit$':>10s} "
          f"{'Return':>8s} {'Days':>5s}  {'Reason'}")
    print("-" * 85)
    for t in trades_:
        print(f"{t['entry_dt']:>12s} {t['exit_dt']:>12s} "
              f"${t['entry_px']:>9.2f} ${t['exit_px']:>9.2f} "
              f"{t['pnl_pct']:>+7.1%} {t['holding_period']:>5d}  {t['exit_reason']}")

    print("=" * 70)

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
        # 'Avg peak gain': f'{avg_peak:+.1%}',
        # 'Avg max drawdown': f'{avg_dd:.1%}',
        'Total P&L': f'${total_pnl:+,.0f}'
    }

    return pd.Series(portfolio_stats), pd.Series(trade_stats)