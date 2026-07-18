import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ── Trade log data from backtest ──
# (return_pct, holding_days)
def holding_scatter(trades):

    returns  = (trades['pnl_pct'] * 100).tolist()
    days     = trades['holding_period'].tolist()

    trades = list(zip(returns, days))

    # returns = [t[0] for t in trades]
    # days    = [t[1] for t in trades]
    colors  = ['#00d4aa' if r >= 0 else '#ff4466' for r in returns]
    sizes   = [abs(r) * 3 + 40 for r in returns]  # bubble size by magnitude

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

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.scatter(days, returns, c=colors, s=sizes, alpha=0.8, edgecolors='white', linewidths=0.5, zorder=5)

    # ── Label the two monster trades ──
    for d, r in trades:
        if r > 100:
            ax.annotate(f'+{r:.0f}%\n({d}d)', xy=(d, r),
                        xytext=(d + 12, r - 20),
                        fontsize=9, color='#00d4aa',
                        arrowprops=dict(arrowstyle='->', color='#00d4aa', lw=1))

    # ── Reference lines ──
    ax.axhline(0, color='#666688', linewidth=0.8)
    ax.axhline(-10, color='#ff4466', linewidth=0.8, linestyle='--', alpha=0.5, label='Hard stop (−10%)')

    # ── Formatting ──
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:+.0f}%'))
    ax.set_xlabel('Holding Period (days)')
    ax.set_ylabel('Trade Return')
    ax.set_title('QQQ / TQQQ Trade Distribution — Return vs. Holding Period',
                 fontsize=14, fontweight='bold', pad=15)
    ax.grid(True, linewidth=0.5)
    ax.legend(loc='lower right', framealpha=0.3, fontsize=9)

    # ── Quadrant annotations ──
    ax.text(0.97, 0.97, 'Winners hold longer,\nlosers cut fast',
            transform=ax.transAxes, fontsize=9, color='#aaaacc',
            ha='right', va='top', style='italic', alpha=0.7)

    plt.tight_layout()
    plt.show()
    # fig.savefig('/home/claude/charts/chart6_trade_scatter.png', dpi=200, bbox_inches='tight')
    # plt.close()
    # print('Done: chart6_trade_scatter.png')

if __name__ == '__main__':
    trades = pd.read_csv(r'D:\test_data\petrou\trades_TQQQ.csv', parse_dates=['entry_date', 'exit_date'])
    holding_scatter(trades)