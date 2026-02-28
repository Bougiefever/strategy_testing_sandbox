"""
YouTube https://youtu.be/Fj41ojAdwJ8?si=ipuNz--CvdiP8XQ6

### Summary of Zero DTE Break Even Iron Condor Strategy by Yon Aar Sanan (John)

**Yon Aar Sanan**, also known as John in English, shares his extensive experience trading the **Zero Days to Expiration (Zero DTE) Break Even Iron Condor** strategy on the S&P 500 index options (SPX). With over **9,000 trades and nearly five years of consistent profitability**, John presents a disciplined, risk-managed approach to day trading iron condors with tight stop-losses and controlled risk.

---

### Core Concepts of the Strategy

- **Zero DTE**: Trades are opened and closed within the same trading day, focusing on options expiring that day.
- **Iron Condor Setup**: Simultaneously selling a **call credit spread** on the upside and a **put credit spread** on the downside, aiming to collect roughly **equal premiums on both sides**.
- **Stop-Loss Rules**:
  - Separate stop-losses are set on each side (call and put) equal to the **total premium collected**.
  - If one side hits the stop-loss (most common), the trade ends roughly at break-even.
  - Losses only occur if **both stop-losses are hit**, which happens in about **8% of trades**.
- **Risk Management**:
  - Never risk more than **1-2% of total account equity per day**, measured by worst-case scenario if all stop-losses trigger.
  - Use no more than **50% of available buying power** on this strategy daily.
- **Trade Frequency**:
  - Typically, enter **one trade per hour** starting about 10-15 minutes after market open, continuing throughout the day including the last three hours which have historically been most profitable.
  - Usually hold around **6-7 trades concurrently**, up to a maximum of 10.
- **Strike Selection**:
  - Short strikes generally set at **10 to 15 delta**.
  - Target premium collection of **$100-$200 per side** ($200-$300 total premium).
  - Starting wing width typically **30 points**, adjusted to balance premium on both sides.

---

### Trade Mechanics and Management

- **Entry Timing**: Wait for market stabilization, defined by observing **two to three 5-minute candles at a similar price level** before entering.
- **Order Execution**: Enter call spread first, followed immediately by the put spread to minimize slippage and ensure balanced premiums.
- **Exit Strategy**:
  - Trades are held until automated stop orders hit or short options reach a value of **5 cents**, at which point the position is closed to lock in profits and reduce risk.
  - Closing shorts at 5 cents also helps avoid last-minute market swings and allows reuse of long options for new trades.
- **Stop-Loss Setup**:
  - Stops are set **only on the short legs**, not on the spreads, reducing slippage and improving execution speed.
  - Uses a combination of **stop-limit and stop-market orders** (OKO – one cancels the other) with a 40-point window between stop and limit, and a stop market order 30 points further out as a last defense.
- **Long Leg Management**:
  - Usually closed immediately if stop-loss triggers on shorts.
  - Occasionally allowed to run if the long option gains enough value to potentially make the whole trade profitable despite the stop loss.

---

### Risk Profile and Challenges

| Risk Factor                         | Description                                                                                   | Frequency/Impact                |
|-----------------------------------|-----------------------------------------------------------------------------------------------|--------------------------------|
| Double Stop-Loss Hits              | Both sides hit stop-losses causing real losses                                               | ~8% of trades                  |
| Catastrophic Fills                | Fast market moves causing poor fills and large losses                                        | Rare but possible (liquidity risk) |
| Market Volatility & Whipsaws      | Intraday volatility can cause multiple stop-loss triggers                                    | Increased recently             |
| Need for Active Monitoring         | Trades require constant monitoring or reliable automation                                    | Essential for risk control     |

- John rates the risk level of this strategy as **4 out of 10**, assuming strict discipline and adherence to risk rules.
- The strategy tends to have **low drawdowns** relative to other zero DTE strategies.
- Caution is advised as poor discipline or ignoring risk limits can drastically increase losses.

---

### Performance Metrics

| Metric                     | Value                      | Notes                                                                                      |
|----------------------------|----------------------------|--------------------------------------------------------------------------------------------|
| Average Net Profit per Trade| 0.28%                      | Measured as net profit divided by buying power used; reflects efficient capital reuse    |
| Premium Capture Rate        | 5.65%                      | Net profit divided by total premium collected; shows profitability despite low win rate  |
| Win Rate                   | ~40%                       | Low win rate, but wins are more than twice the size of losses, resulting in positive expectancy |
| Drawdowns                 | Relatively low              | Consistent profitability with few small drawdowns over 5 years                            |

---

### Additional Insights

- **Win Rate vs Expectancy**: The strategy’s success relies on positive expectancy (wins larger than losses), not a high win rate.
- **Time & Day Effects**:
  - Most profitable days: **Mondays and Fridays**.
  - Least profitable: **Thursdays** (roughly break-even).
  - Most profitable hours: Last three hours of trading.
- **Comparison to MEIC**: Similar to "Multiple Entries Iron Condor" (MEIC) popularized by Tammy Chamblas, but John’s style is less mechanical and often collects lower premiums.
- **Trade Log Importance**: Keeping detailed records for analysis is critical to track performance and improve.

---

### Suitability and Recommendations

- **Best suited for**:
  - Traders who are **risk-averse** but want exposure to zero DTE day trading.
  - Those who can **monitor trades actively** or have reliable automation.
  - Traders interested in **multiple trades per day** with strict risk controls.
- **Not suited for**:
  - Traders unable to maintain discipline or monitor trades actively.
  - Those seeking a high win rate or "set and forget" strategies without active management.

---

### Resources for Further Learning

- Videos on the Theta Profits YouTube channel featuring:
  - Interviews with **David Baronson**, **Nick Magno**, and **Tammy Chamblas**.
- Facebook group **Quantum Options** run by Tammy Chamblas, offering daily updates, research, and community support.

---

### Key Takeaways

- **Discipline is critical**: Stick to stop-losses and risk limits.
- **Always assess total risk**: Know your maximum daily loss if all stops hit.
- **Maintain a trade log**: Essential for analyzing and improving performance.
- The strategy provides a **consistent, profitable zero DTE approach** with relatively low drawdowns if managed properly.

---

This comprehensive overview reflects John’s personal experience and insights into the **Zero DTE Break Even Iron Condor** strategy, emphasizing **risk management, trade discipline, and active monitoring** as keys to success in this form of options day trading.

"""

