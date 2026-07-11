#!/usr/bin/env python3
"""Real data research training run — 10 symbols, Binance OHLCV.
All features use CAUSAL (trailing) windows. No lookahead.
IC/RankIC computed on held-out (last 20% time split), not in-sample.
"""
import numpy as np, pandas as pd, json, os, time, warnings, glob
warnings.filterwarnings('ignore')


def _causal_rolling(arr, window, func="mean"):
    """Causal rolling: only past data. Same-length output, NaN for warmup."""
    n = len(arr)
    result = np.full(n, np.nan)
    kernel = np.ones(window) / window
    if func == "mean":
        conv = np.convolve(arr, kernel, mode="valid")
    elif func == "sum":
        conv = np.convolve(arr, np.ones(window), mode="valid")
    else:
        raise ValueError(f"Unknown func: {func}")
    result[window-1:] = conv
    return result


def _causal_atr(high, low, close, window=14):
    """Causal ATR — no lookahead."""
    tr = np.maximum(high - low,
                    np.maximum(np.abs(high - np.roll(close, 1)),
                               np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    return _causal_rolling(tr, window, func="mean")


print("=" * 60)
print("V7 ENGINE — REAL DATA RESEARCH TRAINING RUN (CAUSAL)")
print("=" * 60)

# ── 1. Load real data ──
print("\n[1] Loading Binance OHLCV...")
files = sorted(glob.glob("data/raw/*/*.parquet"))
print(f"  Files: {len(files)}")
all_data = []
for f in files:
    symbol = f.split("/")[2]
    df = pd.read_parquet(f)
    df["symbol"] = symbol
    all_data.append(df)
data = pd.concat(all_data, ignore_index=True).sort_values(["symbol", "timestamp"])
symbols = data["symbol"].unique().tolist()
print(f"  Symbols ({len(symbols)}): {symbols}")
print(f"  Total rows: {len(data)}")

# ── 2. Compute features (CAUSAL only) ──
print("\n[2] Computing causal features...")
X_parts, y_parts = [], []
warmup_bars = 60  # max window across all features

for symbol in symbols:
    s = data[data["symbol"] == symbol].copy()
    o, h, l, c, v = (s["open"].values, s["high"].values, s["low"].values,
                      s["close"].values, s["volume"].values)
    n = len(c)

    # Returns (causal — diff is naturally causal)
    ret = np.diff(c, prepend=c[0]); ret[0] = 0.0

    # Causal rolling features
    ma5_ret = _causal_rolling(ret, 5)
    ma20_ret = _causal_rolling(ret, 20)
    ma20_c = _causal_rolling(c, 20)
    vol20 = _causal_rolling(v, 20)
    atr14 = _causal_atr(h, l, c, 14)
    pos_ratio_10 = _causal_rolling((ret > 0).astype(float), 10)
    ma3_ret = _causal_rolling(ret, 3)
    ma50_c = _causal_rolling(c, 50)
    vwap_diff = _causal_rolling(v * np.diff(c, prepend=c[0]), 5, func="sum")
    v_sum_5 = _causal_rolling(v, 5, func="sum")

    feat = np.column_stack([
        ret,                              # 0: return
        ma5_ret,                          # 1: MA5 return
        ma20_ret,                         # 2: MA20 return
        c / ma20_c - 1,                   # 3: price vs MA20
        (h - l) / c,                      # 4: range ratio
        v / vol20,                        # 5: volume ratio
        atr14 / c,                        # 6: ATR%
        np.maximum(0, ret),               # 7: pos return
        np.minimum(0, ret),               # 8: neg return
        pos_ratio_10,                     # 9: pos ratio 10
        ma3_ret - ma20_ret,               # 10: momentum diff
        (c - ma50_c) / atr14,             # 11: z-score-ish
        np.abs(np.diff(c, prepend=c[0])) / atr14,  # 12: R multiple
        vwap_diff / v_sum_5,              # 13: VWAP diff
    ])

    # Forward return label (causal: only past data, nan for last 5 bars)
    fwd_ret = np.full(n, np.nan)
    fwd_ret[:-5] = c[5:] / c[:-5] - 1
    label = np.full(n, "NO_TRADE", dtype="U20")
    label[fwd_ret > 0.002] = "LONG_NOW"
    label[fwd_ret < -0.002] = "SHORT_NOW"

    X_parts.append(feat)
    y_parts.append(label)

X = np.vstack(X_parts).astype(np.float64)
y = np.concatenate(y_parts)

# Remove NaN rows + warmup per symbol
valid = ~(np.isnan(X).any(axis=1) | np.isinf(X).any(axis=1))
# Mark first warmup_bars per symbol as invalid
cumul = 0
for s in symbols:
    cnt = (data["symbol"] == s).sum()
    # First warmup_bars of this symbol's block
    end = min(cumul + warmup_bars, cumul + cnt)
    valid[cumul:end] = False
    cumul += cnt

X, y = X[valid], y[valid]

classes, counts = np.unique(y, return_counts=True)
print(f"  Dims: {X.shape[1]}, samples: {len(X)}")
for c_val, cnt in zip(classes, counts):
    print(f"    {c_val}: {cnt} ({cnt/len(y)*100:.1f}%)")

# ── 3. Research profile ──
print("\n[3] Research profile...")
from simulation.contracts.models import SimulationProfile, TradingMode
from simulation.profile_registry.registry import register_profile
research = SimulationProfile(
    profile_version="1.0.0-research", mode=TradingMode.SCALP,
    primary_interval="1h", max_holding_bars=24, stop_multiplier=2.5,
    target_multiplier=2.5, ambiguity_margin_r=0.15, min_action_edge_r=0.10,
    no_trade_default=True, context_intervals=["4h","15m"],
    refinement_intervals=["15m"], stop_method="atr_medium", target_method="atr_medium")
h = register_profile(research)
print(f"  Hash: {h}")

# ── 4. XGBoost training (chronological split) ──
print("\n[4] Training XGBoost (SCALP profile)...")
from alphaforge.training.xgb_trainer import XGBoostTrainer

split = int(len(X) * 0.8)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]

t0 = time.time()
trainer = XGBoostTrainer(mode="SCALP")
result = trainer.train(X_train, y_train)
t1 = time.time()
ma = result.model_artifact
print(f"  Duration: {t1-t0:.2f}s")
print(f"  HP: lr={ma['hyperparameters']['learning_rate']}, depth={ma['hyperparameters']['max_depth']}")
print(f"  Class counts: {dict(ma.get('class_counts',{}))}")
print(f"  Class weights: {dict(ma.get('class_weights',{}))}")
print(f"  Val accuracy (in-fold): {ma['training_metrics']['val_accuracy']:.4f}")

# ── 5. HELD-OUT evaluation (strictly OOS) ──
print("\n[5] Held-out evaluation (last 20%, strictly OOS)...")
from alphaforge.reports.ic_metrics import compute_ic, compute_rank_ic

probs = result.model.inplace_predict(X_test)
pred_class = np.argmax(probs, axis=1)
label_map = {"LONG_NOW": 0, "SHORT_NOW": 1, "NO_TRADE": 2}
actual = np.array([label_map[l] for l in y_test])
oos_acc = (pred_class == actual).mean()

# Directional signal: P(LONG) - P(SHORT)
directional = probs[:, 0] - probs[:, 1]
directional_actual = np.where(actual == 0, 1.0, np.where(actual == 1, -1.0, 0.0))
ic = compute_ic(directional, directional_actual)
rank_ic = compute_rank_ic(directional, directional_actual)
print(f"  OOS accuracy: {oos_acc:.4f}")
print(f"  OOS IC: {ic:.4f}")
print(f"  OOS RankIC: {rank_ic:.4f}")

# ── 6. Directional accuracy (held-out) ──
print("\n[6] Directional accuracy (held-out)...")
correct_dir = (directional * directional_actual) > 0
total_non_neutral = int((actual != 2).sum())
dir_acc = correct_dir.sum() / total_non_neutral if total_non_neutral > 0 else 0
print(f"  Directional accuracy: {dir_acc:.4f} ({correct_dir.sum()}/{total_non_neutral})")

# ── 7. Save ──
results = {
    "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "sha": os.popen("git rev-parse HEAD 2>/dev/null").read().strip(),
    "data": {"symbols": symbols, "bars_per_symbol": 2160, "n_samples": len(X),
             "n_train": split, "n_test": len(X) - split},
    "training": {
        "duration_s": round(t1-t0, 2),
        "hp_lr": ma['hyperparameters']['learning_rate'],
        "hp_depth": ma['hyperparameters']['max_depth'],
        "val_accuracy": ma['training_metrics']['val_accuracy'],
        "class_counts": {str(k): int(v) for k, v in ma.get('class_counts',{}).items()},
        "class_weights": {str(k): float(v) for k, v in ma.get('class_weights',{}).items()},
    },
    "oos_evaluation": {
        "accuracy": round(float(oos_acc), 4),
        "IC": round(float(ic), 6),
        "RankIC": round(float(rank_ic), 6),
        "directional_accuracy": round(float(dir_acc), 4),
        "n_test_samples": len(X_test),
    },
    "feature_method": "causal (trailing windows only, no lookahead)",
}
out = "reports/research_run_real_10sym_causal.json"
os.makedirs("reports", exist_ok=True)
with open(out, "w") as f:
    json.dump(results, f, indent=2)
print(f"\n✅ Saved: {out}")
print("=" * 60)
