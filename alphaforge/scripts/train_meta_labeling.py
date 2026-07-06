#!/usr/bin/env python3
"""Train meta-labeling model on synthetic data.

Generates synthetic OHLCV data, computes features via the pipeline,
trains a primary XGBoost classifier, then trains a MetaLabeler
to predict primary correctness.

Usage:
    python scripts/train_meta_labeling.py [--n-bars 2000] [--mode SWING]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_repo_root = Path(__file__).resolve().parent.parent
_src_path = str(_repo_root / "alphaforge" / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)


def generate_synthetic_data(
    n_bars: int = 2000,
    random_seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Generate synthetic feature matrix and labels.

    Returns (X, y, feature_names) where X has random features and
    y are 3-class labels with a ~balanced distribution.
    """
    rng = np.random.RandomState(random_seed)

    n_features = 10
    X = rng.randn(n_bars, n_features).astype(np.float64)

    # Generate labels with some signal (slightly predictable)
    # Feature 0 positively correlates with LONG, feature 1 with SHORT
    raw_score = X[:, 0] - X[:, 1] + rng.randn(n_bars) * 0.5
    y = np.full(n_bars, 2, dtype=np.int32)  # default NO_TRADE
    y[raw_score > 0.5] = 0   # LONG
    y[raw_score < -0.5] = 1  # SHORT

    feature_names = [f"feature_{i}" for i in range(n_features)]
    return X, y, feature_names


def main() -> int:
    parser = argparse.ArgumentParser(description="Train meta-labeling model")
    parser.add_argument("--n-bars", type=int, default=2000, help="Number of samples")
    parser.add_argument("--mode", type=str, default="SWING", help="Trading mode")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    print("=== Meta-Labeling Training ===\n")

    # 1. Generate synthetic data
    print("1. Generating synthetic data...")
    X, y, feature_names = generate_synthetic_data(
        n_bars=args.n_bars, random_seed=args.seed,
    )
    unique, counts = np.unique(y, return_counts=True)
    for label, count in zip(unique, counts):
        print(f"   Class {label}: {count} ({count / len(y) * 100:.1f}%)")
    print(f"   Features: {X.shape[1]}, Samples: {len(X)}")

    # 2. Train primary XGBoost classifier
    print("\n2. Training primary XGBoost classifier...")
    from alphaforge.training.xgb_trainer import XGBoostTrainer, SWING_DEFAULT_HYPERPARAMS

    primary_trainer = XGBoostTrainer(
        mode=args.mode,
        random_seed=args.seed,
        hyperparameters=SWING_DEFAULT_HYPERPARAMS,
    )
    primary_result = primary_trainer.train(X, y, feature_names=feature_names)

    print(f"   Primary train accuracy: {primary_result.train_metrics['accuracy']:.4f}")
    print(f"   Primary val accuracy:   {primary_result.val_metrics['accuracy']:.4f}")

    # Get primary predictions and probabilities
    from xgboost import DMatrix
    dmat = DMatrix(X)
    if feature_names:
        dmat.feature_names = feature_names
    primary_probas = primary_result.model.predict(dmat)
    primary_preds = np.argmax(primary_probas, axis=1)

    # 3. Train MetaLabeler
    print("\n3. Training MetaLabeler...")
    from alphaforge.meta import MetaLabeler

    labeler = MetaLabeler(
        train_ratio=0.7,
        meta_depth=5,
        meta_reg_lambda=5.0,
        random_state=args.seed,
    )
    meta_model = labeler.fit(X, primary_preds, y, primary_probas=primary_probas)

    # Evaluate meta accuracy on validation portion
    meta_probas = labeler.predict_meta_proba(X, primary_preds, primary_probas)
    meta_preds = (meta_probas > 0.5).astype(np.int32)

    # Generate meta labels for evaluation
    meta_labels_actual = np.where(primary_preds == y, 1, 0).astype(np.int32)
    meta_accuracy = float(np.mean(meta_preds == meta_labels_actual))
    print(f"   Meta accuracy (full set): {meta_accuracy:.4f}")

    # Precision of meta "correct" predictions
    tp = int(((meta_preds == 1) & (meta_labels_actual == 1)).sum())
    fp = int(((meta_preds == 1) & (meta_labels_actual == 0)).sum())
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    print(f"   Meta precision (correct): {precision:.4f}")

    # 4. Filter trades using meta confidence
    print("\n4. Applying meta filter (threshold=0.5)...")
    trades, confidence, final_preds = labeler.predict_with_filter(
        X, primary_preds, primary_probas,
    )

    n_accepted = int(trades.sum())
    n_rejected = len(trades) - n_accepted
    print(f"   Trades accepted: {n_accepted} / {len(trades)} ({100.0 * n_accepted / len(trades):.1f}%)")
    print(f"   Trades filtered: {n_rejected} ({100.0 * n_rejected / len(trades):.1f}%)")

    # Compare filtered vs unfiltered accuracy
    unfiltered_accuracy = float(np.mean(primary_preds == y))
    filtered_mask = trades
    if filtered_mask.sum() > 0:
        filtered_accuracy = float(np.mean(final_preds[filtered_mask] == y[filtered_mask]))
    else:
        filtered_accuracy = 0.0
    print(f"\n   Unfiltered accuracy: {unfiltered_accuracy:.4f}")
    print(f"   Filtered accuracy:   {filtered_accuracy:.4f}")

    # 5. Walk-forward CV
    print("\n5. Walk-forward cross-validation (6 folds)...")
    wfv_result = labeler.walk_forward_fit(X, primary_preds, y, n_folds=6, primary_probas=primary_probas)
    print(f"   Average meta accuracy (WFV): {wfv_result['avg_meta_accuracy']:.4f}")
    print(f"   Std meta accuracy (WFV):     {wfv_result['std_meta_accuracy']:.4f}")
    print(f"   Per-fold accuracies: {[f'{a:.3f}' for a in wfv_result['fold_meta_accuracy']]}")

    # 6. Summary
    print("\n=== Meta-Labeling Training Summary ===")
    print(f"Mode:              {args.mode}")
    print(f"Training samples:  {len(X)}")
    print(f"Meta train ratio:  {labeler._train_ratio}")
    print(f"Meta depth:        {labeler._meta_depth}")
    print(f"Meta reg_lambda:   {labeler._meta_reg_lambda}")
    print(f"Primary accuracy:  {primary_result.val_metrics.get('accuracy', 0.0):.4f}")
    print(f"Meta accuracy:     {meta_accuracy:.4f}")
    print(f"Meta WFV avg:      {wfv_result['avg_meta_accuracy']:.4f}")
    print(f"Trades filtered:   {n_rejected} / {len(trades)}")
    print("\nMeta-labeling training COMPLETE.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
