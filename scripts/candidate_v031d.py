#!/usr/bin/env python3
"""v0.31D — Directional Alpha Candidate v0.1.

Turns v0.31B research finding into the first real AlphaForge candidate.

Changes from baseline:
  - 2-class target: LONG vs SHORT only (NO_TRADE removed from supervision)
  - Confidence threshold disabled (calibration proved it useless)
  - Everything else IDENTICAL to baseline

No tuning. No features changed. No model params changed.
"""
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alphaforge" / "src"))
sys.path.insert(0, str(REPO))

from alphaforge.train import load_cached_data, generate_labels, compute_features_selected
from alphaforge.training.xgb_trainer import XGBoostTrainer
from lib.data_lake.passport import DataPassport
from lib.data_lake.spec import DatasetSpec
from lib.data_lake.catalog import DataCatalog
import xgboost as xgb

# ── Config identical to baseline ──
MODE = "SCALP"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
INTERVAL = "1h"
N_FOLDS = 6

CANDIDATE_ID = "ALPHAFORGE_SCALP_1H_DIRECTION_V01"
OUTPUT_DIR = REPO / "artifacts" / "models" / "scalp_1h_direction_v01"
REPORT_DIR = REPO / "reports" / "candidates"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"{'='*70}")
print(f"  {CANDIDATE_ID}")
print(f"  Directional Alpha Candidate v0.1")
print(f"{'='*70}")

# ── 1. Load data ──
print("\n[1/7] Loading data...")
ohlcv = load_cached_data(SYMBOLS, INTERVAL)
assert ohlcv is not None, "No data loaded"
print(f"  Bars: {len(ohlcv['close'])}")

# ── 2. Generate labels ──
print("\n[2/7] Generating labels...")
y_int, gross_r, net_r, label_metrics = generate_labels(ohlcv, MODE)
dist = dict(Counter(y_int.tolist()))
print(f"  All labels: {dist}")
n_long = int((y_int == 0).sum())
n_short = int((y_int == 1).sum())
n_nt = int((y_int == 2).sum())
print(f"  LONG={n_long} SHORT={n_short} NO_TRADE={n_nt}")

# ── 3. Compute features ──
print("\n[3/7] Computing features...")
X, feat_names = compute_features_selected(ohlcv, MODE)
cut = min(X.shape[0], len(y_int))
X, y_int = X[:cut], y_int[:cut]
net_r = net_r[:cut]
nan_mask = np.isnan(X).any(axis=1)
X, y_int = X[~nan_mask], y_int[~nan_mask]
net_r = net_r[~nan_mask]
print(f"  Features: {X.shape[1]}, Samples: {len(X)}")

# ── 4. Filter to direction-only (NO_TRADE removed) ──
print("\n[4/7] Filtering to direction-only (NO_TRADE removed)...")
dir_mask = y_int < 2
X_dir = X[dir_mask]
y_dir = y_int[dir_mask]
net_r_dir = net_r[dir_mask]
n_removed = (~dir_mask).sum()
print(f"  Direction samples: {len(X_dir)} ({n_removed} NO_TRADE removed)")
print(f"  LONG={int((y_dir==0).sum())} SHORT={int((y_dir==1).sum())}")
print(f"  Class ratio: {int((y_dir==0).sum())/len(X_dir):.3f} / {int((y_dir==1).sum())/len(X_dir):.3f}")

# ── 5. Walk-forward validation (no confidence threshold) ──
print(f"\n[5/7] Walk-forward validation ({N_FOLDS} folds, no confidence threshold)...")
n = len(X_dir)
fold_size = n // (N_FOLDS + 1)
fold_results = []
train_accs, val_accs = [], []
all_true, all_pred, all_net_r = [], [], []
t0 = time.time()

