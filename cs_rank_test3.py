import sys, numpy as np, pandas as pd
sys.path.insert(0, "alphaforge/src")
from collections import Counter

panel_dir = "/root/v7-engine/cache/v7_lite_expanded_panel_v1"
close_df = pd.read_parquet(f"{panel_dir}/panel_v7lite_expanded_close.parquet")
ohlcv = {}
for f in ["close","high","low","open","volume"]:
    ohlcv[f] = pd.read_parquet(f"{panel_dir}/panel_v7lite_expanded_{f}.parquet")[f].values.astype(np.float64)
ohlcv["symbol"] = close_df["symbol"].values

sym_lens = Counter()
for sym in set(ohlcv["symbol"]):
    mask = ohlcv["symbol"] == sym
    sym_lens[int(mask.sum())] += 1
target_len = max(sym_lens.keys(), key=lambda k: sym_lens[k])
print(f"Target: {target_len} bars ({sym_lens[target_len]} symbols)")

multi_ohlcv = {}
for sym in set(ohlcv["symbol"]):
    mask = ohlcv["symbol"] == sym
    if int(mask.sum()) != target_len:
        continue
    multi_ohlcv[sym] = {
        "open": ohlcv["open"][mask], "close": ohlcv["close"][mask],
        "high": ohlcv["high"][mask], "low": ohlcv["low"][mask],
        "volume": ohlcv["volume"][mask],
    }
print(f"Multi-symbol: {len(multi_ohlcv)} symbols")

from alphaforge.features.cross_sectional_rank import compute_cross_sectional_rank_group
cs = compute_cross_sectional_rank_group(multi_ohlcv)
print("Cross-sectional rank:")
for k, v in cs.items():
    print(f"  {k}: {v.shape} mean={np.nanmean(v):.4f}")

from alphaforge.features.lead_lag import compute_lead_lag_group
primary = list(multi_ohlcv.keys())[0]
context = "BTCUSDT" if "BTCUSDT" in multi_ohlcv else list(multi_ohlcv.keys())[1]
ll = compute_lead_lag_group(multi_ohlcv=multi_ohlcv, primary_symbol=primary, context_symbol=context)
print("Lead-lag:")
for k, v in ll.items():
    print(f"  {k}: {v.shape} mean={np.nanmean(v):.4f}")
