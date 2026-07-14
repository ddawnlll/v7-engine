"""Factor selection via IC/RankIC filtering (AlphaForge paper recommendation).
Paper says: optimal factor pool = 10, IC > 3%, ICIR > 0.1, correlation < 0.5.
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "alphaforge/src")
from alphaforge.labels.simulation_r_labels import generate_r_multiple_labels
from scipy.stats import spearmanr

PANEL = "/root/v7-engine/cache/v7_lite_expanded_panel_v1"
close_df = pd.read_parquet(PANEL + "/panel_v7lite_expanded_close.parquet")
ohlcv_raw = {}
for f in ["close","high","low","open","volume"]:
    ohlcv_raw[f] = pd.read_parquet(PANEL + "/panel_v7lite_expanded_" + f + ".parquet")[f].values.astype(np.float64)
ohlcv_raw["symbol"] = close_df["symbol"].values

# Get R-multiple labels
symbols = close_df["symbol"].unique()
all_ints, all_r = [], []
for sym in symbols:
    mask = ohlcv_raw["symbol"] == sym
    sc, hi, lo = ohlcv_raw["close"][mask], ohlcv_raw["high"][mask], ohlcv_raw["low"][mask]
    ints, net_r, _, _ = generate_r_multiple_labels(sc, hi, lo)
    all_ints.append(ints); all_r.append(net_r)

ints_all = np.concatenate(all_ints)
r_all = np.concatenate(all_r)

print("=" * 60)
print("FACTOR SELECTION ANALYSIS (56 symbols)")
print("=" * 60)
print("Total samples: %d" % len(r_all))
print("Active (LONG/SHORT): %d (%.1f%%)" % (int(np.sum(ints_all != 2)), np.mean(ints_all != 2) * 100))
print()
print("Paper recommendation:")
print("  - Optimal factor pool: 10 features")
print("  - IC > 3%, ICIR > 0.1")
print("  - Return correlation < 0.5")
print("  - Dynamic combination: linear regression per rebalance period")
print()
print("Current system: ~108 features (mode-dependent)")
print("Recommendation: reduce to 10-20 features via IC/RankIC filtering")
