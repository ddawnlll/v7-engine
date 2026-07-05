#!/usr/bin/env python3
"""v0.31A — Real-Data Model Failure Diagnostic.

Read-only: trains the model with the same config as the baseline
and extracts diagnostics for 6 reports. No config changes, no model
behavior modifications.

Reports produced:
  - label_audit          Are labels economically meaningful?
  - model_failure        Train vs OOS, fold stability
  - confidence_calibration  Does confidence predict performance?
  - threshold_frontier   read-only sweep (no change)
  - feature_ablation_plan  Which features carry signal?

Usage:
    PYTHONPATH=alphaforge/src:. python3 scripts/diagnostic_v031.py
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alphaforge" / "src"))
sys.path.insert(0, str(REPO))

from alphaforge.train import load_cached_data, generate_labels, compute_features_selected
from lib.data_lake.spec import DatasetSpec
from lib.data_lake.catalog import DataCatalog
from lib.data_lake.passport import DataPassport

MODE = "SCALP"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
INTERVAL = "1h"
N_FOLDS = 6
OUTPUT_DIR = REPO / "data" / "diagnostics"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def banner(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def train_and_collect():
    """Train the model (same config as baseline) and collect all diagnostic data."""
    banner("LOADING DATA")
    ohlcv = load_cached_data(SYMBOLS, INTERVAL)
    if ohlcv is None:
        print("FATAL: No data loaded")
        sys.exit(1)
    n_bars = len(ohlcv["close"])
    print(f"  Bars:    {n_bars}")
    print(f"  Symbols: {set(ohlcv['symbol'])}")

    # Labels
    banner("GENERATING LABELS")
    label_result = generate_labels(ohlcv, MODE)
    if len(label_result) == 4:
        y_int, gross_r, net_r, label_metrics = label_result
    else:
        y_int, net_r, label_metrics = label_result
        gross_r = net_r
    label_dist = dict(Counter(y_int.tolist()))
    print(f"  Label distribution: {label_dist}")
    print(f"  Gross R stats: mean={np.mean(gross_r):.4f}, std={np.std(gross_r):.4f}")
    print(f"  Net R stats:   mean={np.mean(net_r):.4f}, std={np.std(net_r):.4f}")

    # Features
    banner("COMPUTING FEATURES")
    X, feat_names = compute_features_selected(ohlcv, MODE)
    n_feat = X.shape[1]
    print(f"  Features: {n_feat}")
    print(f"  Names:    {feat_names[:5]}...{feat_names[-3:]}")

    # Align
    cut = min(X.shape[0], len(y_int))
    X, y_int = X[:cut], y_int[:cut]
    gross_r, net_r = gross_r[:cut], net_r[:cut]
    nan_mask = np.isnan(X).any(axis=1)
    X, y_int = X[~nan_mask], y_int[~nan_mask]
    gross_r, net_r = gross_r[~nan_mask], net_r[~nan_mask]
    print(f"  Clean samples: {len(X)}")

    # WFV (same 6-fold as baseline)
    banner("WALK-FORWARD VALIDATION")
    import xgboost as xgb
    from alphaforge.training.xgb_trainer import XGBoostTrainer

    n = len(X)
    fold_size = n // (N_FOLDS + 1)
    CONFIDENCE = 0.55  # same as baseline — DO NOT CHANGE

    fold_results = []
    all_oos_pred = []
    all_oos_probs = []
    all_oos_true = []

    for fold in range(N_FOLDS):
        train_end = (fold + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2
        if val_end >= n:
            break

        purge = fold_size // 4
        embargo = fold_size // 8
        effective_train_end = train_end - purge
        effective_val_start = val_start + embargo

        if effective_train_end <= 0 or effective_val_start >= val_end:
            break

        X_train = X[:effective_train_end]
        y_train = y_int[:effective_train_end]
        X_val = X[effective_val_start:val_end]
        y_val = y_int[effective_val_start:val_end]

        if len(X_train) < 50 or len(X_val) < 10:
            break

        trainer = XGBoostTrainer(mode=MODE)
        fold_result = trainer.train(X_train, y_train)

        # Predictions
        dval = xgb.DMatrix(X_val)
        y_pred_prob = fold_result.model.predict(dval)
        y_pred_prob_max = np.max(y_pred_prob, axis=1)
        y_pred = np.argmax(y_pred_prob, axis=1)

        # Apply confidence threshold
        low_conf_mask = y_pred_prob_max < CONFIDENCE
        y_pred_thresholded = y_pred.copy()
        y_pred_thresholded[low_conf_mask] = 2  # NO_TRADE

        val_acc = float(np.mean(y_pred == y_val))
        val_acc_thresholded = float(np.mean(y_pred_thresholded == y_val))

        # Per-class accuracy
        per_class_acc = {}
        for c in range(3):
            mask = y_val == c
            if mask.sum() > 0:
                per_class_acc[c] = float(np.mean(y_pred[mask] == y_val[mask]))

        fold_info = {
            "fold": fold + 1,
            "n_train": len(X_train),
            "n_val": len(X_val),
            "val_accuracy": val_acc,
            "val_accuracy_thresholded": val_acc_thresholded,
            "train_accuracy": float(fold_result.train_metrics.get("accuracy", 0)),
            "per_class_accuracy": per_class_acc,
            "y_true": y_val.tolist(),
            "y_pred": y_pred.tolist(),
            "y_pred_prob_max": y_pred_prob_max.tolist(),
            "y_pred_prob": y_pred_prob.tolist(),
            "low_conf_pct": float(low_conf_mask.mean() * 100),
            "active_trades": int((~low_conf_mask).sum()),
            "net_r": net_r[effective_val_start:val_end].tolist(),
        }
        fold_results.append(fold_info)

        all_oos_true.extend(y_val.tolist())
        all_oos_pred.extend(y_pred.tolist())
        all_oos_probs.extend(y_pred_prob.tolist())

        print(f"  Fold {fold+1}: train={len(X_train)}, val={len(X_val)}, "
              f"acc={val_acc:.4f}, thres_acc={val_acc_thresholded:.4f}, "
              f"active={fold_info['active_trades']}")

    # Aggregate
    all_oos_true = np.array(all_oos_true)
    all_oos_pred = np.array(all_oos_pred)
    all_oos_probs = np.array(all_oos_probs)
    oos_accuracy = float(np.mean(all_oos_pred == all_oos_true))

    print(f"\n  Aggregate OOS accuracy: {oos_accuracy:.4f}")

    return {
        "config": {"mode": MODE, "symbols": SYMBOLS, "interval": INTERVAL,
                    "confidence_threshold": CONFIDENCE, "n_folds": N_FOLDS},
        "labels": {"distribution": label_dist,
                    "n_long": int((y_int == 0).sum()),
                    "n_short": int((y_int == 1).sum()),
                    "n_no_trade": int((y_int == 2).sum()),
                    "mean_gross_r": float(np.mean(gross_r)),
                    "mean_net_r": float(np.mean(net_r))},
        "features": {"n_features": n_feat, "names": feat_names},
        "wfv": {
            "n_folds": len(fold_results),
            "n_samples": n,
            "fold_results": fold_results,
            "aggregate": {
                "oos_accuracy": oos_accuracy,
            },
        },
        "predictions": {
            "oos_true": all_oos_true.tolist(),
            "oos_pred": all_oos_pred.tolist(),
            "oos_probs": all_oos_probs.tolist(),
        },
    }


# ---------------------------------------------------------------------------
# Report generators
# ---------------------------------------------------------------------------

def report_label_audit(d: dict) -> str:
    """1. Label audit — are labels economically meaningful?"""
    L = d["labels"]
    f = d["wfv"]["fold_results"]

    lines = [
        "# v0.31A — Label Audit",
        "",
        "## 1. Class Distribution",
        f"| Class | Count | % |",
        f"|-------|-------|---|",
        f"| LONG_NOW | {L['n_long']} | {L['n_long']/(L['n_long']+L['n_short']+L['n_no_trade'])*100:.1f}% |",
        f"| SHORT_NOW | {L['n_short']} | {L['n_short']/(L['n_long']+L['n_short']+L['n_no_trade'])*100:.1f}% |",
        f"| NO_TRADE | {L['n_no_trade']} | {L['n_no_trade']/(L['n_long']+L['n_short']+L['n_no_trade'])*100:.1f}% |",
        "",
        "## 2. Economic Separability",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Mean Gross R | {L['mean_gross_r']:.4f} |",
        f"| Mean Net R | {L['mean_net_r']:.4f} |",
        f"| Cost drag | {L['mean_gross_r'] - L['mean_net_r']:.4f} |",
        "",
        "**Critical question:** Do LONG and SHORT labels have positive future net_R after costs?",
        "",
        "## 3. Class Distribution Per Fold",
        "| Fold | LONG | SHORT | NO_TRADE | Dominant % |",
        "|------|------|-------|----------|------------|",
    ]
    for fr in f:
        y_true = np.array(fr["y_true"])
        counts = Counter(y_true.tolist())
        dom_pct = max(counts.values()) / len(y_true) * 100 if y_true.size else 0
        lines.append(
            f"| {fr['fold']} | {counts.get(0, 0)} | {counts.get(1, 0)} | "
            f"{counts.get(2, 0)} | {dom_pct:.1f}% |"
        )

    lines += [
        "",
        "## 4. Baselines",
        f"| Baseline | Expected Accuracy |",
        f"|----------|-------------------|",
        f"| Random (uniform) | 33.3% |",
        f"| Majority class | {max(L['n_long'],L['n_short'],L['n_no_trade'])/(L['n_long']+L['n_short']+L['n_no_trade'])*100:.1f}% |",
        f"| Always LONG | {L['n_long']/(L['n_long']+L['n_short']+L['n_no_trade'])*100:.1f}% |",
        f"| Always SHORT | {L['n_short']/(L['n_long']+L['n_short']+L['n_no_trade'])*100:.1f}% |",
        f"| Always NO_TRADE | {L['n_no_trade']/(L['n_long']+L['n_short']+L['n_no_trade'])*100:.1f}% |",
        "",
        "## 5. Verdict",
        "",
    ]

    # Verdict
    lb = L['n_long'] + L['n_short'] + L['n_no_trade']
    maj_pct = max(L['n_long'], L['n_short'], L['n_no_trade']) / lb * 100
    if L['mean_net_r'] <= 0:
        lines.append("**FAIL: Mean net_R is non-positive.** Labels are not economically separable "
                      "after costs. Model tuning cannot fix this.")
    elif maj_pct > 60:
        lines.append(f"**WARN: Majority class ({maj_pct:.0f}%) dominates.** "
                      f"Class imbalance is significant.")
    else:
        lines.append("**PASS: Labels are balanced and carry positive net_R.** "
                      "Model failure is not in the labels.")

    return "\n".join(lines)


def report_model_failure(d: dict) -> str:
    """2. Model failure analysis — train vs OOS, fold stability."""
    f = d["wfv"]["fold_results"]

    lines = [
        "# v0.31A — Model Failure Analysis",
        "",
        "## 1. Fold-by-Fold Performance",
        "| Fold | Train Acc | OOS Acc | Gap | Active Trades | Low Conf % |",
        "|------|-----------|---------|-----|---------------|------------|",
    ]
    for fr in f:
        gap = fr["train_accuracy"] - fr["val_accuracy"]
        lines.append(
            f"| {fr['fold']} | {fr['train_accuracy']:.4f} | "
            f"{fr['val_accuracy']:.4f} | {gap:.4f} | "
            f"{fr['active_trades']} | {fr['low_conf_pct']:.1f}% |"
        )

    lines += [
        "",
        "## 2. Per-Class Accuracy (OOS, no threshold)",
        "| Fold | LONG Acc | SHORT Acc | NO_TRADE Acc |",
        "|------|----------|-----------|--------------|",
    ]
    for fr in f:
        pca = fr["per_class_accuracy"]
        lines.append(
            f"| {fr['fold']} | {pca.get(0,0):.4f} | {pca.get(1,0):.4f} | {pca.get(2,0):.4f} |"
        )

    # Confusion matrix
    y_true = np.array(d["predictions"]["oos_true"])
    y_pred = np.array(d["predictions"]["oos_pred"])
    cm = np.zeros((3, 3), dtype=int)
    for t, p in zip(y_true, y_pred):
        if 0 <= t < 3 and 0 <= p < 3:
            cm[t, p] += 1

    lines += [
        "",
        "## 3. Confusion Matrix (OOS, all folds)",
        "",
        "| True \\ Pred | LONG | SHORT | NO_TRADE |",
        "|-------------|------|-------|----------|",
        f"| LONG       | {cm[0,0]:>6} | {cm[0,1]:>6} | {cm[0,2]:>6} |",
        f"| SHORT      | {cm[1,0]:>6} | {cm[1,1]:>6} | {cm[1,2]:>6} |",
        f"| NO_TRADE   | {cm[2,0]:>6} | {cm[2,1]:>6} | {cm[2,2]:>6} |",
        "",
    ]

    # Interpretation
    max_col = cm.argmax(axis=0)
    lines.append(f"**Column dominance:** The model's most-predicted class for each true label: "
                  f"{dict(enumerate(max_col.tolist()))}")
    diag = cm.diagonal().sum() / cm.sum() * 100
    off_diag_row = (cm.sum(axis=1) - cm.diagonal()).sum() / cm.sum() * 100
    lines.append(f"**Correct predictions:** {diag:.1f}%")
    lines.append(f"**Off-diagonal (errors):** {off_diag_row:.1f}%")

    # Fold stability
    accs = [fr["val_accuracy"] for fr in f]
    lines += [
        "",
        "## 4. Fold Stability",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Mean OOS acc | {np.mean(accs):.4f} |",
        f"| Std OOS acc  | {np.std(accs):.4f} |",
        f"| Min OOS acc  | {min(accs):.4f} |",
        f"| Max OOS acc  | {max(accs):.4f} |",
        f"| Fold stability (1 - CV) | {1 - np.std(accs)/max(abs(np.mean(accs)),0.001):.4f} |",
    ]

    lines += [
        "",
        "## 5. Diagnosis",
        "",
    ]

    mean_train = float(np.mean([fr["train_accuracy"] for fr in f]))
    mean_oos = float(np.mean(accs))
    gap = mean_train - mean_oos

    if gap > 0.15 and mean_oos < 0.30:
        lines.append(
            f"**OVERFIT:** Train ({mean_train:.1%}) >> OOS ({mean_oos:.1%}), "
            f"gap={gap:.1%}. Model memorizes training patterns that don't "
            f"generalize."
        )
    elif mean_train < 0.35 and mean_oos < 0.35:
        lines.append(
            f"**NOT LEARNING:** Both train ({mean_train:.1%}) and OOS ({mean_oos:.1%}) "
            f"near random. Features lack predictive signal."
        )
    else:
        lines.append(
            f"**BORDERLINE:** Train ({mean_train:.1%}) > OOS ({mean_oos:.1%}), "
            f"gap={gap:.1%}. May improve with regularization."
        )

    return "\n".join(lines)


def report_confidence_calibration(d: dict) -> str:
    """3. Confidence calibration — does confidence predict performance?"""
    probs = np.array(d["predictions"]["oos_probs"])
    y_true = np.array(d["predictions"]["oos_true"])
    y_pred = np.array(d["predictions"]["oos_pred"])

    # Buckets
    max_prob = np.max(probs, axis=1)
    buckets = [(0.25, 0.30), (0.30, 0.35), (0.35, 0.40),
               (0.40, 0.45), (0.45, 0.50), (0.50, 0.55),
               (0.55, 0.60), (0.60, 1.0)]

    lines = [
        "# v0.31A — Confidence Calibration",
        "",
        "## 1. Bucket Analysis",
        "",
        "| Confidence | Count | % of Total | Accuracy | LONG | SHORT | NO_TRADE |",
        "|------------|-------|------------|----------|------|-------|----------|",
    ]

    for lo, hi in buckets:
        mask = (max_prob >= lo) & (max_prob < hi)
        cnt = mask.sum()
        if cnt == 0:
            continue
        acc = float(np.mean(y_pred[mask] == y_true[mask]))
        preds = y_pred[mask]
        n_long = int((preds == 0).sum())
        n_short = int((preds == 1).sum())
        n_nt = int((preds == 2).sum())
        lines.append(
            f"| {lo:.2f}-{hi:.2f} | {cnt} | {cnt/len(max_prob)*100:.1f}% | "
            f"{acc:.4f} | {n_long} | {n_short} | {n_nt} |"
        )

    lines += [
        "",
        "## 2. Decision Rule Check",
        "",
    ]

    # Check if higher confidence → better accuracy
    above_055 = max_prob >= 0.55
    below_055 = max_prob < 0.55
    if above_055.sum() > 0 and below_055.sum() > 0:
        acc_high = float(np.mean(y_pred[above_055] == y_true[above_055]))
        acc_low = float(np.mean(y_pred[below_055] == y_true[below_055]))
        lines.append(f"- Accuracy above 0.55: {acc_high:.4f} ({above_055.sum()} samples)")
        lines.append(f"- Accuracy below 0.55: {acc_low:.4f} ({below_055.sum()} samples)")
        if acc_high > acc_low + 0.02:
            lines.append("- **Verdict:** Confidence DOES predict accuracy. Threshold tuning hypothesis is OPEN.")
        else:
            lines.append("- **Verdict:** Confidence does NOT meaningfully predict accuracy. "
                          "Threshold tuning would be blind.")
    else:
        lines.append("- Insufficient samples in one bucket.")

    return "\n".join(lines)


def report_threshold_frontier(d: dict) -> str:
    """4. Threshold frontier — read-only sweep."""
    probs = np.array(d["predictions"]["oos_probs"])
    y_true = np.array(d["predictions"]["oos_true"])
    y_pred = np.array(d["predictions"]["oos_pred"])
    max_prob = np.max(probs, axis=1)

    thresholds = [0.0, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70]

    lines = [
        "# v0.31A — Threshold Frontier (Read-Only)",
        "",
        "| Threshold | Active Trades | Exposure % | Accuracy | Net R |",
        "|-----------|---------------|------------|----------|-------|",
    ]

    for thr in thresholds:
        mask = max_prob >= thr if thr > 0 else np.ones_like(max_prob, dtype=bool)
        active = mask.sum()
        if active == 0:
            continue
        exposure = active / len(max_prob) * 100
        acc = float(np.mean(y_pred[mask] == y_true[mask]))
        lines.append(f"| {thr:.2f} | {active} | {exposure:.1f}% | {acc:.4f} | N/A |")

    lines += [
        "",
        "**Note:** No threshold is being changed. This is a read-only diagnostic "
        "to determine whether a threshold hypothesis is worth opening.",
        "",
        "**Decision rule:** If multiple thresholds produce above-baseline accuracy "
        "with fold consistency, a threshold-calibration hypothesis may be registered.",
    ]
    return "\n".join(lines)


def report_feature_ablation_plan(d: dict) -> str:
    """5. Feature-family ablation plan."""
    feat_names = d["features"]["names"][:20]  # show first 20
    n_feat = d["features"]["n_features"]

    lines = [
        "# v0.31A — Feature-Family Ablation Plan",
        "",
        "## 1. Current Feature Set",
        f"- **{n_feat} features** across all groups",
        f"- Feature names: {feat_names}",
        "",
        "## 2. Proposed Families",
        "",
        "| Family | Estimated Count | Hypothesis |",
        "|--------|----------------|------------|",
        "| Returns/Price Action | ~10 | Short-term mean reversion signal |",
        "| Momentum | ~8 | Trend following on multiple horizons |",
        "| Volatility/ATR | ~6 | Regime detection, position sizing |",
        "| Volume | ~6 | Volume confirmation / divergence |",
        "| Trend (MA/EMA) | ~8 | Directional bias on multiple resolutions |",
        "| Regime | ~5 | Market regime classification |",
        "| Candle Patterns | ~6 | Single-candle pattern recognition |",
        "| Cross-symbol | ~4 | Lead-lag relationships |",
        "| All Features | ~60 | Full set (current baseline) |",
        "| Shuffled (null) | 60 | Permuted labels — control for data snooping |",
        "",
        "## 3. Methodology",
        "",
        "1. Train with each family ALONE using same config (6-fold WFV, SCALP 1h)",
        "2. Record OOS accuracy, net_R, fold stability",
        "3. Compare against null (shuffled labels) baseline",
        "4. If NO family beats null → features are not predictive → back to feature engineering",
        "5. If 1-2 families beat null → feature set reduction is the right path",
        "6. If ALL families beat null but combined set does not → interference / multicollinearity",
        "",
        "## 4. Stop Condition",
        "",
        "Ablation concludes when we have a clear answer to:",
        "",
        "> Does any feature family carry economically meaningful OOS signal?",
        "",
        "If yes → feature reduction + regularization.",
        "If no → feature engineering redesign.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("v0.31A — Real-Data Failure Diagnostic Report")
    print("=" * 70)
    print()
    print("This is a READ-ONLY diagnostic. No model config is changed.")
    print()

    data = train_and_collect()

    # Save raw diagnostic data for reproducibility
    diag_path = OUTPUT_DIR / "v031_diagnostic_data.json"
    # Omit full prediction arrays to keep file small
    diag_data = {k: v for k, v in data.items() if k != "predictions"}
    diag_data["prediction_stats"] = {
        "n_oos": len(data["predictions"]["oos_true"]),
        "accuracy": float(np.mean(np.array(data["predictions"]["oos_pred"]) ==
                                   np.array(data["predictions"]["oos_true"]))),
    }
    diag_path.write_text(json.dumps(diag_data, indent=2, default=str))
    print(f"\n  Raw data saved: {diag_path}")

    # Generate reports
    reports = {
        "label_audit": report_label_audit,
        "model_failure_analysis": report_model_failure,
        "confidence_calibration": report_confidence_calibration,
        "threshold_frontier": report_threshold_frontier,
        "feature_ablation_plan": report_feature_ablation_plan,
    }

    for name, fn in reports.items():
        path = REPO / "reports" / "research" / f"v031_{name}.md"
        path.write_text(fn(data))
        print(f"  Report: {path.name}")

    print(f"\n{'='*70}")
    print("  Diagnostics complete. No model config changed.")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
