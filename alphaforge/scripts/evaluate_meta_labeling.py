#!/usr/bin/env python3
"""Evaluate meta-labeling with PBO guard (6-fold walk-forward + cost-stress).

Computes:
  - Per-fold meta accuracy and stability
  - PBO (Probability of Backtest Overfitting) via 6-fold WFV
  - Cost-stress sensitivity of meta-filtered predictions
  - Comparison of single vs filtered trade sets

Usage:
    python scripts/evaluate_meta_labeling.py [--n-bars 2000] [--mode SWING]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

_src_path = str(Path(__file__).resolve().parent.parent / "alphaforge" / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)


def generate_synthetic_data(
    n_bars: int = 2000,
    random_seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Generate synthetic feature matrix and 3-class labels."""
    rng = np.random.RandomState(random_seed)
    n_features = 10
    X = rng.randn(n_bars, n_features).astype(np.float64)
    raw_score = X[:, 0] - X[:, 1] + rng.randn(n_bars) * 0.5
    y = np.full(n_bars, 2, dtype=np.int32)
    y[raw_score > 0.5] = 0
    y[raw_score < -0.5] = 1
    feature_names = [f"feature_{i}" for i in range(n_features)]
    return X, y, feature_names


def compute_pbo_risk(
    fold_metrics: List[float],
    baseline_metric: float,
) -> Dict[str, Any]:
    """Compute PBO risk from walk-forward fold metrics.

    Uses the rank-based PBO estimator from Lopez de Prado (2018):
    PBO = fraction of folds where OOS metric < median of IS metrics.

    Args:
        fold_metrics: List of OOS metrics (one per fold).
        baseline_metric: Full-sample IS metric for comparison.

    Returns:
        Dict with keys: pbo_risk, n_folds, metric_std, rank_stability.
    """
    if not fold_metrics:
        return {"pbo_risk": 1.0, "n_folds": 0, "metric_std": 0.0, "rank_stability": 0.0}

    n_folds = len(fold_metrics)
    metrics_arr = np.array(fold_metrics)

    # PBO: fraction of folds below the median IS performance
    median_oos = float(np.median(metrics_arr))
    pbo_risk = float(np.mean(metrics_arr < baseline_metric))

    # Stability: std of fold metrics (lower = more stable)
    metric_std = float(np.std(metrics_arr, ddof=1)) if n_folds > 1 else 0.0

    # Rank stability: Spearman-like rank correlation between consecutive folds
    if n_folds >= 3:
        ranks = np.argsort(np.argsort(metrics_arr))
        rank_diffs = np.diff(ranks)
        rank_stability = float(1.0 - np.mean(np.abs(rank_diffs)) / (n_folds - 1))
    else:
        rank_stability = 1.0

    return {
        "pbo_risk": pbo_risk,
        "n_folds": n_folds,
        "metric_std": metric_std,
        "median_oos": median_oos,
        "rank_stability": rank_stability,
    }