for fold in range(N_FOLDS):
    train_end = (fold + 1) * fold_size
    val_start = train_end
    val_end = val_start + fold_size // 2
    if val_end >= n:
        break
    purge = fold_size // 4
    embargo = fold_size // 8
    eff_train_end = train_end - purge
    eff_val_start = val_start + embargo
    if eff_train_end <= 0 or eff_val_start >= val_end:
        break

    X_tr = X_dir[:eff_train_end]
    y_tr = y_dir[:eff_train_end]
    X_va = X_dir[eff_val_start:val_end]
    y_va = y_dir[eff_val_start:val_end]
    net_va = net_r_dir[eff_val_start:val_end]

    trainer = XGBoostTrainer(mode=MODE)
    result = trainer.train(X_tr, y_tr)
    dval = xgb.DMatrix(X_va)
    probs = result.model.predict(dval)
    preds = np.argmax(probs, axis=1)

    train_acc = float(result.train_metrics.get("accuracy", 0))
    val_acc = float(np.mean(preds == y_va))
    long_acc = float(np.mean(preds[y_va == 0] == y_va[y_va == 0])) if (y_va == 0).sum() > 0 else 0
    short_acc = float(np.mean(preds[y_va == 1] == y_va[y_va == 1])) if (y_va == 1).sum() > 0 else 0
    net_r_fold = float(np.mean(net_va[preds == y_va])) if (preds == y_va).sum() > 0 else 0

    train_accs.append(train_acc)
    val_accs.append(val_acc)
    all_true.extend(y_va.tolist())
    all_pred.extend(preds.tolist())
    all_net_r.extend(net_va.tolist())

    fold_results.append({
        "fold": fold + 1,
        "n_train": len(X_tr),
        "n_val": len(X_va),
        "train_accuracy": round(train_acc, 4),
        "val_accuracy": round(val_acc, 4),
        "long_accuracy": round(long_acc, 4),
        "short_accuracy": round(short_acc, 4),
        "net_r_mean": round(net_r_fold, 6),
        "active_trades": len(y_va),
    })
    print(f"  Fold {fold+1}: train={len(X_tr)} val={len(X_va)} "
          f"acc={val_acc:.4f} LONG={long_acc:.4f} SHORT={short_acc:.4f} net_R={net_r_fold:.6f}")

wfv_time = time.time() - t0
all_true = np.array(all_true)
all_pred = np.array(all_pred)
all_net_r_arr = np.array(all_net_r)

# ── 6. Aggregate metrics ──
print(f"\n[6/7] Computing aggregate metrics...")
oos_acc = float(np.mean(all_pred == all_true))
oos_bal_acc = float((np.mean(all_pred[all_true == 0] == all_true[all_true == 0]) +
                     np.mean(all_pred[all_true == 1] == all_true[all_true == 1])) / 2)
oos_long_acc = float(np.mean(all_pred[all_true == 0] == all_true[all_true == 0])) if (all_true == 0).sum() > 0 else 0
oos_short_acc = float(np.mean(all_pred[all_true == 1] == all_true[all_true == 1])) if (all_true == 1).sum() > 0 else 0
correct = all_pred == all_true
net_r_mean = float(np.mean(all_net_r_arr[correct])) if correct.sum() > 0 else 0
net_r_sum = float(all_net_r_arr[correct].sum()) if correct.sum() > 0 else 0

# Confusion matrix
cm = np.zeros((2, 2), dtype=int)
for t, p in zip(all_true, all_pred):
    if 0 <= t < 2 and 0 <= p < 2:
        cm[t, p] += 1

# Fold stability
mean_val = float(np.mean(val_accs))
std_val = float(np.std(val_accs))
fold_stability = 1 - std_val / max(mean_val, 0.001)

# Baselines
n_total = len(all_true)
n_long_true = int((all_true == 0).sum())
n_short_true = int((all_true == 1).sum())
majority_baseline = max(n_long_true, n_short_true) / n_total
random_baseline = 0.50

# Net profit factor (simplified)
positive_r = all_net_r_arr[all_net_r_arr > 0].sum() if all_net_r_arr[all_net_r_arr > 0].sum() > 0 else 0.001
negative_r = abs(all_net_r_arr[all_net_r_arr < 0].sum()) if all_net_r_arr[all_net_r_arr < 0].sum() < 0 else 0.001
profit_factor = float(positive_r / negative_r) if negative_r > 0 else 0

# ── DataPassport ──
spec = DatasetSpec(
    dataset_id=CANDIDATE_ID,
    source="binance", market="um_futures",
    symbols=tuple(SYMBOLS),
    intervals=(INTERVAL,),
    data_types=("klines",),
    start=datetime(2023, 1, 1, tzinfo=timezone.utc),
    end=datetime.now(timezone.utc),
)
cat = DataCatalog()
passport = DataPassport.from_spec(spec, cat)

