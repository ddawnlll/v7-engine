#!/usr/bin/env python3
"""v0.31E — Directional Candidate v0.2: Symmetric Direction Balance.

One change from v0.1: fold-local class/sample weights so LONG/SHORT
errors are penalized symmetrically. Everything else identical.

v0.1 problem: LONG=44.9%, SHORT=57.8% (unbalanced)
v0.2 target:  LONG>=48%, SHORT>=53%, balanced_acc>=52%
"""
import json, sys, time
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

MODE = "SCALP"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
INTERVAL = "1h"
N_FOLDS = 6
CANDIDATE_ID = "ALPHAFORCE_SCALP_1H_DIRECTION_V02"
REPORT_DIR = REPO / "reports" / "candidates"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── 1-4: Identical to v0.1 ──
print(f"{'='*70}\n  {CANDIDATE_ID}\n{'='*70}")
ohlcv = load_cached_data(SYMBOLS, INTERVAL)
y_int, gross_r, net_r, _ = generate_labels(ohlcv, MODE)
X, feat_names = compute_features_selected(ohlcv, MODE)
cut = min(X.shape[0], len(y_int))
X, y_int, net_r = X[:cut], y_int[:cut], net_r[:cut]
nan_mask = np.isnan(X).any(axis=1)
X, y_int, net_r = X[~nan_mask], y_int[~nan_mask], net_r[~nan_mask]
dir_mask = y_int < 2
X, y_int, net_r = X[dir_mask], y_int[dir_mask], net_r[dir_mask]
print(f"  Direction samples: {len(X)} (LONG={int((y_int==0).sum())} SHORT={int((y_int==1).sum())})")

# ── 5: WFV with class weights ──
n = len(X)
fold_size = n // (N_FOLDS + 1)
fold_results = []
train_accs, val_accs = [], []
all_true, all_pred, all_net_r = [], [], []

print(f"\n[WFV] {N_FOLDS} folds with class weighting...\n")
t0 = time.time()

for fold in range(N_FOLDS):
    train_end = (fold + 1) * fold_size
    val_start = train_end
    val_end = val_start + fold_size // 2
    if val_end >= n: break
    purge = fold_size // 4
    embargo = fold_size // 8
    eff_tr_end = train_end - purge
    eff_va_start = val_start + embargo
    if eff_tr_end <= 0 or eff_va_start >= val_end: break

    X_tr = X[:eff_tr_end]
    y_tr = y_int[:eff_tr_end]
    X_va = X[eff_va_start:val_end]
    y_va = y_int[eff_va_start:val_end]
    net_va = net_r[eff_va_start:val_end]

    # --- Class weights: inverse frequency, fold-local ---
    n_long = int((y_tr == 0).sum())
    n_short = int((y_tr == 1).sum())
    if n_long > 0 and n_short > 0:
        weight_scale = (n_long + n_short) / 2  # geometric mean target
        sample_weights = np.where(y_tr == 0, weight_scale / n_long, weight_scale / n_short)
        sample_weights = sample_weights / sample_weights.mean()  # normalize
    else:
        sample_weights = np.ones(len(y_tr))

    trainer = XGBoostTrainer(mode=MODE)
    # Use weighted DMatrix for symmetric class loss
    dtrain = xgb.DMatrix(X_tr, label=y_tr, weight=sample_weights)
    dval = xgb.DMatrix(X_va, label=y_va)
    params = trainer._extract_xgb_params()
    params["objective"] = "multi:softprob"
    params["num_class"] = 2
    params["eval_metric"] = "mlogloss"
    booster = xgb.train(params, dtrain, num_boost_round=200,
                         evals=[(dval, "val")], verbose_eval=False)
    probs = booster.predict(dval)
    preds = np.argmax(probs, axis=1)

    # Compute train accuracy from weighted model
    d_train_pred = xgb.DMatrix(X_tr)
    train_preds = np.argmax(booster.predict(d_train_pred), axis=1)
    train_acc = float(np.mean(train_preds == y_tr))
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
        "fold": fold + 1, "n_train": len(X_tr), "n_val": len(X_va),
        "train_accuracy": round(train_acc, 4), "val_accuracy": round(val_acc, 4),
        "long_accuracy": round(long_acc, 4), "short_accuracy": round(short_acc, 4),
        "net_r_mean": round(net_r_fold, 6),
        "sample_weights": {"long": round(float(sample_weights[y_tr == 0].mean()) if n_long > 0 else 0, 4),
                           "short": round(float(sample_weights[y_tr == 1].mean()) if n_short > 0 else 0, 4)},
    })
    print(f"  Fold {fold+1}: acc={val_acc:.4f} LONG={long_acc:.4f} SHORT={short_acc:.4f} "
          f"weights(L={sample_weights[y_tr==0].mean():.2f}/S={sample_weights[y_tr==1].mean():.2f})")

