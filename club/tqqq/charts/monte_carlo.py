import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import argparse

def monte_carlo(returns: pd.Series, num_tests: int = 100, starting_equity: float = 10000):
    """
    returns: pd.Series of pct_change values (NaNs will be dropped)
    num_tests: how many shuffled simulations to run
    starting_equity: beginning portfolio value
    """
    returns = returns.dropna().values

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.set_facecolor("black")
    ax.set_facecolor("black")

    for i in range(num_tests):
        shuffled = np.random.permutation(returns)
        equity_curve = starting_equity * np.cumprod(1 + shuffled)
        equity_curve = np.insert(equity_curve, 0, starting_equity)
        ax.plot(equity_curve, linewidth=0.6, alpha=0.4)

    ax.set_xlabel("Trade #", color="white", fontsize=11)
    ax.set_ylabel("Equity ($)", color="white", fontsize=11)
    ax.set_title(f"Monte Carlo Simulation — {num_tests} Tests", color="white", fontsize=13)
    plt.tight_layout()
    plt.show()

def risk_of_ruin(returns: pd.Series, num_tests: int = 10000, starting_equity: float = 10000,
                 ruin_levels: list = None):
    """
    ruin_levels: list of drawdown percentages to test, e.g. [10, 20, 30, ...]
                 meaning 'equity drops 10% from start', '20% from start', etc.
    """
    if ruin_levels is None:
        ruin_levels = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

    returns = returns.dropna().values
    ruin_thresholds = {level: starting_equity * (1 - level / 100) for level in ruin_levels}
    ruin_counts = {level: 0 for level in ruin_levels}

    for _ in range(num_tests):
        shuffled = np.random.permutation(returns)
        equity_curve = starting_equity * np.cumprod(1 + shuffled)

        min_equity = equity_curve.min()

        for level in ruin_levels:
            if min_equity <= ruin_thresholds[level]:
                ruin_counts[level] += 1

    # build results
    results = {level: ruin_counts[level] / num_tests * 100 for level in ruin_levels}

    # print table
    print(f"\nRisk of Ruin — {num_tests:,} simulations\n" + "-" * 35)
    for level in ruin_levels:
        print(f"  {level:>3}% drawdown:  {results[level]:>6.2f}% chance")

    # plot
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(ruin_levels, [results[l] for l in ruin_levels], width=6, color="crimson", alpha=0.8)
    bars = ax.bar(ruin_levels, [results[l] for l in ruin_levels], width=6, color="crimson", alpha=0.8)

    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, height + 0.5,
                f"{height:.1f}%", ha="center", va="bottom", fontsize=9, color="white")
    ax.set_xlabel("Portfolio Drawdown %")
    ax.set_ylabel("Probability %")
    ax.set_title(f"Risk of Ruin — {num_tests:,} Simulations")
    ax.set_xticks(ruin_levels)
    ax.set_xticklabels([f"{l}%" for l in ruin_levels])
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    # title = 'ORB 5-Min Crabel Stretch - ALL Tickers'
    # fn = r'D:\test_data\day_trading\orb_buy_options\multiple\daily_1.csv'
    title = 'SPX PCS 0DTE Trade — Monte Carlo Simulation'
    fn = r'D:\test_data\day_trading\spx_trade\daily_6.csv'
    df = pd.read_csv(fn, parse_dates=['date'])
    returns = df["portfolio_value"].pct_change()
    num_simulations = 1000
    monte_carlo(returns, num_tests=num_simulations)
    risk_of_ruin(returns, num_tests=num_simulations)
