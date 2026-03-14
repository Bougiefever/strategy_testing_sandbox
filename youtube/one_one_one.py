"""
1-1-1	Trading Strategy YouTube Summaries
1.	Theta Returns Interview:
https://youtu.be/d3MDIGl7TjA?si=fcY0RdS4i8EQgblj
2.	Retire with Options channel
https://youtu.be/y7Ds8jcpu28?si=wxjBMfIkq3UARi8l
3.	One Glance Trader
https://youtu.be/uSqiXx-ZXdU?si=xlePP92gh6nXxtMJ
4.	Tom King Trades
https://youtu.be/ilfZPRHwl_k?si=rwgwAKJ9SQ8eXxcH


"""
import pandas as pd
import numpy as np
from pathlib import Path
import datetime
import matplotlib.pyplot as plt
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.single import Single

ticker = 'SPY'

options_root_dir = Path(r'D:\options_data\daily')
stats_fn = options_root.joinpath(ticker, 'data', f'{ticker}_optionstats.parquet')

stats_df = pd.read_parquet(stats_fn)



