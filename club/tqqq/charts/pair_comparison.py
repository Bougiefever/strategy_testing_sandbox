import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ── Data from backtest results ──
pairs = ['QQQ/\nTQQQ', 'SPY/\nUPRO', 'XLK/\nTECL', 'SMH/\nSOXL',
         'XLF/\nFAS', 'XLE/\nERX', 'IBB/\nLABU', 'GDX/\nNUGT']

cagr   = [24.3, 23.8, 32.8, 25.7,  13.6,  3.1,  -2.9, -6.5]
sharpe = [1.22, 1.29, 1.41, 1.68,  None,  None,  None, None]
pf     = [3.87, 5.38, 5.27, 2.62,  2.02,  1.02,  0.58, 0.48]

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

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

x = np.arange(len(pairs))

# ── Left panel: CAGR ──
bar_colors = ['#00d4aa' if c >= 10 else '#ffaa33' if c >= 0 else '#ff4466' for c in cagr]
bars1 = ax1.bar(x, cagr, color=bar_colors, width=0.6)
for bar, c in zip(bars1, cagr):
    y = bar.get_height()
    va = 'bottom' if y >= 0 else 'top'
    offset = 0.8 if y >= 0 else -0.8
    ax1.text(bar.get_x() + bar.get_width()/2, y + offset,
             f'{c:+.1f}%', ha='center', va=va, fontsize=9, color='#e0e0e0')
ax1.axhline(0, color='#666688', linewidth=0.8)
ax1.set_xticks(x)
ax1.set_xticklabels(pairs, fontsize=9)
ax1.set_ylabel('CAGR (%)')
ax1.set_title('CAGR by ETF Pair', fontsize=13, fontweight='bold')
ax1.grid(True, axis='y', linewidth=0.5)

# ── Right panel: Profit Factor ──
pf_colors = ['#00d4aa' if p >= 2.0 else '#ffaa33' if p >= 1.0 else '#ff4466' for p in pf]
bars2 = ax2.bar(x, pf, color=pf_colors, width=0.6)
for bar, p in zip(bars2, pf):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.08,
             f'{p:.2f}', ha='center', va='bottom', fontsize=9, color='#e0e0e0')
ax2.axhline(1.0, color='#ffaa33', linewidth=1.0, linestyle='--', alpha=0.6, label='Breakeven')
ax2.set_xticks(x)
ax2.set_xticklabels(pairs, fontsize=9)
ax2.set_ylabel('Profit Factor')
ax2.set_title('Profit Factor by ETF Pair', fontsize=13, fontweight='bold')
ax2.grid(True, axis='y', linewidth=0.5)
ax2.legend(loc='upper right', framealpha=0.3, fontsize=9)

fig.suptitle('Which ETF Pairs Work (and Which Don\'t)',
             fontsize=15, fontweight='bold', y=1.02, color='#e0e0e0')

plt.tight_layout()
plt.show()
# fig.savefig('/home/claude/charts/chart4_pair_comparison.png', dpi=200, bbox_inches='tight')
# plt.close()
# print('Done: chart4_pair_comparison.png')