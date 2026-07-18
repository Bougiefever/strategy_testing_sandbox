import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.dates as mdates


def trade_overlay(price, macd):
    df = price.merge(macd, on='date')
    df['in_trade'] = df['in_trade'].astype(bool)

    # ── Detect entry / exit points ──
    df['trade_change'] = df['in_trade'].astype(int).diff()
    entries = df[df['trade_change'] == 1]   # False → True
    exits   = df[df['trade_change'] == -1]  # True → False

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

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1.5],
                                    sharex=True, gridspec_kw={'hspace': 0.08},
                                    layout='constrained')

    # ══════════════════════════════════════
    # Top panel: QQQ price + entry/exit markers
    # ══════════════════════════════════════
    ax1.plot(df['date'], df['base_close'], color='#7788cc', linewidth=1.2, label='QQQ Close')

    # Shade in-trade periods
    for i in range(len(df)):
        if df['in_trade'].iloc[i]:
            x0 = df['date'].iloc[max(0, i-1)]
            x1 = df['date'].iloc[i]
            ax1.axvspan(x0, x1, color='#00d4aa', alpha=0.08)

    # Entry / exit markers
    ax1.scatter(entries['date'], entries['base_close'], marker='^', color='#00d4aa',
                s=80, zorder=5, label='Entry')
    ax1.scatter(exits['date'], exits['base_close'], marker='v', color='#ff4466',
                s=80, zorder=5, label='Exit')

    ax1.set_ylabel('QQQ Price')
    ax1.set_title('QQQ Weekly MACD — Entry / Exit Signals Overlaid on Price',
                  fontsize=14, fontweight='bold', pad=12)
    ax1.legend(loc='upper left', framealpha=0.3, fontsize=9)
    ax1.grid(True, linewidth=0.5)

    # ══════════════════════════════════════
    # Bottom panel: MACD histogram
    # ══════════════════════════════════════
    macd_hist = df['base_macd'] - df['base_macd_signal']
    hist_colors = ['#00d4aa' if v >= 0 else '#ff4466' for v in macd_hist]

    ax2.bar(df['date'], macd_hist, color=hist_colors, width=5, alpha=0.6)
    ax2.plot(df['date'], df['base_macd'], color='#00aaff', linewidth=1.2, label='MACD')
    ax2.plot(df['date'], df['base_macd_signal'], color='#ffaa33', linewidth=1.0, label='Signal')
    ax2.axhline(0, color='#888888', linewidth=0.8)

    ax2.set_ylabel('MACD')
    ax2.legend(loc='upper left', framealpha=0.3, fontsize=9)
    ax2.grid(True, linewidth=0.5)

    # ── Shared x-axis formatting ──
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))

    plt.show()
    # fig.savefig('/home/claude/charts/chart5_macd_overlay.png', dpi=200, bbox_inches='tight')
    # plt.close()
    # print('Done: chart5_macd_overlay.png')

if __name__ == "__main__":
    # ── Load data ──
    price = pd.read_csv(r'D:\test_data\petrou\daily_QQQ_TQQQ.csv', parse_dates=['date'])
    macd = pd.read_csv(r'D:\test_data\petrou\base_record_QQQ.csv', parse_dates=['date'])

    trade_overlay(price, macd)