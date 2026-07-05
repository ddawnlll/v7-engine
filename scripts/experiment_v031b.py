#!/usr/bin/env python3
"""v0.31B — Target Decomposition Experiment.

Controlled experiment with 4 variants testing whether the 3-class softmax
target is structurally wrong due to NO_TRADE collapse.

Variants:
  A — 3-class baseline (LONG/SHORT/NO_TRADE, threshold disabled)
  B — Direction-only (LONG vs SHORT, trained only on actionable rows)
  C — Actionability (TRADE vs NO_TRADE, binary)
  D — Two-stage policy (actionability gate + direction model)

No tuning. No threshold changes. No feature changes. Same folds, same config.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "alphaforge" / "src"))
sys.path.insert(0, str(REPO))

from alphaforge.train import load_cached_data, generate_labels, compute_features_selected
from alphaforge.training.xgb_trainer import XGBoostTrainer
import xgboost as xgb

# ── Config (identical to baseline) ──
MODE = "SCALP"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
INTERVAL = "1h"
N_FOLDS = 6
CONFIDENCE = 0.55        # same as baseline (but variant A disables for diagnostic)
OUTPUT_DIR = REPO / "data" / "diagnostics"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = REPO / "reports" / "research"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

METRICS_ORDER = [
    "accuracy", "balanced_accuracy", "n_correct", "n_total",
    "per_class_acc", "confusion_matrix",
    "net_r_mean", "net_r_sum", "net_r_std",
    "active_trade_count", "exposure_pct",
    "fold_pass_ratio", "baseline_defeat",
]
LABEL_NAMES_3 = {0: "LONG", 1: "SHORT", 2: "NO_TRADE"}
LABEL_NAMES_2 = {0: "LONG", 1: "SHORT"}
LABEL_NAMES_BINARY = {0: "NO_TRADE", 1: "TRADE"}


# ── Helpers ──

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                    net_r: np.ndarray | None = None,
                    label_names: dict | None = None) -> dict[str, Any]:
    """Compute all metrics for a single variant fold or aggregate."""
    n = len(y_true)
    if n == 0:
        return {"accuracy": 0.0, "n_total": 0, "error": "empty"}

    correct = y_pred == y_true
    acc = float(correct.mean())

    # Per-class accuracy
    n_classes = len(np.unique(list(y_true) + list(y_pred)))
    per_class = {}
    for c in range(n_classes):
        mask = y_true == c
        if mask.sum() > 0:
            per_class[f"class_{c}"] = float((y_pred[mask] == y_true[mask]).mean())
        else:
            per_class[f"class_{c}"] = 0.0

    # Balanced accuracy
    class_accs = [v for v in per_class.values() if not np.isnan(v)]
    bal_acc = float(np.mean(class_accs)) if class_accs else 0.0

    # Confusion matrix
    cm = np.zeros((n_classes, n_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        if 0 <= t < n_classes and 0 <= p < n_classes:
            cm[t, p] += 1

    # Net R metrics
    net_r_mean = 0.0
    net_r_sum = 0.0
    net_r_std = 0.0
    if net_r is not None and len(net_r) == n:
        net_r_mean = float(np.mean(net_r[correct])) if correct.sum() > 0 else 0.0
        net_r_sum = float(net_r[correct].sum()) if correct.sum() > 0 else 0.0
        net_r_std = float(np.std(net_r[correct])) if correct.sum() > 1 else 0.0

    return {
        "accuracy": round(acc, 4),
        "balanced_accuracy": round(bal_acc, 4),
        "n_correct": int(correct.sum()),
        "n_total": n,
        "per_class_acc": per_class,
        "confusion_matrix": cm.tolist(),
        "net_r_mean": round(net_r_mean, 6),
        "net_r_sum": round(net_r_sum, 6),
        "net_r_std": round(net_r_std, 6),
        "active_trade_count": n,
        "exposure_pct": 100.0,
        "label_names": label_names,
    }


def standard_folds(X, y_int, net_r, n_folds=N_FOLDS):
    """Generate same fold splits as the baseline."""
    n = len(X)
    fold_size = n // (n_folds + 1)
    folds = []
    for fold in range(n_folds):
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
        folds.append({
            "fold": fold + 1,
            "X_train": X[:effective_train_end],
            "y_train": y_int[:effective_train_end],
            "X_val": X[effective_val_start:val_end],
            "y_val": y_int[effective_val_start:val_end],
            "net_r_val": net_r[effective_val_start:val_end],
            "n_train": effective_train_end,
            "n_val": val_end - effective_val_start,
        })
    return folds


def train_xgb(X_train, y_train):
    """Train XGBoost with baseline config."""
    trainer = XGBoostTrainer(mode=MODE)
    return trainer.train(X_train, y_train)


def predict_xgb(model, X_val):
    """Get predictions and probabilities."""
    dval = xgb.DMatrix(X_val)
    probs = model.predict(dval)
    preds = np.argmax(probs, axis=1)
    return preds, probs


# ── Variant runners ──

def run_variant_a(folds, label_names):
    """Variant A: 3-class baseline, threshold disabled."""
    all_true, all_pred, all_net_r = [], [], []
    fold_results = []
    for f in folds:
        result = train_xgb(f["X_train"], f["y_train"])
        preds, probs = predict_xgb(result.model, f["X_val"])
        all_true.extend(f["y_val"].tolist())
        all_pred.extend(preds.tolist())
        all_net_r.extend(f["net_r_val"].tolist())
        fold_results.append(compute_metrics(
            f["y_val"], preds, f["net_r_val"], label_names))
    agg = compute_metrics(
        np.array(all_true), np.array(all_pred),
        np.array(all_net_r), label_names)
    return agg, fold_results


def run_variant_b(folds, label_names):
    """Variant B: Direction-only. Filter NO_TRADE rows from train + eval."""
    all_true, all_pred, all_net_r = [], [], []
    fold_results = []
    for f in folds:
        # Filter training: keep only LONG(0) and SHORT(1)
        train_mask = f["y_train"] < 2
        if train_mask.sum() < 50:
            fold_results.append({"error": "insufficient direction rows"})
            continue
        X_train_dir = f["X_train"][train_mask]
        y_train_dir = f["y_train"][train_mask]

        result = train_xgb(X_train_dir, y_train_dir)
        preds, _ = predict_xgb(result.model, f["X_val"])

        # Evaluate on ALL validation rows (including NO_TRADE)
        all_true.extend(f["y_val"].tolist())
        all_pred.extend(preds.tolist())
        all_net_r.extend(f["net_r_val"].tolist())

        # Per-fold metrics on NON-NO_TRADE only
        val_mask = f["y_val"] < 2
        if val_mask.sum() > 0:
            fm = compute_metrics(
                f["y_val"][val_mask], preds[val_mask],
                f["net_r_val"][val_mask], label_names)
            fm["fold"] = f["fold"]
            fold_results.append(fm)

    agg = compute_metrics(
        np.array(all_true), np.array(all_pred),
        np.array(all_net_r), label_names)
    return agg, fold_results


def run_variant_c(folds, label_names):
    """Variant C: Actionability — binary TRADE(1) vs NO_TRADE(0)."""
    all_true, all_pred, all_net_r = [], [], []
    fold_results = []

    for f in folds:
        # Map: LONG/SHORT → TRADE(1), NO_TRADE(2) → NO_TRADE(0)
        y_binary = np.where(f["y_train"] < 2, 1, 0).astype(np.int32)
        val_y_binary = np.where(f["y_val"] < 2, 1, 0).astype(np.int32)

        if (y_binary == 0).sum() < 5 or (y_binary == 1).sum() < 5:
            fold_results.append({"error": "insufficient class samples"})
            continue

        result = train_xgb(f["X_train"], y_binary)
        preds, probs = predict_xgb(result.model, f["X_val"])

        all_true.extend(val_y_binary.tolist())
        all_pred.extend(preds.tolist())
        all_net_r.extend(f["net_r_val"].tolist())

        fm = compute_metrics(val_y_binary, preds, f["net_r_val"], label_names)
        fm["fold"] = f["fold"]

        # AUC estimate (simple: accuracy on class 1)
        pos_mask = val_y_binary == 1
        if pos_mask.sum() > 0:
            fm["trade_recall"] = float((preds[pos_mask] == 1).mean())
        neg_mask = val_y_binary == 0
        if neg_mask.sum() > 0:
            fm["no_trade_recall"] = float((preds[neg_mask] == 0).mean())

        fold_results.append(fm)

    agg = compute_metrics(
        np.array(all_true), np.array(all_pred),
        np.array(all_net_r), label_names)

    # Aggregate recall
    all_true_arr = np.array(all_true)
    all_pred_arr = np.array(all_pred)
    pos = all_true_arr == 1
    neg = all_true_arr == 0
    if pos.sum() > 0:
        agg["trade_recall"] = float((all_pred_arr[pos] == 1).mean())
    if neg.sum() > 0:
        agg["no_trade_recall"] = float((all_pred_arr[neg] == 0).mean())

    return agg, fold_results


def run_variant_d(folds, dir_label_names, act_label_names):
    """Variant D: Two-stage — actionability gate + direction model."""
    all_true, all_pred, all_net_r = [], [], []
    fold_results = []

    for f in folds:
        # Stage 1: train actionability model
        y_act = np.where(f["y_train"] < 2, 1, 0).astype(np.int32)
        val_y_act = np.where(f["y_val"] < 2, 1, 0).astype(np.int32)

        if (y_act == 0).sum() < 5 or (y_act == 1).sum() < 5:
            fold_results.append({"error": "insufficient actionability samples"})
            continue

        act_result = train_xgb(f["X_train"], y_act)
        act_preds, act_probs = predict_xgb(act_result.model, f["X_val"])

        # Stage 2: train direction model (only on actionable rows)
        train_act_mask = f["y_train"] < 2
        if train_act_mask.sum() < 50:
            fold_results.append({"error": "insufficient direction rows"})
            continue

        dir_result = train_xgb(
            f["X_train"][train_act_mask],
            f["y_train"][train_act_mask],
        )
        dir_preds, _ = predict_xgb(dir_result.model, f["X_val"])

        # Combine: actionability decides TRADE vs NO_TRADE
        # Direction decides LONG vs SHORT
        final_preds = np.where(act_preds == 0, 2, dir_preds)  # 0=NO_TRADE→class 2

        all_true.extend(f["y_val"].tolist())
        all_pred.extend(final_preds.tolist())
        all_net_r.extend(f["net_r_val"].tolist())

        fm = compute_metrics(f["y_val"], final_preds, f["net_r_val"], dir_label_names)
        fm["fold"] = f["fold"]
        fold_results.append(fm)

    agg = compute_metrics(
        np.array(all_true), np.array(all_pred),
        np.array(all_net_r), dir_label_names)
    return agg, fold_results


# ── Report writers ──

def make_variant_table(name: str, agg: dict, folds: list, baseline: dict | None = None) -> str:
    lines = [
        f"## {name}",
        "",
        "### Aggregate",
        f"| Metric | Value" + (" | Baseline | Delta |" if baseline else " |"),
        f"|--------|------" + ("|----------|-------|" if baseline else "|"),
        f"| Accuracy | {agg.get('accuracy', 'N/A')}" + (f" | {baseline.get('accuracy', 'N/A')} | {_delta(agg.get('accuracy', 0), baseline.get('accuracy', 0))} |" if baseline else " |"),
        f"| Balanced Acc | {agg.get('balanced_accuracy', 'N/A')}" + (f" | {baseline.get('balanced_accuracy', 'N/A')} | {_delta(agg.get('balanced_accuracy', 0), baseline.get('balanced_accuracy', 0))} |" if baseline else " |"),
        f"| Correct/Total | {agg.get('n_correct', 0)}/{agg.get('n_total', 0)}" + (" | |" if baseline else " |"),
        f"| Net R (mean) | {agg.get('net_r_mean', 0):.6f}" + (f" | {baseline.get('net_r_mean', 0):.6f} |" if baseline else " |"),
        f"| Net R (sum) | {agg.get('net_r_sum', 0):.4f}" + (f" | {baseline.get('net_r_sum', 0):.4f} |" if baseline else " |"),
        f"| Active Trades | {agg.get('active_trade_count', 0)}" + (" | |" if baseline else " |"),
        "",
        "### Per-Class Accuracy",
    ]
    pca = agg.get("per_class_acc", {})
    for k, v in pca.items():
        lines.append(f"- {k}: {v:.4f}")

    lines += ["", "### Confusion Matrix", ""]
    cm = agg.get("confusion_matrix", [])
    if cm:
        n_classes = len(cm)
        header = "| True \\\\ Pred | " + " | ".join(str(i) for i in range(n_classes)) + " |"
        sep = "|" + "---|" * (n_classes + 1)
        lines.append(header)
        lines.append(sep)
        for i, row in enumerate(cm):
            lines.append(f"| {i} | " + " | ".join(str(c) for c in row) + " |")

    if folds:
        lines += ["", "### Per-Fold", ""]
        for f in folds:
            if "error" in f:
                lines.append(f"  Fold {f.get('fold', '?'):} — ERROR: {f['error']}")
            else:
                lines.append(
                    f"  Fold {f.get('fold', '?'):3} | "
                    f"acc={f.get('accuracy', 0):.4f} | "
                    f"net_R={f.get('net_r_mean', 0):.6f} | "
                    f"trades={f.get('active_trade_count', 0)}")

    return "\n".join(lines)


def _delta(cur, base) -> str:
    """Format delta with sign."""
    d = cur - base
    return f"{d:+.4f}"


# ── Main ──

def main():
    print("=" * 70)
    print("  v0.31B — Target Decomposition Experiment")
    print("=" * 70)
    print()
    print("  Variants: A=3-class B=direction C=actionability D=two-stage")
    print("  No tuning. No threshold changes. No feature changes.")
    print()

    # ── Load data (identical to baseline) ──
    print("[1/5] Loading data...")
    ohlcv = load_cached_data(SYMBOLS, INTERVAL)
    assert ohlcv is not None, "No data loaded"
    print(f"  Bars: {len(ohlcv['close'])}")

    # ── Labels ──
    print("[2/5] Generating labels...")
    y_int, gross_r, net_r, label_metrics = generate_labels(ohlcv, MODE)
    dist = Counter(y_int.tolist())
    print(f"  Labels: {dict(dist)}")

    # ── Features ──
    print("[3/5] Computing features...")
    X, feat_names = compute_features_selected(ohlcv, MODE)
    cut = min(X.shape[0], len(y_int))
    X, y_int = X[:cut], y_int[:cut]
    net_r = net_r[:cut]
    nan_mask = np.isnan(X).any(axis=1)
    X, y_int = X[~nan_mask], y_int[~nan_mask]
    net_r = net_r[~nan_mask]
    print(f"  Features: {X.shape[1]}, Samples: {len(X)}")

    # ── Folds (identical splits for all variants) ──
    print("[4/5] Creating fold splits...")
    folds = standard_folds(X, y_int, net_r)
    print(f"  Folds: {len(folds)}")
    for f in folds:
        print(f"    Fold {f['fold']}: train={f['n_train']}, val={f['n_val']}")

    # ── Run all 4 variants ──
    print("[5/5] Running 4 variants...")
    print()

    # Variant A: 3-class baseline
    print("  Variant A: 3-class baseline...")
    t0 = time.time()
    agg_a, folds_a = run_variant_a(folds, LABEL_NAMES_3)
    print(f"    acc={agg_a['accuracy']:.4f}, bal_acc={agg_a['balanced_accuracy']:.4f}, "
          f"net_R={agg_a['net_r_mean']:.6f} ({time.time()-t0:.1f}s)")

    # Variant B: Direction-only
    print("  Variant B: Direction-only...")
    t0 = time.time()
    agg_b, folds_b = run_variant_b(folds, LABEL_NAMES_2)
    print(f"    acc={agg_b['accuracy']:.4f}, bal_acc={agg_b['balanced_accuracy']:.4f}, "
          f"net_R={agg_b['net_r_mean']:.6f} ({time.time()-t0:.1f}s)")

    # Variant C: Actionability
    print("  Variant C: Actionability...")
    t0 = time.time()
    agg_c, folds_c = run_variant_c(folds, LABEL_NAMES_BINARY)
    print(f"    acc={agg_c['accuracy']:.4f}, bal_acc={agg_c['balanced_accuracy']:.4f}, "
          f"trade_recall={agg_c.get('trade_recall',0):.3f}, "
          f"no_trade_recall={agg_c.get('no_trade_recall',0):.3f} ({time.time()-t0:.1f}s)")

    # Variant D: Two-stage
    print("  Variant D: Two-stage policy...")
    t0 = time.time()
    agg_d, folds_d = run_variant_d(folds, LABEL_NAMES_3, LABEL_NAMES_BINARY)
    print(f"    acc={agg_d['accuracy']:.4f}, bal_acc={agg_d['balanced_accuracy']:.4f}, "
          f"net_R={agg_d['net_r_mean']:.6f} ({time.time()-t0:.1f}s)")

    # ── Save raw results ──
    results = {
        "config": {"mode": MODE, "symbols": SYMBOLS, "interval": INTERVAL, "n_folds": N_FOLDS},
        "variant_a_3class_baseline": {"aggregate": agg_a},
        "variant_b_direction_only": {"aggregate": agg_b},
        "variant_c_actionability": {"aggregate": agg_c},
        "variant_d_two_stage": {"aggregate": agg_d},
    }
    raw_path = OUTPUT_DIR / "v031b_results.json"
    raw_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n  Raw results: {raw_path}")

    # ── Generate reports ──
    print("\n  Generating reports...")

    # Main comparison report
    lines = [
        "# v0.31B — Target Decomposition Experiment",
        "",
        "**Date:** 2026-07-02",
        f"**Config:** {MODE}, {INTERVAL}, {SYMBOLS}, {N_FOLDS}-fold WFV, XGBoost depth=4/200trees",
        "**Status:** CONTROLLED_EXPERIMENT — No tuning, no threshold changes",
        "",
        "## Summary",
        "",
        "| Variant | Accuracy | Balanced Acc | Net R (mean) | Net R (sum) | Active Trades |",
        "|---------|----------|-------------|-------------|-------------|--------------|",
        f"| A — 3-class | {agg_a['accuracy']:.4f} | {agg_a['balanced_accuracy']:.4f} | {agg_a['net_r_mean']:.6f} | {agg_a['net_r_sum']:.4f} | {agg_a['active_trade_count']} |",
        f"| B — Direction | {agg_b['accuracy']:.4f} | {agg_b['balanced_accuracy']:.4f} | {agg_b['net_r_mean']:.6f} | {agg_b['net_r_sum']:.4f} | {agg_b['active_trade_count']} |",
        f"| C — Actionability | {agg_c['accuracy']:.4f} | {agg_c['balanced_accuracy']:.4f} | {agg_c['net_r_mean']:.6f} | {agg_c['net_r_sum']:.4f} | {agg_c['active_trade_count']} |",
        f"| D — Two-stage | {agg_d['accuracy']:.4f} | {agg_d['balanced_accuracy']:.4f} | {agg_d['net_r_mean']:.6f} | {agg_d['net_r_sum']:.4f} | {agg_d['active_trade_count']} |",
        "",
        "## Baselines",
        "",
        "| Baseline | Accuracy |",
        "|----------|----------|",
        "| 3-class random | 33.3% |",
        "| 3-class majority | 42.0% |",
        f"| 2-class random | 50.0% |",
        f"| 2-class majority | ~50.5% |",
        "",
        "## Verdict",
        "",
    ]

    # Determine verdict
    b_acc = agg_b.get("accuracy", 0)
    c_no_trade_recall = agg_c.get("no_trade_recall", 0)
    d_acc = agg_d.get("accuracy", 0)

    if b_acc > 0.51:
        lines.append("- **Direction signal EXISTS.** Variant B beats 2-class majority baseline.")
    else:
        lines.append("- **Direction signal WEAK.** Variant B does not reliably beat majority.")

    if c_no_trade_recall > 0.3:
        lines.append("- **NO_TRADE is partially learnable.** Actionability recall > 30%.")
    else:
        lines.append("- **NO_TRADE is NOT learnable** from current 1h features.")

    if d_acc > agg_a.get("accuracy", 0):
        lines.append("- **Two-stage improves** over 3-class baseline. Decomposition is the right path.")
    else:
        lines.append("- **Two-stage does not improve** over baseline. Further investigation needed.")

    lines += [
        "",
        "## Detailed Results",
        "",
    ]

    (REPORTS_DIR / "v031b_target_decomposition.md").write_text("\n".join(lines))

    # Individual variant reports
    reports = {
        "v031b_direction_model.md": ("Variant B — Direction-Only (LONG vs SHORT)", agg_b, folds_b),
        "v031b_actionability_model.md": ("Variant C — Actionability (TRADE vs NO_TRADE)", agg_c, folds_c),
        "v031b_two_stage_policy.md": ("Variant D — Two-Stage Policy", agg_d, folds_d),
    }

    for fname, (name, agg, flds) in reports.items():
        content = [
            f"# v0.31B — {name}",
            "",
            f"**Config:** {MODE}, {INTERVAL}, {SYMBOLS}, {N_FOLDS}-fold WFV",
            "",
        ]
        content.append(make_variant_table(name, agg, flds, agg_a if fname != "v031b_direction_model.md" else None))
        (REPORTS_DIR / fname).write_text("\n".join(content))
        print(f"  Report: {fname}")

    print(f"\n  Reports in: {REPORTS_DIR}")
    print()


if __name__ == "__main__":
    main()