import pandas as pd
import numpy as np
import talib
import datetime
from pathlib import Path
from options_framework.config import settings
from options_framework.utils.helpers import get_market_dates
from options_framework.portfolio import OptionPortfolio
from options_framework.spreads.vertical import Vertical
from collections import defaultdict
from utility import *

options_root = Path(r'D:\options_data\daily')
start_date = datetime.datetime(2022, 1, 3)
end_date = datetime.datetime(2022, 11, 23)
delta_target = 0.10
delta_min = 0.08
delta_max= 0.16
prem_target = 1.25
prem_min = 0.75
prem_max = 2.5
starting_width = 30

starting_cash = 100_000
start_time = datetime.time(9, 30)
open_times = defaultdict(datetime.time)
open_times[1] = datetime.time(9, 45)
open_times[2] = datetime.time(10, 0)
open_times[3] = datetime.time(11, 0)
open_times[4] = datetime.time(12, 0)
open_times[5] = datetime.time(13, 0)
open_times[6] = datetime.time(14, 0)
open_times[7] = datetime.time(14, 30)
closing_time = datetime.time(15, 50)
end_time = datetime.time(16, 0)
ticker = 'SPXW'

def get_day_times(dt: datetime.datetime) -> list[datetime.datetime]:
    tm = open_times[3]
    today = []
    while tm <= end_time:
        new_dt = datetime.datetime.combine(dt, tm)
        today.append(new_dt)
        new_dt += datetime.timedelta(minutes=5)
        tm = new_dt.time()
    return today

def get_vertical_spread(option_type, short_strike, long_strike_target):
    long_strike = min(strikes, key=lambda x: abs(long_strike_target - x))
    credit_spread = Vertical.create(option_chain=option_chain, expiration=exp, option_type=option_type,
                                         long_strike=long_strike, short_strike=short_strike)
    premium = credit_spread.short_option.get_open_price() - credit_spread.long_option.get_open_price()
    return credit_spread, premium

def score_candidate_pairs(call_candidate, put_candidate):
    call_prem = call_candidate[1]
    put_prem = put_candidate[1]
    total_prem = call_prem + put_prem

    # ratio of larger to smaller premium - 1.0 is a perfect score
    balance = min(call_prem, put_prem) / max(call_prem, put_prem)

    # get average deltas
    avg_delta = (call_candidate[0].short_option.delta + abs(put_candidate[0].short_option.delta)) / 2.0
    delta_penalty = abs(avg_delta - delta_target)

    score = (1.0 - balance) * 10.0 + delta_penalty
    return score, total_prem

def get_closing_price(vertical_spread):
    short_price = vertical_spread.short_option.get_closing_price()
    long_price = vertical_spread.long_option.get_closing_price()
    return long_price - short_price, short_price

def on_expired(vertical_spread):
    vertical_spread.user_defined['exit_reason'] = 'expired'

dts = get_market_dates(start_date=start_date, end_date=end_date)

start_date = datetime.datetime.combine(start_date, start_time)
end_date = datetime.datetime.combine(end_date, end_time)
portfolio = OptionPortfolio(cash=starting_cash, start_date = start_date, end_date = end_date, check_margin_on_open=False)
portfolio.bind(position_expired=on_expired)

