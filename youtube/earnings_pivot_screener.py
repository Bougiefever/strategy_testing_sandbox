import pandas as pd
import numpy as np
import math
from pathlib import Path
import talib



daily_stock_folder = Path(r'D:\stock_data\daily_stock_prices')
calcs_folder = Path(r'D:\stock_data\calcs')
tickers = ['OPEN',	'WMB',	'SVM',	'AMKR',	'GT',	'UPWK',	'GTM',	'CHGG',	'PFG',	'ACGL',	'ICHR',	'RLGT',	'PSEC',	'MTW',	'MEDP',	'CINF',	'CRBG',	'VNO',	'BRX',	'PFLT',	'UDR',	'DAC',	'PNNT',	'SSD',	'DLHC',	'PAL',	'KRC',	'NTB',	'UTL',	'KO',	'OSCR',	'DDOG',	'SPOT',	'CVS',	'SPGI',	'DD',	'CAN',	'HOG',	'DUK',	'ENTG',	'RACE',	'MAR',	'AZN',	'INCY',	'INMD',	'GILT',	'TRMB',	'SLAB',	'SAIA',	'XYL',	'DGX',	'HAS',	'ECL',	'WCC',	'ZBH',	'OGI',	'PAX',	'ACRE',	'MAS',	'LUXE',	'ARMK',	'IRMD',	'AXTA',	'CTS',	'BLKB',	'GCMG',	'RGCO',]
for stock_fn in daily_stock_folder.iterdir():
    ticker = stock_fn.stem[:-1]
    if ticker not in tickers:
        continue
    df = pd.read_parquet(stock_fn, engine='pyarrow')
    df.set_index('quote_datetime', inplace=True)
    df.sort_index(inplace=True)

    df['100d_sma'] = talib.SMA(df['close'].to_numpy(float), timeperiod=100)
    df['100d_sma_shift'] = df['100d_sma'].shift(100)
    df['roc100'] = (df['100d_sma'] - df['100d_sma_shift']) / df['100d_sma_shift'] * 100

    roc100  = df.iloc[-1]['roc100']
    if roc100 >= -10.0:
        print(ticker, "long")
    elif roc100 < 0.0:
        print(ticker, "short")




