"""
Daily Prices:
Put Credit Spread (Vertical)

    * Get the options with the closest to 30 dte
    * Find the put option closest to -0.30 delta
    * Find the put option 10 points further OTM
    * The stop loss is 2x the credit received
    * The profit target is 50% of the credit received
    * Only open if SPY open price is greater than the 200 SMA

"""

from options_framework import OptionPortfolio, Vertical, OptionPositionType, settings, get_market_dates
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import talib

# Custom event handlers can be created for portfolio or option events
def position_is_expiring(my_position):
    # add the user_defined "exit_reason" to the position
    my_position.user_defined['exit_reason'] = 'expired'

# set up test parameters
starting_equity = 100_000
start_date = datetime(2022, 1, 3)
end_date = datetime(2023, 12, 29)
target_dte = 30
target_delta = -0.30
spread_width = 10
position_risk = 0.01
profit_percent = 0.50

# You can add your own settings values to the settings.toml file. They will be available in settings.
df_spy = pd.read_parquet(Path(settings["stock_data_files"]).joinpath("SPY.parquet"))
df_spy = df_spy.set_index("quote_datetime")
df_spy = df_spy.sort_index()

# take the 200 ma of the close price - take the price from the previous day to avoid
# peeking into the future
df_spy['ma200'] = talib.SMA(df_spy['close'].shift(1).to_numpy(), timeperiod=200)
df_spy = df_spy.loc[start_date:end_date]

# Helper function to get market dates. All non-market days are skipped. Optionally, you can
# skip economic and half-days as well by adding the settings to the settings.toml file
test_dates = get_market_dates(start_date=start_date, end_date=end_date)
settings['data_frequency'] = 'daily' # override the settings file value

portfolio = OptionPortfolio(cash=starting_equity, start_date=start_date, end_date=end_date)

# Optionally bind to position_closed or position_expired events to surface this in your test for logging
portfolio.bind(position_expired=position_is_expiring)

for dt in test_dates:
    open_price = df_spy.loc[dt, 'open']
    ma_200 = df_spy.loc[dt, 'ma200']

    # Pass current dt to the portfolio so the correct option chains will be fetched
    # If you are trading with multiple symbols, you can pass an array of symbols
    portfolio.next(dt, 'SPY')

    # get the option chain from the portfolio. It will have the quotes from its "current_datetime" property
    # which is set when "next" is called on the portfolio
    option_chain = portfolio.option_chains['SPY']

    # check if trades are closing today. Make a copy so the open positions list
    # so the list isn't changing as you're looping through it. Closing removes items from the portfolio's list
    positions = portfolio.positions.copy()
    for position in positions:
        pnl = position.get_profit_loss()
        pnl_pct = position.get_profit_loss_percent()
        exit_trade = False

        max_loss = position.user_defined['max_loss_premium']
        if pnl < max_loss:
            exit_trade = True
            exit_reason = 'stop loss'

        if pnl_pct >= profit_percent:
            exit_trade = True
            exit_reason = 'profit'

        if exit_trade:
            # close the trade from the portfolio. Adding the user_defined "exit_reason"
            portfolio.close_position(option_spread=position, exit_reason=exit_reason)

    if open_price >= ma_200:
        # find the expiration closest to the target dte
        expirations = option_chain.expirations
        exp_target_dt = dt + timedelta(days=target_dte)
        expiration = min(expirations, key=lambda x: abs(x - exp_target_dt.date()).days)

        # get option quotes for the selected expiration. Since we only want puts, we can select on that as well.
        options = [x for x in option_chain.options if x['expiration'] == expiration and x['option_type'] == 'put']

        # Short option: find the option with the delta closest to the target
        deltas = [x['delta'] for x in options]
        delta = min(deltas, key=lambda x: abs(x - target_delta))
        short_strike = next(x['strike'] for x in options if x['delta'] == delta)

        # Long option: find the option with the closest strike that is at least 10 points away
        # first get the strikes available for the selected expiration
        strikes = option_chain.expiration_strikes[expiration]
        strikes.sort(reverse=True)
        long_strike = next(x for x in strikes if x <= (short_strike - spread_width))

        # define the option spread using the create function of the spread type, in this case, VERTICAL
        put_credit_spread = Vertical.create(
            option_chain=option_chain,
            expiration=expiration,
            option_type="put",
            short_strike=short_strike,
            long_strike=long_strike,
            position_type=OptionPositionType.SHORT)

        # calculate the number of contracts to open
        max_position_risk = portfolio.current_value * position_risk
        pcs_spread_width = put_credit_spread.short_option.strike - put_credit_spread.long_option.strike
        risk_per_contract = (pcs_spread_width - abs(put_credit_spread.price)) * 100
        shares = max(1, int(round((max_position_risk / risk_per_contract), 0)))

        # open the position in the portfolio. You can add any user-defined values by just adding it to the kwargs
        # option_spread and quantity are required. Any keyword arguments added will be available in a dictionary
        # named user_defined
        portfolio.open_position(option_spread=put_credit_spread, quantity=shares, ma_200=ma_200)

        # You can add items directly to "user_defined"
        max_loss_premium = put_credit_spread.get_trade_premium() * 2
        put_credit_spread.user_defined["max_loss_premium"] = max_loss_premium

# after looping through all the dates, you can close any remaining open positions
positions = portfolio.positions.copy()
for position in positions:
    portfolio.close_position(option_spread=position, exit_reason='end of test')

# When the portfolio closes positions, it moves them to the "closed_positions" list
# We can use this list to analyze the test results
trades = [{
    'id': x.instance_id, # Each position is identified by a unique id
    'symbol': x.symbol,
    'entry_date': x.get_open_datetime(),
    'exit_date': x.get_close_datetime(),
    'open_premium': x.get_trade_premium(),
    'expiration': x.expiration,
    'long_option_id': x.long_option.instance_id, # Each option is also identified by its own unique id
    'long_strike': x.long_option.strike,
    'short_strike': x.short_option.strike,
    'short_option_id': x.short_option.instance_id,
    'open_spot_price': x.short_option.trade_open_info.spot_price,
    'close_spot_price': x.spot_price,
    'vertical_open_price': x.get_trade_price(),
    'gross_pnl': x.get_profit_loss(),
    'net_pnl': (x.get_profit_loss() - x.get_fees()),
    'pnl_pct': x.get_profit_loss_percent(),
    'days_in_trade': x.get_days_in_trade(),
    'fees': x.get_fees(),
    'ma_200': x.user_defined['ma_200'],
    'exit_reason': x.user_defined['exit_reason'], }
    for x in portfolio.closed_positions]

# Now you can use the data to analyze the test
df_trades = pd.DataFrame(trades)