def compute_cost_stress_impact(
    meta_accuracy: float,
    unfiltered_accuracy: float,
    trade_fraction: float,
) -> Dict[str, Any]:
    """Compute cost-stress-like impact of meta-filtering.

    Models filtering as a cost: filtering reduces trade frequency but
    improves per-trade accuracy.

    Args:
        meta_accuracy: Accuracy of meta-filtered predictions.
        unfiltered_accuracy: Accuracy of raw primary predictions.
        trade_fraction: Fraction of trades accepted by meta-filter.

    Returns:
        Dict with keys: accuracy_gain, trade_reduction, efficiency_ratio.
    """
    accuracy_gain = meta_accuracy - unfiltered_accuracy
    trade_reduction = 1.0 - trade_fraction

    # Efficiency: accuracy gain per unit trade reduction
    efficiency_ratio = accuracy_gain / max(trade_reduction, 1e-6)

    return {
        "accuracy_gain": accuracy_gain,
        "trade_reduction": trade_reduction,
        "trade_fraction": trade_fraction,
        "efficiency_ratio": efficiency_ratio,
        "meta_accuracy": meta_accuracy,
        "unfiltered_accuracy": unfiltered_accuracy,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate meta-labeling with PBO guard")
    parser.add_argument("--n-bars", type=int, default=2000, help="Number of samples")
    parser.add_argument("--mode", type=str, default="SWING", help="Trading mode")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--n-folds", type=int, default=6, help="WFV folds")
    args = parser.parse_args()

    print("=== Meta-Labeling Evaluation (PBO-Guarded) ===\n")

    # 1. Generate data
    print("1. Generating synthetic data...")
    X, y, feature_names = generate_synthetic_data(
        n_bars=args.n_bars, random_seed=args.seed,
    )
    print(f"   Samples: {len(X)}, Features: {X.shape[1]}")

    # 2. Train primary classifier on full data
    print("\n2. Training primary classifier...")
    from alphaforge.training.xgb_trainer import XGBoostTrainer, SWING_DEFAULT_HYPERPARAMS

    primary_trainer = XGBoostTrainer(
        mode=args.mode,
        random_seed=args.seed,
        hyperparameters=SWING_DEFAULT_HYPERPARAMS,
    )
    primary_result = primary_trainer.train(X, y, feature_names=feature_names)
    baseline_accuracy = primary_result.val_metrics.get("accuracy", 0.0)
    print(f"   Primary accuracy: {baseline_accuracy:.4f}")

    # Primary predictions
    from xgboost import DMatrix
    dmat = DMatrix(X)
    if feature_names:
        dmat.feature_names = feature_names
    primary_probas = primary_result.model.predict(dmat)
    primary_preds = np.argmax(primary_probas, axis=1)

    # 3. Walk-forward meta-labeling evaluation (PBO guard)
    print(f"\n3. Walk-forward meta evaluation ({args.n_folds} folds)...")
    from alphaforge.meta import MetaLabeler

    labeler = MetaLabeler(
        train_ratio=0.7,
        meta_depth=5,
        meta_reg_lambda=5.0,
        random_state=args.seed,
    )

    fold_size = len(X) // args.n_folds
    fold_meta_accs: List[float] = []
    fold_filtered_accs: List[float] = []

    for fold_idx in range(args.n_folds):
        val_start = fold_idx * fold_size
        val_end = min(val_start + fold_size, len(X))

        if val_end - val_start < 20:
            continue

        X_train = X[:val_start] if val_start > 0 else X[:1]  # at least 1
        y_train = y[:val_start] if val_start > 0 else y[:1]
        X_val = X[val_start:val_end]
        y_val = y[val_start:val_end]

        if len(X_train) < 20:
            continue

        # Train primary on this fold's train set
        fold_primary = XGBoostTrainer(
            mode=args.mode,
            random_seed=args.seed + fold_idx,
            hyperparameters=SWING_DEFAULT_HYPERPARAMS,
        )
        fold_primary_result = fold_primary.train(
            X_train, y_train, feature_names=feature_names,
        )

        dmat_val = DMatrix(X_val)
        if feature_names:
            dmat_val.feature_names = feature_names
        fold_primary_probas = fold_primary_result.model.predict(dmat_val)
        fold_primary_preds = np.argmax(fold_primary_probas, axis=1)

        # Get primary predictions on full train set for meta-label generation
        dmat_train = DMatrix(X_train)
        if feature_names:
            dmat_train.feature_names = feature_names
        train_primary_probas = fold_primary_result.model.predict(dmat_train)
        train_primary_preds = np.argmax(train_primary_probas, axis=1)

        # Train meta on this fold's train set
        fold_labeler = MetaLabeler(
            train_ratio=0.7,
            meta_depth=5,
            meta_reg_lambda=5.0,
            random_state=args.seed + fold_idx,
        )
        fold_labeler.fit(X_train, train_primary_preds, y_train, primary_probas=train_primary_probas)

        # Evaluate on val set
        fold_meta_probas = fold_labeler.predict_meta_proba(
            X_val, fold_primary_preds, fold_primary_probas,
        )

        # Meta accuracy
        meta_labels = np.where(fold_primary_preds == y_val, 1, 0).astype(np.int32)
        meta_preds = (fold_meta_probas > 0.5).astype(np.int32)
        meta_acc = float(np.mean(meta_preds == meta_labels))
        fold_meta_accs.append(meta_acc)

        # Filtered prediction accuracy
        trades, _, final_preds = fold_labeler.predict_with_filter(
            X_val, fold_primary_preds, fold_primary_probas,
        )
        if trades.sum() > 0:
            filtered_acc = float(np.mean(final_preds[trades] == y_val[trades]))
        else:
            filtered_acc = 0.0
        fold_filtered_accs.append(filtered_acc)

        print(
            f"   Fold {fold_idx}: meta_acc={meta_acc:.4f} "
            f"filtered_acc={filtered_acc:.4f} "
            f"val_size={len(X_val)}"
        )

    # 4. PBO risk computation
    print("\n4. PBO Risk Analysis...")
    pbo_result = compute_pbo_risk(fold_meta_accs, baseline_accuracy)
    print(f"   PBO risk:       {pbo_result['pbo_risk']:.4f}")
    print(f"   Metric std:     {pbo_result['metric_std']:.4f}")
    print(f"   Median OOS:     {pbo_result['median_oos']:.4f}")
    print(f"   Rank stability: {pbo_result['rank_stability']:.4f}")
    print(f"   Folds:          {pbo_result['n_folds']}")

    pbo_verdict = "PASS" if pbo_result["pbo_risk"] < 0.5 else "FAIL_HIGH_PBO_RISK"
    print(f"   PBO verdict:    {pbo_verdict}")

    # 5. Cost-stress impact
    print("\n5. Cost-Stress Impact Analysis...")
    # Full-sample evaluation for cost-stress
    labeler_full = MetaLabeler(
        train_ratio=0.7, meta_depth=5, meta_reg_lambda=5.0, random_state=args.seed,
    )
    labeler_full.fit(X, primary_preds, y, primary_probas=primary_probas)
    trades_full, _, final_preds_full = labeler_full.predict_with_filter(
        X, primary_preds, primary_probas,
    )

    unfiltered_acc = float(np.mean(primary_preds == y))
    filtered_acc = float(np.mean(final_preds_full[trades_full] == y[trades_full])) if trades_full.sum() > 0 else 0.0
    trade_fraction = float(trades_full.sum()) / len(trades_full)

    cost_result = compute_cost_stress_impact(filtered_acc, unfiltered_acc, trade_fraction)
    print(f"   Unfiltered accuracy:  {cost_result['unfiltered_accuracy']:.4f}")
    print(f"   Filtered accuracy:    {cost_result['meta_accuracy']:.4f}")
    print(f"   Accuracy gain:        {cost_result['accuracy_gain']:.4f}")
    print(f"   Trade fraction:       {cost_result['trade_fraction']:.4f}")
    print(f"   Trade reduction:      {cost_result['trade_reduction']:.4f}")
    print(f"   Efficiency ratio:     {cost_result['efficiency_ratio']:.4f}")

    cost_verdict = "PASS" if cost_result["accuracy_gain"] > 0 else "FAIL_NO_GAIN"
    print(f"   Cost-stress verdict:  {cost_verdict}")

    # 6. Summary
    print("\n=== Evaluation Summary ===")
    print(f"Mode:                    {args.mode}")
    print(f"Samples:                 {len(X)}")
    print(f"WFV folds:               {args.n_folds}")
    print(f"Avg meta accuracy (WFV): {np.mean(fold_meta_accs):.4f}")
    print(f"PBO risk:                {pbo_result['pbo_risk']:.4f}")
    print(f"PBO verdict:             {pbo_verdict}")
    print(f"Accuracy gain:           {cost_result['accuracy_gain']:.4f}")
    print(f"Cost-stress verdict:     {cost_verdict}")
    print(f"Overall:                 {'PASS' if pbo_verdict == 'PASS' and cost_verdict == 'PASS' else 'REVIEW'}")

    return 0 if (pbo_verdict == "PASS" and cost_verdict == "PASS") else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
