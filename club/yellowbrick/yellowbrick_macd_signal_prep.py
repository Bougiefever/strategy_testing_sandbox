from datetime import datetime, timedelta
from pathlib import Path
import talib
from club.yellowbrick.utility import *

stock_data = Path(r'D:\stock_data\daily')
yb_signals_fn = Path(r'D:\projects\club\Yellowbrick\yb_data_dates.csv')
df_yb = pd.read_csv(yb_signals_fn, parse_dates=['pitch_date'])
df_yb = df_yb[['pitch_date', 'ticker', 'sentiment']]
df_yb.set_index('pitch_date', inplace=True)
df_yb.sort_index(inplace=True)

start_date = datetime(2024, 1,1)
end_date = datetime(2026,6,1)
num_days = (end_date - start_date).days
date_list = [(start_date + timedelta(days=x)).date() for x in range(num_days)]

signals = []
for dt in date_list:
    pitches = df_yb.loc[pd.Timestamp(dt):pd.Timestamp(dt)]
    for dt, pitch in pitches.iterrows():
        ticker = pitch['ticker']
        sentiment = pitch['sentiment']
        if sentiment == 'neutral':
            continue

        data_fn = stock_data.joinpath(f"{ticker}.parquet")
        if data_fn.exists():
            df = pd.read_parquet(data_fn, engine='pyarrow', columns=['symbol', 'quote_datetime', 'close', 'volume'])
            df.set_index('quote_datetime', inplace=True)

            # Get MACD calcs
            df['macd'], df['sig'], _ = talib.MACD(df['close'].to_numpy())
            df['macd_above_sig'] = df['macd'] > df['sig']
            df = df[df.index >= dt]

            if sentiment == 'bullish':
                trigger_date = first_true_ts(df['macd_above_sig'])
            elif sentiment == 'bearish':
                macd_below_sig = ~df['macd_above_sig']
                trigger_date = first_true_ts(macd_below_sig)

            if pd.notna(trigger_date):
                signal = {
                    'trigger_dt': trigger_date,
                    'pitch_dt': dt,
                    'ticker': ticker,
                    'sentiment': sentiment,
                }
                signals.append(signal)


signals_df = pd.DataFrame(signals)
signals_df.to_csv('yb_signals.csv', index=False)