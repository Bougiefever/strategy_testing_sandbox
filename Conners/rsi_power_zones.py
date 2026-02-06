from __future__ import annotations

import datetime
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.vertical import Vertical
from options_framework.config import settings
import pandas as pd
import talib
import numpy as np
import vectorbtpro as vbt

from pathlib import Path

options_root = Path(settings['options_directory'], 'daily')
stock_root = Path(settings['stock_data_files'])

ticker = 'SPY'
rsi_period = 4
rsi_limit = 30
exit_limit = 55
entry_size = 0.10
starting_cash = 100_000
credit_spread_width = 5
delta = 0.30

stock_file = stock_root.joinpath(f'{ticker}_.parquet')

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



if __name__ == '__main__':

    df = pd.read_parquet(stock_file, columns=['symbol', 'quote_datetime', 'open', 'high', 'low', 'close', 'volume'],
                         engine='pyarrow')
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float).where(df[col] > 0, np.nan)
    df = df.dropna(subset=["open", "high", "low", "close"]).copy()

    df.set_index('quote_datetime', inplace=True)
    df['rsi'] = talib.RSI(df['close'].to_numpy(), timeperiod=rsi_period)
    df['ma_200'] = talib.MA(df['close'].to_numpy(), timeperiod=200)

    df = df.dropna(subset=["rsi", "ma_200"]).copy()

    df['entry'] = (df['rsi'] <= rsi_limit) & (df['rsi'].shift(1) > rsi_limit) & (df['close'] > df['ma_200'])
    df['exit'] = (df['rsi'] >= exit_limit) & (df['rsi'].shift(1) < exit_limit)

    # start_date = datetime.datetime(2024, 1, 1)
    # end_date = datetime.datetime(2026, 1, 31)
    #
    # df = df[df.index >= start_date]
    # df = df[df.index <= end_date]

    portfolio = OptionPortfolio(cash=starting_cash, start_date=df.index.min().to_pydatetime(),
                                end_date=df.index.max().to_pydatetime())

    for dt, row in df.iterrows():
        dt = dt.to_pydatetime()
        print(dt, portfolio.current_value)
        portfolio.next(dt, 'SPY', portfolio.cash, portfolio.portfolio_margin_allocation)
        rsi = row['rsi']
        ma_200 = row['ma_200']
        entry = row['entry']

        if len(portfolio.positions) > 0:
            debit_spread = portfolio.positions[0]
            pnl = debit_spread.get_profit_loss_percent()
            dte = debit_spread.get_dte()
            if pnl >= 0.25 or pnl <= -0.5 or dte < 8:
                portfolio.close_position(debit_spread.instance_id)
                print(debit_spread, debit_spread.get_profit_loss())


        if entry and len(portfolio.positions) == 0:
            buy_next = False
            option_chain = portfolio.option_chains['SPY']

            expiration_target = dt + datetime.timedelta(days=21)
            expiration = min(option_chain.expirations, key=lambda x: abs((x - expiration_target.date()).days))
            # if abs(expiration - expiration_target.date()).days > 5:
            #     continue

            options = [x for x in option_chain.options.copy() if x['option_type'] == 'call' and x['expiration'] == expiration]

            deltas = [abs(x['delta']) for x in options if x['option_type'] == 'call']
            long_delta = min(deltas, key=lambda x: abs(x - 0.65))
            call_data = next(x for x in options if x['option_type'] == 'call' and x['delta'] == long_delta)
            long_strike = call_data['strike']
            short_delta = min(deltas, key=lambda x: abs(x - 0.40))
            call_data = next(x for x in options if x['option_type'] == 'call' and x['delta'] == short_delta)
            short_strike = call_data['strike']
            if long_strike >= short_strike:
                continue

            debit_spread = Vertical.create(option_chain=option_chain, expiration=expiration, option_type = 'call', short_strike=short_strike, long_strike=long_strike)
            portfolio.open_position(option_spread=debit_spread, quantity=1)
            print(debit_spread)


    portfolio_running_values = portfolio.close_values
    dates = [x[0] for x in portfolio_running_values]
    nlv = pd.Series([x[1] for x in portfolio_running_values], index=dates, name='nlv')
    cash = pd.Series([x[2] for x in portfolio_running_values], index=dates, name='cash')
    margin = pd.Series([x[3] for x in portfolio_running_values], index=dates, name='margin')

    trades_data = [[o.get_open_datetime(), o.get_close_datetime(), o.get_profit_loss(), o.get_trade_premium(), o.get_fees()] for o in
                   portfolio.closed_positions]
    trades_index = [o.instance_id for o in portfolio.closed_positions]
    trades_df = pd.DataFrame(data=trades_data, index=trades_index,
                             columns=['entry_date', 'exit_date', 'pnl', 'capital_at_risk', 'fees'])
    output = portfolio_stats_options(nlv, trades_df, cash, margin)
    print(output)
