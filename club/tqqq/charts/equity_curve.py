import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.dates as mdates


def equity_curve(df, title):
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

    # ── Shade in-trade periods ──
    in_trade = df['in_trade'].astype(bool)
    for i in range(len(df)):
        if in_trade.iloc[i]:
            x0 = df['date'].iloc[max(0, i-1)]
            x1 = df['date'].iloc[i]
            ax.axvspan(x0, x1, color='#00d4aa', alpha=0.07)

    # ── Portfolio value line ──
    ax.plot(df['date'], df['portfolio_value'], color='#00d4aa', linewidth=1.8, label='Portfolio Value')

    # ── Formatting ──
    ax.set_yscale('log')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.set_xlabel('')
    ax.set_ylabel('Portfolio Value (log scale)')
    ax.set_title(title, fontsize=15, fontweight='bold', pad=15)
    ax.grid(True, axis='both', linewidth=0.5)
    ax.legend(loc='upper left', framealpha=0.3)

    # ── Annotate start / end ──
    start_val = df['portfolio_value'].iloc[0]
    end_val   = df['portfolio_value'].iloc[-1]
    ax.annotate(f'${start_val:,.0f}', xy=(df['date'].iloc[0], start_val),
                fontsize=9, color='#aaaacc', ha='left', va='bottom')
    ax.annotate(f'${end_val:,.0f}', xy=(df['date'].iloc[-1], end_val),
                fontsize=9, color='#00d4aa', ha='right', va='bottom')

    plt.tight_layout()
    plt.show()


    # fig.savefig('/home/claude/charts/chart1_equity_curve.png', dpi=200, bbox_inches='tight')
    # plt.close()
    # print('Done: chart1_equity_curve.png')

if __name__ == "__main__":
    # ── Load data ──
    #fn = r'D:\test_data\petrou\daily_QQQ_TQQQ.csv'
    #title = 'QQQ / TQQQ Weekly MACD Strategy — Equity Curve'
    fn = r'D:\test_data\day_trading\spx_trade\daily_6.csv'
    title = 'SPX PCS 0DTE Trade — Equity Curve'
    df = pd.read_csv(fn, parse_dates=['date'])
    equity_curve(df, title)