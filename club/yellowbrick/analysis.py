import pandas as pd
from matplotlib import pyplot as plt
from pathlib import Path

output_folder = Path(r'D:\test_data\yellowbrick')
fn = Path(r'D:\projects\club\Yellowbrick\yb_returns.parquet')

df_returns = pd.read_parquet(fn, engine='pyarrow')

avg_curve = df_returns.groupby("day")["excess_rtn"].mean()

# avg_curve.plot(kind="line")
# plt.title("Average Excess Returns")
# plt.ylabel("Return %")
# plt.xlabel("Days")
# plt.show()

bullish = df_returns[df_returns['sentiment'] == "bullish"]
bearish = df_returns[df_returns['sentiment'] == "bearish"]

pct = len(bullish)/len(df_returns)
print(pct)

avg_bullish_x = bullish.groupby("day")["excess_rtn"].mean()
avg_bearish_x = bearish.groupby("day")["excess_rtn"].mean()

# plt.plot(avg_bullish_x, label="bullish", color="blue")
# plt.plot(avg_bearish_x, label="bearish", color="orange")
#
# plt.title("Average Excess Returns")
# plt.ylabel("Return %")
# plt.xlabel("Days")
# plt.legend()
#
# plt.show()
#
# plt.plot(avg_bullish_x, label="bullish", color='blue')
# plt.title("Bullish Excess Returns")
# plt.ylabel("Return %")
# plt.xlabel("Days")
# plt.legend()
# plt.show()
#
# plt.plot(avg_bearish_x, label="bearish", color='orange')
# plt.title("Bearish Excess Returns")
# plt.ylabel("Return %")
# plt.xlabel("Days")
# plt.legend()
# plt.show()
#
# avg_bullish = bullish.groupby("day")["stock_rtn"].mean()
# plt.plot(avg_bullish, label="bullish", color='blue')
# plt.title("Bullish Returns")
# plt.ylabel("Return %")
# plt.xlabel("Days")
# plt.legend()
# plt.show()

df_days = bullish[(bullish['day'] == 30) | (bullish['day'] == 60) | (bullish['day'] == 90) | (bullish['day'] == 180) | (bullish['day'] == 250)]
avg_days = df_days.groupby("day")["excess_rtn"].mean()
med_days = df_days.groupby("day")["excess_rtn"].median()

alpha = (bullish['excess_rtn'] > 0).mean()
print(alpha)
print(bullish['excess_rtn'].median())

quantile = bullish['excess_rtn'].quantile([
   0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
)
print(quantile)

horizons = [30, 60, 90, 180, 250]

summary = (
    bullish[bullish["day"].isin(horizons)]
    .pivot(
        index="tip_id",
        columns="day",
        values="excess_rtn"
    )
    .rename(columns=lambda x: f"alpha_{x}")
)

summary = summary.merge(
    bullish[["tip_id", "contributor"]].drop_duplicates(),
    on="tip_id"
)


# Contributor

contributors = (
    summary
    .groupby("contributor")
    .agg(
        count=("tip_id", "count"),

        mean_30=("alpha_30", "mean"),
        mean_60=("alpha_60", "mean"),
        mean_90=("alpha_90", "mean"),
        mean_180=("alpha_180", "mean"),
        mean_250=("alpha_250", "mean"),

        median_30=("alpha_30", "median"),
        median_60=("alpha_60", "median"),
        median_90=("alpha_90", "median"),
        median_180=("alpha_180", "median"),
        median_250=("alpha_250", "median"),

        win_30=("alpha_30", lambda x: (x > 0).mean()),
        win_60=("alpha_60", lambda x: (x > 0).mean()),
        win_90=("alpha_90", lambda x: (x > 0).mean()),
        win_180=("alpha_180", lambda x: (x > 0).mean()),
        win_250=("alpha_250", lambda x: (x > 0).mean()),
    )
)


# contributors = tips.groupby("contributor").agg(
#    mean_alpha = ("excess_rtn", "mean"),
#    median_alpha = ("excess_rtn", "median"),
#    win_rate = ("excess_rtn", lambda x: (x > 0).mean()),
#    q90 = ("excess_rtn", lambda x: x.quantile(0.9)),
#    q10 = ("excess_rtn", lambda x: x.quantile(0.1)),
#    count = ("tip_id", "count")
# )
# contributors = contributors[contributors['count'] > 200]
# contributors['win_rate'] = contributors['win_rate'] * 100
# contributors.sort_values(["median_alpha", "win_rate"], ascending=False, inplace=True)
# print(contributors)
#
contributors.to_csv(output_folder / 'contributors.csv', index=True)
#
# contributors.plot.scatter(x="count", y="median_alpha")
# plt.show()

pass