wfv_time = time.time() - t0
all_true = np.array(all_true)
all_pred = np.array(all_pred)
all_net_r_arr = np.array(all_net_r)

# ── 6: Metrics ──
oos_acc = float(np.mean(all_pred == all_true))
oos_bal_acc = float((np.mean(all_pred[all_true==0]==all_true[all_true==0]) +
                     np.mean(all_pred[all_true==1]==all_true[all_true==1])) / 2)
oos_long_acc = float(np.mean(all_pred[all_true==0]==all_true[all_true==0])) if (all_true==0).sum()>0 else 0
oos_short_acc = float(np.mean(all_pred[all_true==1]==all_true[all_true==1])) if (all_true==1).sum()>0 else 0
correct = all_pred == all_true
net_r_mean = float(np.mean(all_net_r_arr[correct])) if correct.sum()>0 else 0
net_r_sum = float(all_net_r_arr[correct].sum()) if correct.sum()>0 else 0
cm = np.zeros((2,2), dtype=int)
for t,p in zip(all_true, all_pred):
    if 0<=t<2 and 0<=p<2: cm[t,p] += 1
mean_val = float(np.mean(val_accs))
std_val = float(np.std(val_accs))
fold_stab = 1 - std_val/max(mean_val,0.001)
n_total = len(all_true)
n_long_true = int((all_true==0).sum())
n_short_true = int((all_true==1).sum())
maj_baseline = max(n_long_true, n_short_true)/n_total
pos_r = all_net_r_arr[all_net_r_arr>0].sum() if all_net_r_arr[all_net_r_arr>0].sum()>0 else 0.001
neg_r = abs(all_net_r_arr[all_net_r_arr<0].sum()) if all_net_r_arr[all_net_r_arr<0].sum()<0 else 0.001
pf = float(pos_r/neg_r) if neg_r>0 else 0

spec = DatasetSpec(dataset_id=CANDIDATE_ID, source="binance", market="um_futures",
    symbols=tuple(SYMBOLS), intervals=(INTERVAL,), data_types=("klines",),
    start=datetime(2023,1,1,tzinfo=timezone.utc), end=datetime.now(timezone.utc))
cat = DataCatalog()
passport = DataPassport.from_spec(spec, cat)

# ── 7: Report ──
v01_path = REPORT_DIR / "alphaforge_scalp_1h_direction_v01.json"
v01 = json.loads(v01_path.read_text()) if v01_path.exists() else None
v01_acc = v01["metrics"]["oos_accuracy"] if v01 else 0
v01_bal = v01["metrics"]["oos_balanced_accuracy"] if v01 else 0
v01_long = v01["metrics"]["oos_long_accuracy"] if v01 else 0
v01_short = v01["metrics"]["oos_short_accuracy"] if v01 else 0
v01_netr = v01["metrics"]["oos_net_r_mean"] if v01 else 0
v01_stab = v01["metrics"]["fold_stability"] if v01 else 0

print(f"\n{'='*70}")
print(f"  {CANDIDATE_ID}")
print(f"{'='*70}")
print(f"  Metric              v0.1        v0.2        Δ")
print(f"  ───────────────────────────────────────────────────")
print(f"  OOS Accuracy        {v01_acc:.4f}    {oos_acc:.4f}    {oos_acc-v01_acc:+.4f}")
print(f"  Balanced Acc        {v01_bal:.4f}    {oos_bal_acc:.4f}    {oos_bal_acc-v01_bal:+.4f}")
print(f"  LONG Acc            {v01_long:.4f}    {oos_long_acc:.4f}    {oos_long_acc-v01_long:+.4f}")
print(f"  SHORT Acc           {v01_short:.4f}    {oos_short_acc:.4f}    {oos_short_acc-v01_short:+.4f}")
print(f"  Net R (mean)        {v01_netr:.6f}  {net_r_mean:.6f}  {net_r_mean-v01_netr:+.6f}")
print(f"  Fold Stability      {v01_stab:.4f}    {fold_stab:.4f}    {fold_stab-v01_stab:+.4f}")
print(f"  Beats random:       YES         {'YES' if oos_acc>0.5 else 'NO'}")
print(f"  Beats majority:     {'YES' if v01_acc>maj_baseline else 'NO'}         {'YES' if oos_acc>maj_baseline else 'NO'}")

