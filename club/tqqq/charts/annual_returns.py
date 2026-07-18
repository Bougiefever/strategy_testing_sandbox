import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ── Data from backtest ──
# years   = list(range(2010, 2027))
# returns = [37.9, -48.1, -5.9, 115.7, 73.2, -0.4, -22.8, 100.6, -4.1,
#            78.7, 62.5, 83.0, -21.3, 29.5, 41.2, 18.8, -9.2]


def annual_returns(df, title):
    df['year'] = df['date'].dt.year

    # ── Get first and last portfolio_value per year ──
    annual = df.groupby('year')['portfolio_value'].agg(['first', 'last'])
    annual['return_pct'] = (annual['last'] / annual['first'] - 1) * 100

    years = annual.index.tolist()
    returns = annual['return_pct'].values.tolist()

    colors = ['#00d4aa' if r >= 0 else '#ff4466' for r in returns]

    # ── Style ──
    plt.rcParams.update({
        'figure.facecolor': '#1a1a2e',
        'axes.facecolor':   '#1a1a2e',
        'axes.edgecolor':   '#444466',
        'text.color':       '#e0e0e0',
        'axes.labelcolor':  '#e0e0e0',
        'xtick.color':      '#aaaacc',
        'ytick.color':      '#aaaacc',
        'grid.color':       '#2a2a4a',
        'grid.alpha':       0.6,
        'font.family':      'sans-serif',
        'font.size':        11,
    })

    fig, ax = plt.subplots(figsize=(14, 6))

    bars = ax.bar(years, returns, color=colors, width=0.7, edgecolor='none')

    # ── Value labels on bars ──
    for bar, ret in zip(bars, returns):
        y = bar.get_height()
        va = 'bottom' if y >= 0 else 'top'
        offset = 2 if y >= 0 else -2
        ax.text(bar.get_x() + bar.get_width()/2, y + offset,
                f'{ret:+.0f}%', ha='center', va=va, fontsize=8.5, color='#e0e0e0')

    # ── Formatting ──
    ax.axhline(0, color='#666688', linewidth=0.8)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:+.0f}%'))
    ax.set_xticks(years)
    ax.set_xticklabels(years, rotation=45, ha='right')
    ax.set_xlabel('')
    ax.set_ylabel('Annual Return')
    ax.set_title(title,
                 fontsize=15, fontweight='bold', pad=15)
    ax.grid(True, axis='y', linewidth=0.5)

    plt.tight_layout()
    plt.show()
    # fig.savefig('/home/claude/charts/chart3_annual_returns.png', dpi=200, bbox_inches='tight')
    # plt.close()
    # print('Done: chart3_annual_returns.png')

if __name__ == '__main__':
    # ── Load data ──
    title = 'ORB 5-Min Crabel Stretch - ALL Tickers'
    fn = r'D:\test_data\day_trading\orb_buy_options\multiple\daily_1.csv'
    title = 'SPX PCS 0DTE Trade — Annual Returns'
    fn = r'D:\test_data\day_trading\spx_trade\daily_5.csv'
    df = pd.read_csv(fn, parse_dates=['date'])
    annual_returns(df, title)