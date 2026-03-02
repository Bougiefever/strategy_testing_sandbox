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
        start = pd.to_datetime(r["entry_dt"]).normalize()
        end = pd.to_datetime(r["exit_dt"]).normalize()
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

def perf_metrics(
    equity: pd.Series,                 # daily portfolio value (EOD), indexed by date
    periods_per_year: int = 252,        # 252 trading days
    rf_annual: float = 0.0,             # annual risk-free rate (e.g., 0.04)
    mar_annual: float = 0.0,            # minimum acceptable return for Sortino (annual)
    omega_threshold_annual: float = 0.0 # threshold for Omega (annual)
) -> dict:
    equity = equity.dropna().astype(float)
    if len(equity) < 2:
        raise ValueError("Need at least 2 equity points.")

    # Daily returns
    r = equity.pct_change().dropna()

    # Convert annual rates to per-period (daily) rates
    rf = (1 + rf_annual) ** (1 / periods_per_year) - 1
    mar = (1 + mar_annual) ** (1 / periods_per_year) - 1
    thr = (1 + omega_threshold_annual) ** (1 / periods_per_year) - 1

    # Total return
    total_return = equity.iloc[-1] / equity.iloc[0] - 1

    # CAGR (use calendar time between first/last date)
    days = (equity.index[-1] - equity.index[0]).days
    years = days / 365.25 if days > 0 else (len(equity) / periods_per_year)
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan

    # Drawdowns
    running_max = equity.cummax()
    dd = equity / running_max - 1
    max_dd = dd.min()  # negative number

    # Max drawdown duration (in trading days, since equity index is trading days)
    # Duration = longest stretch without reaching a new high
    is_new_high = equity.eq(running_max)
    grp = is_new_high.cumsum()
    # each group starts at a new high; underwater days are group_size - 1
    grp_sizes = equity.groupby(grp).size()
    max_dd_duration_days = int((grp_sizes - 1).max())

    # Excess returns
    excess = r - rf

    # Sharpe (annualized)
    sharpe = np.nan
    if excess.std(ddof=1) > 0:
        sharpe = (excess.mean() / excess.std(ddof=1)) * np.sqrt(periods_per_year)

    # Sortino (annualized): downside deviation vs MAR
    # downside only counts returns below MAR
    downside = (r - mar).clip(upper=0)
    downside_dev = downside.std(ddof=1)
    sortino = np.nan
    if downside_dev > 0:
        sortino = ((r.mean() - mar) / downside_dev) * np.sqrt(periods_per_year)

    # Calmar = CAGR / |MaxDD|
    calmar = np.nan
    if max_dd < 0:
        calmar = cagr / abs(max_dd)

    # Omega ratio relative to threshold
    # Omega = sum(max(r - thr, 0)) / sum(max(thr - r, 0))
    gains = (r - thr).clip(lower=0).sum()
    losses = (thr - r).clip(lower=0).sum()
    omega = np.nan
    if losses > 0:
        omega = gains / losses

    return {
        "Total Return %": total_return * 100,
        "CAGR %": cagr * 100,
        "Max Drawdown %": max_dd * 100,
        "Max Drawdown Duration (days)": max_dd_duration_days,
        "Sharpe Ratio": sharpe,
        "Sortino Ratio": sortino,
        "Calmar Ratio": calmar,
        "Omega Ratio": omega,
    }

def daily_portfolio_from_trades(
    prices_1m: pd.DataFrame,
    trades: pd.DataFrame,
    initial_cash: float,
    price_col: str = "close",
    entry_dt_col: str = "entry_dt",
    exit_dt_col: str = "exit_dt",
    entry_px_col: str = "entry_px",
    exit_px_col: str = "exit_px",
    shares_col: str = "shares",
    commission_per_trade: float = 0.0,   # optional
):
    """
    Returns a daily DataFrame indexed by trading date with:
      close, shares_eod, position_value, cash_eod, total_value, equity_used

    Assumptions:
      - prices_1m index is datetime-like (UTC or local, consistent with trades)
      - trades contains entry/exit datetimes + executed prices + shares
      - long-only shares (positive). For shorts you'd extend sign logic.
    """

    # --- 1) Daily close from 1-minute data (trading days only) ---
    px = prices_1m.copy()
    if not isinstance(px.index, pd.DatetimeIndex):
        px.index = pd.to_datetime(px.index)

    daily_close = (
        px[price_col]
        .resample("1D")
        .last()
        .dropna()
    )
    daily_idx = daily_close.index.normalize()

    # --- 2) Build cash/share "events" from trades (2 rows per trade) ---
    t = trades.copy()
    for c in [entry_dt_col, exit_dt_col]:
        t[c] = pd.to_datetime(t[c])

    # Entry event: buy shares, spend cash
    entry_events = pd.DataFrame({
        "ts": t[entry_dt_col],
        "shares_delta":  t[shares_col].astype(float),
        "cash_delta":   -(t[shares_col].astype(float) * t[entry_px_col].astype(float)),
    })

    # Exit event: sell shares, receive cash
    exit_events = pd.DataFrame({
        "ts": t[exit_dt_col],
        "shares_delta": -t[shares_col].astype(float),
        "cash_delta":    (t[shares_col].astype(float) * t[exit_px_col].astype(float)),
    })

    events = pd.concat([entry_events, exit_events], ignore_index=True)

    # Optional: subtract commissions (apply once on entry + once on exit)
    if commission_per_trade:
        # 2 events per trade -> charge commission per event if you want:
        events["cash_delta"] -= commission_per_trade

    # Aggregate events by day
    events["date"] = events["ts"].dt.normalize()
    events_daily = (
        events.groupby("date", as_index=True)[["shares_delta", "cash_delta"]]
        .sum()
        .reindex(daily_idx, fill_value=0.0)
    )

    # --- 3) EOD shares + cash via cumulative sums (vectorized) ---
    shares_eod = events_daily["shares_delta"].cumsum()
    cash_eod   = initial_cash + events_daily["cash_delta"].cumsum()

    # --- 4) Mark-to-market at EOD close ---
    position_value = shares_eod.values * daily_close.reindex(daily_idx).values
    total_value    = cash_eod.values + position_value

    out = pd.DataFrame({
        "close": daily_close.reindex(daily_idx).values,
        "shares_eod": shares_eod.values,
        "position_value": position_value,
        "cash_eod": cash_eod.values,
        "total_value": total_value,
    }, index=daily_idx)

    # “How much equity I'm using” (for a long-only cash account)
    # You can define this as market value of open position.
    out["equity_used"] = out["position_value"].clip(lower=0)

    # Optional: percent invested
    out["pct_invested"] = np.where(out["total_value"] != 0, out["equity_used"] / out["total_value"], np.nan)

    return out