results = {"candidate_id": CANDIDATE_ID,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "v7_status": "RESEARCH_ONLY / NOT_READY",
    "config": {"mode": MODE, "interval": INTERVAL, "symbols": SYMBOLS,
               "n_folds": N_FOLDS, "target": "2-class direction (weighted)",
               "confidence_threshold": "DISABLED",
               "change_from_v01": "fold-local class weighting for symmetric LONG/SHORT loss"},
    "metrics": {"oos_accuracy": round(oos_acc,4), "oos_balanced_accuracy": round(oos_bal_acc,4),
                "oos_long_accuracy": round(oos_long_acc,4), "oos_short_accuracy": round(oos_short_acc,4),
                "train_accuracy_mean": round(float(np.mean(train_accs)),4),
                "train_oos_gap": round(float(np.mean(train_accs))-oos_acc,4),
                "oos_net_r_mean": round(net_r_mean,6), "oos_net_r_sum": round(net_r_sum,4),
                "oos_profit_factor": round(pf,4), "active_trade_count": n_total,
                "fold_stability": round(fold_stab,4),
                "baselines": {"random_direction": 0.5, "majority_direction": round(maj_baseline,4)},
                "baseline_defeat_random": oos_acc>0.5, "baseline_defeat_majority": oos_acc>maj_baseline},
    "comparison_v01": {"delta_accuracy": round(oos_acc-v01_acc,4),
                       "delta_balanced_accuracy": round(oos_bal_acc-v01_bal,4),
                       "delta_long_accuracy": round(oos_long_acc-v01_long,4),
                       "delta_short_accuracy": round(oos_short_acc-v01_short,4),
                       "delta_net_r_mean": round(net_r_mean-v01_netr,6),
                       "delta_fold_stability": round(fold_stab-v01_stab,4)},
    "confusion_matrix": cm.tolist(), "fold_results": fold_results,
    "data_passport": passport.to_dict()}

json_path = REPORT_DIR / f"{CANDIDATE_ID.lower()}.json"
json_path.write_text(json.dumps(results, indent=2, default=str))

md = [
    f"# {CANDIDATE_ID}",
    f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    "**Status:** RESEARCH_CANDIDATE — NOT V7_READY",
    "",
    "## Change from v0.1",
    "Fold-local inverse-frequency class weights so LONG/SHORT errors penalized symmetrically.",
    "",
    "## Comparison",
    "| Metric | v0.1 | v0.2 | Δ | Target |",
    "|--------|------|------|---|--------|",
    f"| OOS Accuracy | {v01_acc:.4f} | {oos_acc:.4f} | {oos_acc-v01_acc:+.4f} | > v0.1 |",
    f"| Balanced Acc | {v01_bal:.4f} | {oos_bal_acc:.4f} | {oos_bal_acc-v01_bal:+.4f} | >= 52% |",
    f"| LONG Acc | {v01_long:.4f} | {oos_long_acc:.4f} | {oos_long_acc-v01_long:+.4f} | >= 48% |",
    f"| SHORT Acc | {v01_short:.4f} | {oos_short_acc:.4f} | {oos_short_acc-v01_short:+.4f} | >= 53% |",
    f"| Net R (mean) | {v01_netr:.6f} | {net_r_mean:.6f} | {net_r_mean-v01_netr:+.6f} | >= v0.1 |",
    f"| Fold Stability | {v01_stab:.4f} | {fold_stab:.4f} | {fold_stab-v01_stab:+.4f} | high |",
    "",
    "## Confusion Matrix",
    "| True \\\\ Pred | LONG | SHORT |",
    "|-------------|------|-------|",
    f"| LONG       | {cm[0,0]:>6} | {cm[0,1]:>6} |",
    f"| SHORT      | {cm[1,0]:>6} | {cm[1,1]:>6} |",
    "",
]
(REPORT_DIR / f"{CANDIDATE_ID.lower()}.md").write_text("\n".join(md))
print(f"\n  Reports saved.")
print(f"\n{'='*70}")