pair_id = 0
for dt in dts:
    print(dt)
    times = get_day_times(dt)
    trade_num = 6
    trade_time = open_times[trade_num]
    exp = None
    find_trade = False
    for dtt in times:
        tm = dtt.time()
        #print(tm)
        portfolio.next(dtt, 'SPXW')
        option_chain = portfolio.option_chains[ticker]
        if len(option_chain.expirations) == 0:
            continue

        # find today expiration
        if exp is None:
            try:
                expirations = option_chain.expirations
                exp = next(x for x in expirations if x == dt.date())
                strikes = option_chain.expiration_strikes[exp]
            except StopIteration:
                break # if there is not a 0dte expiration, go to next date

        open_positions = portfolio.positions.copy()
        for p in open_positions:
            partner_id = p.user_defined['partner_id']
            sl_prem = p.user_defined['total_prem']
            price, short_price = get_closing_price(p)
            trade_price = p.get_trade_price()
            prem = (price - trade_price) * 100 * p.quantity
            exit_reason = ''
            to_close = False
            if prem <= sl_prem:
                exit_reason = 'stop'
                to_close = True
            elif tm >= closing_time:
                if short_price > 0.05:
                    exit_reason = 'time'
                    to_close = True
            elif short_price <= 0.05:
                exit_reason = 'profit'
                to_close = True

            if to_close:
                portfolio.close_position(p, exit_reason=exit_reason)

        # check open positions
        if find_trade or tm == trade_time:
            # open new trade
            #print(trade_num, trade_time)


            # find calls
            call_options = [x for x in option_chain.options if x['expiration'] == exp and x['option_type'] == 'call'
                            and x['delta'] >= delta_min]
            call_options.sort(key=lambda x: x['delta'], reverse=False)

            call_candidates = []
            spread_width = starting_width
            while True:
                short = call_options.pop(0)
                short_strike = short['strike']
                long_strike_target = short['strike'] + spread_width
                call_spread, premium = get_vertical_spread('call', short_strike, long_strike_target)
                if delta_min < call_spread.short_option.delta < delta_max:
                    if prem_min < premium < prem_max:
                        call_candidates.append((call_spread, premium))
                else:
                    break

            put_options =  [x for x in option_chain.options if x['expiration'] == exp and x['option_type'] == 'put'
                            and x['delta'] <= -delta_min]
            put_options.sort(key=lambda x: x['delta'], reverse=True)
            put_candidates = []
            while True:
                short = put_options.pop(0)
                short_strike = short['strike']
                long_strike_target = short['strike'] - spread_width
                put_spread, premium = get_vertical_spread('put', short_strike, long_strike_target)
                if -delta_min > put_spread.short_option.delta > -delta_max:
                    if prem_min < premium < prem_max:
                        put_candidates.append((put_spread, premium))
                else:
                    break

            pairs = []
            for c in call_candidates:
                for p in put_candidates:
                    # filter out any that do not meet minimum ratio requirements
                    ratio = min(c[1], p[1]) / max(c[1], p[1])
                    if ratio < 0.67:
                        continue
                    score, total = score_candidate_pairs(c, p)
                    pairs.append((score, -total, c, p))

            pairs.sort(key=lambda x: x[0])
            if len(pairs) == 0:
                find_trade = True if tm.minute < (trade_time.minute + 15) else False
                continue
            _, total_prem, call_spread, put_spread = pairs[0][0], pairs[0][1], pairs[0][2][0], pairs[0][3][0]
            total_prem = total_prem * 100

            portfolio.open_position(call_spread, quantity=1, pair_id=pair_id, partner_id=put_spread.instance_id, total_prem=total_prem)
            portfolio.open_position(put_spread, quantity=1, pair_id=pair_id, partner_id=call_spread.instance_id, total_prem=total_prem)
            pair_id += 1
            trade_num += 1
            trade_time = open_times[trade_num]
            find_trade = False


closed_positions = portfolio.closed_positions.copy()

trades = [{
        'id': x.instance_id,
        'symbol': x.symbol,
        'option_type': x.option_type,
        'pair_id': x.user_defined['pair_id'],
        'entry_dt': x.get_open_datetime(),
        'exit_dt': x.get_close_datetime(),
        'open_premium': x.get_trade_premium(),
        'expiration': x.expiration,
        'open_spot_price': x.long_option.trade_open_info.spot_price,
        'close_spot_price': x.spot_price,
        'open_price': x.get_trade_price(),
        'close_price': x.get_closed_price(),
        'pnl': x.get_profit_loss(),
        'pnl_pct': x.get_profit_loss_percent(),
        'qty': x.long_option.trade_open_info.quantity,
        'fees': x.get_fees(),
        'reason': x.user_defined['exit_reason'],
        }
        for x in portfolio.closed_positions]

df_trades = pd.DataFrame(trades)
stats = trade_stats(df_trades)
print(stats)

output_folder = Path(r'D:\test_data\spx_ic')
fn = output_folder.joinpath('trades_4.csv')
df_trades.to_csv(fn, index=False)
stats.to_csv(output_folder.joinpath('stats_4.csv'), index=True)







