import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.dates as mdates


def drawdown(df, title):
    # ── Compute drawdown ──
    running_max = df['portfolio_value'].cummax()
    drawdown = (df['portfolio_value'] - running_max) / running_max * 100  # as pct

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

    fig, ax = plt.subplots(figsize=(14, 5))

    # ── Fill drawdown area ──
    ax.fill_between(df['date'], drawdown, 0, color='#ff4466', alpha=0.35)
    ax.plot(df['date'], drawdown, color='#ff4466', linewidth=1.2)

    # ── Mark max drawdown ──
    worst_idx = drawdown.idxmin()
    worst_date = df['date'].iloc[worst_idx]
    worst_dd = drawdown.iloc[worst_idx]
    ax.annotate(f'Max DD: {worst_dd:.1f}%',
                xy=(worst_date, worst_dd),
                xytext=(worst_date + pd.Timedelta(days=180), worst_dd + 5),
                fontsize=10, color='#f2fa05', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#f2fa05', lw=1.5))

    # ── Formatting ──
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:.0f}%'))
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.set_xlabel('')
    ax.set_ylabel('Drawdown')
    ax.set_title(title, fontsize=15, fontweight='bold', pad=15)
    ax.grid(True, axis='both', linewidth=0.5)
    ax.set_ylim(bottom=min(drawdown) - 5, top=5)
    ax.axhline(0, color='#666688', linewidth=0.8)

    plt.tight_layout()
    plt.show()
    pass
    # fig.savefig('/home/claude/charts/chart2_drawdown.png', dpi=200, bbox_inches='tight')
    # plt.close()
    # print('Done: chart2_drawdown.png')

if __name__ == '__main__':
    # ── Load data ──
    # title = 'ORB 5-Min Crabel Stretch - ALL Tickers'
    # fn = r'D:\test_data\day_trading\orb_buy_options\multiple\daily_1.csv'
    title = 'SPX PCS 0DTE Trade — Drawdown'
    fn = r'D:\test_data\day_trading\spx_trade\daily_6.csv'
    df = pd.read_csv(fn, parse_dates=['date'])
    drawdown(df, title)