# ── Results ──
results = {
    "candidate_id": CANDIDATE_ID,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "v7_status": "RESEARCH_ONLY / NOT_READY",
    "config": {
        "mode": MODE,
        "interval": INTERVAL,
        "symbols": SYMBOLS,
        "n_folds": N_FOLDS,
        "target": "2-class direction (LONG vs SHORT)",
        "confidence_threshold": "DISABLED",
        "no_trade_treatment": "REMOVED_FROM_SUPERVISION",
        "features": len(feat_names),
    },
    "metrics": {
        "oos_accuracy": round(oos_acc, 4),
        "oos_balanced_accuracy": round(oos_bal_acc, 4),
        "oos_long_accuracy": round(oos_long_acc, 4),
        "oos_short_accuracy": round(oos_short_acc, 4),
        "train_accuracy_mean": round(float(np.mean(train_accs)), 4),
        "train_oos_gap": round(float(np.mean(train_accs) - oos_acc), 4),
        "oos_net_r_mean": round(net_r_mean, 6),
        "oos_net_r_sum": round(net_r_sum, 4),
        "oos_profit_factor": round(profit_factor, 4),
        "active_trade_count": n_total,
        "fold_stability": round(fold_stability, 4),
        "baselines": {
            "random_direction": random_baseline,
            "majority_direction": round(majority_baseline, 4),
        },
        "baseline_defeat_random": oos_acc > random_baseline,
        "baseline_defeat_majority": oos_acc > majority_baseline,
    },
    "confusion_matrix": cm.tolist(),
    "fold_results": fold_results,
    "data_passport": passport.to_dict(),
}

# Print summary
print(f"\n{'='*70}")
print(f"  {CANDIDATE_ID}")
print(f"{'='*70}")
print(f"  OOS Accuracy:          {oos_acc:.4f}")
print(f"  OOS Balanced Acc:      {oos_bal_acc:.4f}")
print(f"  OOS LONG Acc:          {oos_long_acc:.4f}")
print(f"  OOS SHORT Acc:         {oos_short_acc:.4f}")
print(f"  Train/OOS Gap:         {float(np.mean(train_accs))-oos_acc:.4f}")
print(f"  Net R (mean):          {net_r_mean:.6f}")
print(f"  Net R (sum):           {net_r_sum:.4f}")
print(f"  Profit Factor:         {profit_factor:.4f}")
print(f"  Active Trades:         {n_total}")
print(f"  Fold Stability:        {fold_stability:.4f}")
print(f"  WFV Time:              {wfv_time:.1f}s")
print(f"  Random baseline:       {random_baseline}")
print(f"  Majority baseline:     {majority_baseline:.4f}")
print(f"  Beats random:          {oos_acc > random_baseline}")
print(f"  Beats majority:        {oos_acc > majority_baseline}")
print(f"  V7 Status:             RESEARCH_ONLY / NOT_READY")

# Confusion matrix
print(f"\n  Confusion Matrix:")
print(f"           Pred LONG  Pred SHORT")
print(f"  True LONG   {cm[0,0]:>6}   {cm[0,1]:>6}")
print(f"  True SHORT  {cm[1,0]:>6}   {cm[1,1]:>6}")

# Passport
print(f"\n  DataPassport:")
print(f"    Source:      {passport.source}")
print(f"    Real data:   {passport.is_real_data}")
print(f"    Coverage:    {passport.coverage_pct:.1f}%")
print(f"    Backtest OK: {passport.is_trustworthy_for_backtest()}")

# ── 7. Save artifacts ──
print(f"\n[7/7] Saving artifacts...")

# JSON report
json_path = REPORT_DIR / f"{CANDIDATE_ID.lower()}.json"
json_path.write_text(json.dumps(results, indent=2, default=str))
print(f"  Report: {json_path}")

