"""AlphaForge Profitability v0.1 — A/B Karşılaştırma Scripti

Baseline (eski feature'lar):
  RETURNS, VOLATILITY, ATR, MOMENTUM, VOLUME, BREAKOUT

New (yeni feature'lar):
  + ORDERBOOK (OBI, OBI_N, OFI, VAMP, spread, volume HHI, micro-price)
  + REGIME (OnlineRegimeDetector: CUSUM + HMM)
  + CANDLE_PATTERN (10+ multi-bar pattern)

Kullanım:
  PYTHONPATH=alphaforge/src python3 scripts/ab_comparison.py
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import xgboost as xgb

# Load cached data from pipeline
sys.path.insert(0, ".")
sys.path.insert(0, "alphaforge/src")

from alphaforge.features.pipeline import (
    FeatureGroup,
    FeatureMatrix,
    PIPELINE_VERSION,
    compute_features,
)
from alphaforge.train import generate_synthetic_ohlcv
from alphaforge.training.xgb_trainer import XGBoostTrainer, SWING_DEFAULT_HYPERPARAMS
from alphaforge.validation.walk_forward_runner import (
    run_walk_forward,
    MODE_ANNUALIZATION,
)

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------

MODE = "SWING"
N_BARS = 5000
N_SYMBOLS = 3
RANDOM_SEED = 42

BASELINE_EXCLUDED = {
    FeatureGroup.LEAD_LAG,
    FeatureGroup.PERPETUAL_FUNDING,
    FeatureGroup.ORDERBOOK,
    FeatureGroup.REGIME,
    FeatureGroup.CANDLE_PATTERN,
}

NEW_EXCLUDED = {
    FeatureGroup.LEAD_LAG,
    FeatureGroup.PERPETUAL_FUNDING,
}

BASELINE_GROUPS = [g.value for g in FeatureGroup if g not in BASELINE_EXCLUDED]
NEW_GROUPS = [g.value for g in FeatureGroup if g not in NEW_EXCLUDED]

print("=" * 80)
print("AlphaForge Profitability v0.1 — A/B Comparison")
print("=" * 80)
print(f"Mode: {MODE} | Bars: {N_BARS} | Symbols: {N_SYMBOLS}")
print(f"Pipeline version: {PIPELINE_VERSION}")
print()

# -------------------------------------------------------------------
# Generate data
# -------------------------------------------------------------------

np.random.seed(RANDOM_SEED)

print("Generating synthetic OHLCV data...")
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
data = {}
for sym in symbols:
    data[sym] = generate_synthetic_ohlcv(N_BARS)

print(f"  {N_BARS} bars × {len(symbols)} symbols = {N_BARS * len(symbols)} total bars")
print()

# -------------------------------------------------------------------
# Compute features — BASELINE
# -------------------------------------------------------------------

print("-" * 80)
print("BASELINE: Feature groups =", ", ".join(sorted(BASELINE_GROUPS)))
print("-" * 80)

baseline_matrices = {}
baseline_time = time.time()

for sym in symbols:
    mat = compute_features(data[sym], mode=MODE)
    # Override feature_group_ids to exclude new groups
    mat.feature_group_ids = [g for g in mat.feature_group_ids if g in BASELINE_GROUPS]
    # Remove new feature columns
    new_prefixes = ("obi_", "multi_level_obi_", "ofi_", "vamp_", "quoted_spread_",
                    "vwap_mid_deviation_", "trade_count_", "volume_concentration_hhi_",
                    "stoikov_micro_price_", "microprice_", "depth_ratio_",
                    "liquidity_vacuum_", "spread_pct_", "volume_imbalance_",
                    "trade_intensity_", "amihud_", "roll_spread_", "microstructure_",
                    "serial_correlation_", "vpin_", "price_impact_",
                    "cusum_", "hmm_", "volatility_regime",
                    "doji_", "hammer_", "gap_", "consecutive_", "lowest_", "highest_",
                    "roc_", "candle_")
    filtered = {}
    for name, arr in mat.features.items():
        if not any(name.startswith(p) for p in new_prefixes):
            filtered[name] = arr
    mat.features = filtered
    print(f"  {sym}: {len(filtered)} features (removed {len(mat.features) - len(filtered)})")
    baseline_matrices[sym] = mat

baseline_time = time.time() - baseline_time
print(f"  Time: {baseline_time:.2f}s")
print()

# -------------------------------------------------------------------
# Compute features — NEW (all)
# -------------------------------------------------------------------

print("-" * 80)
print("NEW: Feature groups =", ", ".join(sorted(NEW_GROUPS)))
print("-" * 80)

new_matrices = {}
new_time = time.time()

for sym in symbols:
    mat = compute_features(data[sym], mode=MODE)
    new_matrices[sym] = mat
    print(f"  {sym}: {mat.total_features()} features")
    # Print new features
    new_prefixes = ("obi_", "multi_level_obi_", "ofi_", "vamp_", "quoted_spread_",
                    "vwap_mid_deviation_", "trade_count_", "volume_concentration_hhi_",
                    "stoikov_micro_price_", "microprice_", "depth_ratio_",
                    "liquidity_vacuum_", "spread_pct_", "volume_imbalance_",
                    "trade_intensity_", "amihud_", "roll_spread_", "microstructure_",
                    "serial_correlation_", "vpin_", "price_impact_",
                    "cusum_", "hmm_", "volatility_regime",
                    "doji_", "hammer_", "gap_", "consecutive_", "lowest_", "highest_",
                    "roc_", "candle_")
    new_feats = [n for n in mat.features if any(n.startswith(p) for p in new_prefixes)]
    print(f"  New features: {len(new_feats)}")
    if new_feats:
        print(f"    {', '.join(sorted(new_feats)[:10])}...")

new_time = time.time() - new_time
print(f"  Time: {new_time:.2f}s")
print()

# -------------------------------------------------------------------
# Train + Evaluate — BASELINE
# -------------------------------------------------------------------

def train_and_eval(matrices, label, mode=MODE):
    """Train XGBoost on stacked symbol matrices, return metrics."""
    # Stack all symbols
    all_X = []
    all_y = []
    for sym in sorted(matrices.keys()):
        mat = matrices[sym]
        # Generate simple labels: forward return sign
        close = data[sym]["close"]
        forward_ret = np.roll(close, -6) - close
        y = np.zeros(len(close), dtype=np.int32)
        y[forward_ret > 0.005] = 0  # LONG_NOW
        y[forward_ret < -0.005] = 1  # SHORT_NOW
        y[np.abs(forward_ret) <= 0.005] = 2  # NO_TRADE

        # Build X from features
        feat_names = sorted(mat.features.keys())
        X = np.column_stack([mat.features[n] for n in feat_names])
        # NaN handling
        X = np.nan_to_num(X, nan=0.0)
        all_X.append(X)
        all_y.append(y)

    X = np.vstack(all_X)
    y = np.concatenate(all_y)

    # Split (80/20 chronological)
    split = int(len(X) * 0.8)

    train_X, val_X = X[:split], X[split:]
    train_y, val_y = y[:split], y[split:]

    dtrain = xgb.DMatrix(train_X, label=train_y)
    dval = xgb.DMatrix(val_X, label=val_y)

    params = dict(SWING_DEFAULT_HYPERPARAMS)
    params["num_class"] = 3
    params["seed"] = RANDOM_SEED

    # Train
    model = xgb.train(params, dtrain, num_boost_round=200,
                      evals=[(dtrain, "train"), (dval, "val")],
                      early_stopping_rounds=20, verbose_eval=False)

    # Metrics
    train_pred = model.predict(dtrain)
    val_pred = model.predict(dval)
    train_acc = np.mean(train_pred.argmax(axis=1) == train_y)
    val_acc = np.mean(val_pred.argmax(axis=1) == val_y)

    # Feature importance
    importance = model.get_score(importance_type="total_gain")
    top_features = sorted(importance.items(), key=lambda x: -x[1])[:10]

    # Per-class precision
    from sklearn.metrics import precision_recall_fscore_support
    prec, rec, f1, _ = precision_recall_fscore_support(val_y, val_pred.argmax(axis=1),
                                                       average=None, labels=[0, 1, 2])
    labels_map = {0: "LONG", 1: "SHORT", 2: "NO_TRADE"}

    return {
        "model": model,
        "train_acc": float(train_acc),
        "val_acc": float(val_acc),
        "accuracy_gap": float(train_acc - val_acc),
        "overfit_ratio": float(val_acc / train_acc) if train_acc > 0 else 0,
        "top_features": top_features,
        "n_features": X.shape[1],
        "n_train": train_X.shape[0],
        "n_val": val_X.shape[0],
        "per_class_precision": {labels_map[i]: float(prec[i]) for i in range(3)},
        "per_class_recall": {labels_map[i]: float(rec[i]) for i in range(3)},
        "per_class_f1": {labels_map[i]: float(f1[i]) for i in range(3)},
    }


print("=" * 80)
print(f"Training — Baseline ({', '.join(sorted(BASELINE_GROUPS))})")
print("=" * 80)
baseline_result = train_and_eval(baseline_matrices, "Baseline")
print(f"  Train accuracy:    {baseline_result['train_acc']:.4f}")
print(f"  Val accuracy:      {baseline_result['val_acc']:.4f}")
print(f"  Accuracy gap:      {baseline_result['accuracy_gap']:.4f}")
print(f"  Overfit ratio:     {baseline_result['overfit_ratio']:.4f}")
print(f"  Features:          {baseline_result['n_features']}")
print(f"  Train samples:     {baseline_result['n_train']}")
print(f"  Val samples:       {baseline_result['n_val']}")
print(f"  Top features:")
for name, score in baseline_result['top_features']:
    print(f"    {name}: {score:.1f}")
print()

print("=" * 80)
print(f"Training — NEW (all {len(NEW_GROUPS)} groups)")
print("=" * 80)
new_result = train_and_eval(new_matrices, "New")
print(f"  Train accuracy:    {new_result['train_acc']:.4f}")
print(f"  Val accuracy:      {new_result['val_acc']:.4f}")
print(f"  Accuracy gap:      {new_result['accuracy_gap']:.4f}")
print(f"  Overfit ratio:     {new_result['overfit_ratio']:.4f}")
print(f"  Features:          {new_result['n_features']}")
print(f"  Train samples:     {new_result['n_train']}")
print(f"  Val samples:       {new_result['n_val']}")
print(f"  Top features:")
for name, score in new_result['top_features']:
    print(f"    {name}: {score:.1f}")
print()

# -------------------------------------------------------------------
# COMPARISON TABLE
# -------------------------------------------------------------------

print()
print("▓" * 80)
print("▓  A/B COMPARISON — AlphaForge Profitability v0.1")
print("▓" * 80)
print()
print(f"{'Metric':<30} {'BASELINE':<20} {'NEW':<20} {'Δ':<15} {'IMPROVEMENT':<15}")
print(f"{'─'*30:<30} {'─'*20:<20} {'─'*20:<20} {'─'*15:<15} {'─'*15:<15}")

def delta_str(old, new, higher_is_better=True):
    diff = new - old
    sign = "+" if diff > 0 else ""
    pct = (diff / abs(old) * 100) if old != 0 else 0
    icon = "✅" if (higher_is_better and diff > 0) or (not higher_is_better and diff < 0) else "❌"
    return f"{sign}{diff:.4f} ({sign}{pct:.1f}%) {icon}"

metrics = [
    ("Val Accuracy", baseline_result['val_acc'], new_result['val_acc'], True),
    ("Train Accuracy", baseline_result['train_acc'], new_result['train_acc'], True),
    ("Accuracy Gap (overfit)", baseline_result['accuracy_gap'], new_result['accuracy_gap'], False),
    ("Overfit Ratio", baseline_result['overfit_ratio'], new_result['overfit_ratio'], True),
    ("# Features", baseline_result['n_features'], new_result['n_features'], True),
]

for name, old, new, hib in metrics:
    print(f"{name:<30} {old:<20.4f} {new:<20.4f} {delta_str(old, new, hib):<15}")

print()
print("Per-Class Precision:")
print(f"{'Class':<15} {'BASELINE':<15} {'NEW':<15} {'Δ':<15}")
print(f"{'─'*15:<15} {'─'*15:<15} {'─'*15:<15} {'─'*15:<15}")
for cls in ["LONG", "SHORT", "NO_TRADE"]:
    old_p = baseline_result['per_class_precision'][cls]
    new_p = new_result['per_class_precision'][cls]
    imp = "✅" if new_p > old_p else "❌"
    print(f"{cls:<15} {old_p:<15.4f} {new_p:<15.4f} {'+' if new_p>old_p else ''}{new_p-old_p:.4f} {imp}")

print()
print("Per-Class F1-Score:")
print(f"{'Class':<15} {'BASELINE':<15} {'NEW':<15} {'Δ':<15}")
print(f"{'─'*15:<15} {'─'*15:<15} {'─'*15:<15} {'─'*15:<15}")
for cls in ["LONG", "SHORT", "NO_TRADE"]:
    old_f = baseline_result['per_class_f1'][cls]
    new_f = new_result['per_class_f1'][cls]
    imp = "✅" if new_f > old_f else "❌"
    print(f"{cls:<15} {old_f:<15.4f} {new_f:<15.4f} {'+' if new_f>old_f else ''}{new_f-old_f:.4f} {imp}")

print()
print("Top-5 Features (Baseline):")
for i, (name, score) in enumerate(baseline_result['top_features'][:5]):
    print(f"  {i+1}. {name}: {score:.1f}")

print()
print("Top-5 Features (New):")
for i, (name, score) in enumerate(new_result['top_features'][:5]):
    is_new = any(name.startswith(p) for p in new_prefixes)
    marker = " 🆕" if is_new else ""
    print(f"  {i+1}. {name}: {score:.1f}{marker}")

print()
print("=" * 80)
print("SUMMARY")
print("=" * 80)

val_improved = new_result['val_acc'] > baseline_result['val_acc']
gap_reduced = new_result['accuracy_gap'] < baseline_result['accuracy_gap']
feature_count = new_result['n_features'] - baseline_result['n_features']

print(f"  Val accuracy:      {baseline_result['val_acc']:.4f} → {new_result['val_acc']:.4f} {'✅' if val_improved else '❌'}")
print(f"  Overfit gap:       {baseline_result['accuracy_gap']:.4f} → {new_result['accuracy_gap']:.4f} {'✅' if gap_reduced else '❌'}")
print(f"  New features:      +{feature_count}")
print(f"  Feature groups:    {len(BASELINE_GROUPS)} → {len(NEW_GROUPS)}")

if val_improved and gap_reduced:
    print()
    print("  🎉 AlphaForge Profitability v0.1: POSITIVE — accuracy arttı, overfit azaldı")
elif val_improved:
    print()
    print("  📈 AlphaForge Profitability v0.1: MIXED — accuracy arttı ama overfit de arttı")
elif gap_reduced:
    print()
    print("  📉 AlphaForge Profitability v0.1: MIXED — accuracy aynı/düşük ama overfit azaldı")
else:
    print()
    print("  📊 AlphaForge Profitability v0.1: NO CHANGE — sentetik veride sinyal yok")

print()
print(f"Pipeline version: {PIPELINE_VERSION}")
print(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
