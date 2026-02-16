import pandas as pd
import numpy as np
from pathlib import Path
import pyarrow.parquet as pq
import pyarrow as pa

def forward_factor_pairs(
    term_df: pd.DataFrame,
    *,
    symbol_col: str = "symbol",
    quote_col: str = "quote_datetime",
    exp_col: str = "expiration",
    iv_col: str = "atm_iv",
    T_col: str = "T",
    dte_col: str = "dte",
    max_back_dte: int = 120,
    min_gap_dte: int = 7,
    min_ff: float = 0.14,
    keep_only_needed_cols: bool = True
) -> pd.DataFrame:
    """
    Compute Campasano ATM-IV Forward Factor for ALL quote dates in term_df (typically one ticker file),
    returning ALL expiry pairs (front_exp, back_exp) per quote_date where FF >= min_ff.

    Uses a self-merge on (symbol, quote_date), then vectorized forward IV math.
    """

    cols = [symbol_col, quote_col, exp_col, iv_col, T_col, dte_col]
    df = term_df[cols].copy()

    df[quote_col] = pd.to_datetime(df[quote_col]).dt.normalize()
    df[exp_col] = pd.to_datetime(df[exp_col]).dt.normalize()

    df = df.dropna(subset=[iv_col, T_col, dte_col])
    df = df[df[dte_col].between(1, max_back_dte)].copy()

    # small speed/memory win if many rows
    #df[symbol_col] = df[symbol_col].astype("category")

    left = df.rename(columns={
        exp_col: "front_exp",
        iv_col: "iv_front",
        T_col: "T1",
        dte_col: "front_dte"
    })
    right = df.rename(columns={
        exp_col: "back_exp",
        iv_col: "iv_back",
        T_col: "T2",
        dte_col: "back_dte"
    })

    pairs = left.merge(right, on=[symbol_col, quote_col], how="inner")

    # Valid ordering + constraints
    pairs = pairs[
        (pairs["back_dte"] >= pairs["front_dte"] + int(min_gap_dte)) &
        (pairs["back_dte"] <= int(max_back_dte)) &
        (pairs["T2"] > pairs["T1"]) &
        (pairs["T1"] > 0)
        ].copy()

    # Vectorized forward variance and FF
    iv_front = pairs["iv_front"].to_numpy(dtype=float)
    iv_back = pairs["iv_back"].to_numpy(dtype=float)
    T1 = pairs["T1"].to_numpy(dtype=float)
    T2 = pairs["T2"].to_numpy(dtype=float)

    denom = (T2 - T1)
    fwd_var = (iv_back ** 2 * T2 - iv_front ** 2 * T1) / denom

    ok = np.isfinite(fwd_var) & (fwd_var > 0)
    pairs = pairs.loc[ok].copy()

    pairs["fwd_iv"] = np.sqrt(fwd_var[ok])
    pairs["forward_factor"] = pairs["iv_front"] / pairs["fwd_iv"] - 1.0

    # Keep all pairs with FF >= threshold
    pairs = pairs[pairs["forward_factor"] >= float(min_ff)].copy()

    # Optional: drop obvious duplicates (front==back can't happen with our filters; keep as-is)
    # Sorting makes it easier to inspect or take top-N later
    pairs = pairs.sort_values(
        [symbol_col, quote_col, "forward_factor"],
        ascending=[True, True, False]
    ).reset_index(drop=True)

    if keep_only_needed_cols:
        pairs = pairs[[
            symbol_col, quote_col,
            "front_exp", "back_exp",
            "front_dte", "back_dte",
            "iv_front", "iv_back",
            "T1", "T2",
            "fwd_iv", "forward_factor"
        ]].copy()

    return pairs


options_root = Path(r'D:\options_data\daily')
dest_folder = Path(r'D:\test_data\forward_factor\source_files')
option_dirs = list(options_root.glob('*'))
names = [x.name for x in option_dirs]

for d in option_dirs:
    ticker = d.name

    iv_file = d.joinpath('data', f'{ticker}_iv.parquet')
    if not iv_file.exists():
        continue
    print(f'forward factor for {ticker}')
    df_iv = pd.read_parquet(iv_file, engine='pyarrow')
    df_iv = df_iv.sort_values(by=['quote_datetime', 'expiration'])
    ffs = forward_factor_pairs(df_iv)

    ta = pa.Table.from_pandas(ffs)
    schema = ta.schema.remove_metadata()
    ta = ta.replace_schema_metadata(schema.metadata)
    fn = dest_folder.joinpath(f'{ticker}_ff_pairs.parquet')
    pq.write_table(ta, fn)