# Markdown report
md_lines = [
    f"# {CANDIDATE_ID}",
    "",
    f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    f"**Status:** RESEARCH_CANDIDATE — NOT V7_READY, NOT PAPER_READY, NOT LIVE_READY",
    "",
    "## Architecture Change",
    "",
    "| Change | Before | After | Evidence |",
    "|--------|--------|-------|----------|",
    "| Target | 3-class (LONG/SHORT/NO_TRADE) | 2-class (LONG vs SHORT) | NO_TRADE balanced acc = 50.01% (random) |",
    "| Confidence threshold | 0.55 | DISABLED | Flat calibration curve, 0.5% gain for 91% trade loss |",
    "| NO_TRADE treatment | Supervised class | REMOVED from direction training | Actionability model confirmed unlearnable |",
    "",
    "## Config",
    f"| Param | Value |",
    f"|-------|-------|",
    f"| Mode | {MODE} |",
    f"| Interval | {INTERVAL} |",
    f"| Symbols | {SYMBOLS} |",
    f"| WFV folds | {N_FOLDS} |",
    f"| Features | {len(feat_names)} |",
    f"| Model | XGBoost depth=4, 200 trees |",
    "",
    "## Results",
    f"| Metric | Value | vs Random | vs Majority |",
    f"|--------|-------|-----------|-------------|",
    f"| OOS Accuracy | {oos_acc:.4f} | {'BEATS' if oos_acc > random_baseline else 'BELOW'} ({random_baseline}) | {'BEATS' if oos_acc > majority_baseline else 'BELOW'} ({majority_baseline:.4f}) |",
    f"| Balanced Acc | {oos_bal_acc:.4f} | | |",
    f"| LONG Accuracy | {oos_long_acc:.4f} | | |",
    f"| SHORT Accuracy | {oos_short_acc:.4f} | | |",
    f"| Train/OOS Gap | {float(np.mean(train_accs))-oos_acc:.4f} | | |",
    f"| Net R (mean) | {net_r_mean:.6f} | | |",
    f"| Net R (sum) | {net_r_sum:.4f} | | |",
    f"| Profit Factor | {profit_factor:.4f} | | |",
    f"| Fold Stability | {fold_stability:.4f} | | |",
    f"| Active Trades | {n_total} | | |",
    "",
    "## Confusion Matrix",
    "",
    "| True \\\\ Pred | LONG | SHORT |",
    "|-------------|------|-------|",
    f"| LONG       | {cm[0,0]:>6} | {cm[0,1]:>6} |",
    f"| SHORT      | {cm[1,0]:>6} | {cm[1,1]:>6} |",
    "",
    "## Per-Fold",
    "| Fold | Train | Val | Train Acc | Val Acc | LONG Acc | SHORT Acc | Net R |",
    "|------|-------|-----|-----------|---------|----------|-----------|-------|",
]
for fr in fold_results:
    md_lines.append(
        f"| {fr['fold']} | {fr['n_train']} | {fr['n_val']} | "
        f"{fr['train_accuracy']:.4f} | {fr['val_accuracy']:.4f} | "
        f"{fr['long_accuracy']:.4f} | {fr['short_accuracy']:.4f} | "
        f"{fr['net_r_mean']:.6f} |"
    )

md_lines += [
    "",
    "## DataPassport",
    f"- Source: {passport.source}",
    f"- Real data: {passport.is_real_data}",
    f"- PIT safe: {passport.point_in_time_safe}",
    f"- Coverage: {passport.coverage_pct:.1f}%",
    f"- Backtest trustworthy: {passport.is_trustworthy_for_backtest()}",
    "",
    "## V7 Status",
    "",
    "**RESEARCH_CANDIDATE** — This candidate is NOT ready for V7 gates.",
    "",
    "| Gate | Status | Reason |",
    "|------|--------|--------|",
    "| V7_READY | ❌ | Research candidate, not production-ready |",
    "| PAPER_READY | ❌ | Requires V7 promotion gate evidence |",
    "| LIVE_READY | ❌ | Requires paper trading validation |",
    "",
    "## Next Candidate Iteration (v0.31E)",
    "",
    "One improvement from:",
    "- Feature reduction (feature-family ablation)",
    "- Regularization (shallower trees, fewer estimators)",
    "- Funding cost correction with real funding rate data",
    "",
]
md_path = REPORT_DIR / f"{CANDIDATE_ID.lower()}.md"
md_path.write_text("\n".join(md_lines))
print(f"  Report: {md_path}")

# Serialize model artifacts
artifacts = {
    "candidate_id": CANDIDATE_ID,
    "metrics": results["metrics"],
    "fold_results": fold_results,
    "config": results["config"],
    "data_passport": passport.to_dict(),
    "feature_names": feat_names,
}
art_path = OUTPUT_DIR / "candidate_artifacts.json"
art_path.write_text(json.dumps(artifacts, indent=2, default=str))
print(f"  Artifacts: {art_path}")

print(f"\n{'='*70}")
print(f"  Candidate locked: {CANDIDATE_ID}")
print(f"{'='*70}")
