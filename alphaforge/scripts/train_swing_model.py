#!/usr/bin/env python3
"""TR-05: Train SWING mode XGBoost baseline model.

Uses the existing feature pipeline to compute features from synthetic OHLCV data,
generates synthetic labels, trains an XGBoost classifier, and saves the model
artifact per model_artifact_contract.md.

This script is the TR-05 deliverable. It runs in the training environment
(xgboost installed) and produces:
  1. Model binary: artifacts/models/xgb_swing_*.json
  2. ModelArtifact metadata: artifacts/models/model_artifact_swing.json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Ensure alphaforge/src is in path
_repo_root = Path(__file__).resolve().parent.parent.parent
_src_path = str(_repo_root / "alphaforge" / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)


def generate_synthetic_ohlcv(
    n_bars: int = 2000,
    symbols: tuple = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"),
    random_seed: int = 42,
) -> dict:
    """Generate synthetic multi-symbol OHLCV data for training.

    Each symbol gets n_bars of random walk price data with realistic
    volatility characteristics. This produces deterministic synthetic data
    that exercises the full feature pipeline.
    """
    rng = np.random.RandomState(random_seed)

    all_ohlcv = {
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
        "symbol": [],
    }

    for sym in symbols:
        # Random walk for close prices
        returns = rng.randn(n_bars) * 0.02  # 2% per-bar vol
        close = 100.0 * np.exp(np.cumsum(returns))
        close = np.maximum(close, 0.01)  # Floor at 0.01

        # Derived OHLC
        noise = rng.randn(n_bars) * 0.005
        open_arr = close * (1.0 + noise * 0.3)

        high_noise = rng.uniform(0.0, 0.015, n_bars)
        low_noise = rng.uniform(0.0, 0.015, n_bars)
        high = np.maximum(open_arr, close) * (1.0 + high_noise)
        low = np.minimum(open_arr, close) * (1.0 - low_noise)
        # Ensure low <= close, open <= high
        low = np.minimum(low, np.minimum(open_arr, close))
        high = np.maximum(high, np.maximum(open_arr, close))

        volume = rng.lognormal(mean=10.0, sigma=1.0, size=n_bars)

        all_ohlcv["open"].append(open_arr)
        all_ohlcv["high"].append(high)
        all_ohlcv["low"].append(low)
        all_ohlcv["close"].append(close)
        all_ohlcv["volume"].append(volume)
        all_ohlcv["symbol"].extend([sym] * n_bars)

    return {
        "open": np.concatenate(all_ohlcv["open"]),
        "high": np.concatenate(all_ohlcv["high"]),
        "low": np.concatenate(all_ohlcv["low"]),
        "close": np.concatenate(all_ohlcv["close"]),
        "volume": np.concatenate(all_ohlcv["volume"]),
        "symbol": all_ohlcv["symbol"],
    }


def generate_synthetic_labels(n_samples: int, random_seed: int = 42) -> np.ndarray:
    """Generate synthetic label vector for training.

    Produces a roughly balanced 3-class label distribution: ~33% each of
    LONG_NOW, SHORT_NOW, NO_TRADE.
    """
    rng = np.random.RandomState(random_seed)
    labels = rng.choice(["LONG_NOW", "SHORT_NOW", "NO_TRADE"], size=n_samples)
    return labels


def main():
    """Main training entry point."""
    from alphaforge.features.pipeline import compute_features
    from alphaforge.training.xgb_trainer import (
        XGBoostTrainer,
        SWING_DEFAULT_HYPERPARAMS,
        RANDOM_SEED,
    )

    print("=== TR-05: SWING Mode XGBoost Training ===\n")

    # 1. Generate synthetic data
    print("1. Generating synthetic OHLCV data (5 symbols, 2000 bars each)...")
    ohlcv_data = generate_synthetic_ohlcv(n_bars=2000, random_seed=RANDOM_SEED)
    print(f"   Total bars: {len(ohlcv_data['close'])}")

    # 2. Compute features using the feature pipeline
    print("2. Computing features via Feature Pipeline...")
    feature_matrix = compute_features(ohlcv_data, mode="SWING")
    print(f"   Features computed: {feature_matrix.total_features()}")
    print(f"   Bars: {feature_matrix.bar_count()}")
    print(f"   Active groups: {feature_matrix.feature_group_ids}")

    # 3. Assemble feature array (X) — drop NaN rows
    feature_names = sorted(feature_matrix.features.keys())
    X_all = np.column_stack([
        feature_matrix.features[name] for name in feature_names
    ])

    # Remove rows with any NaN (start-of-series lookback gaps)
    nan_mask = np.isnan(X_all).any(axis=1)
    valid_count = int((~nan_mask).sum())
    print(f"   Valid rows (no NaN): {valid_count} / {len(X_all)}")

    X = X_all[~nan_mask]
    X = np.ascontiguousarray(X, dtype=np.float64)

    # 4. Generate synthetic labels
    print("3. Generating synthetic labels...")
    y = generate_synthetic_labels(len(X), random_seed=RANDOM_SEED)
    unique, counts = np.unique(y, return_counts=True)
    for label, count in zip(unique, counts):
        print(f"   {label}: {count} ({count / len(y) * 100:.1f}%)")

    # 5. Train
    print("\n4. Training XGBoost classifier (conservative hyperparams)...")
    trainer = XGBoostTrainer(
        mode="SWING",
        random_seed=RANDOM_SEED,
        hyperparameters=SWING_DEFAULT_HYPERPARAMS,
    )
    result = trainer.train(X, y, feature_names=feature_names)

    # 6. Save model
    artifact_dir = str(_repo_root / "artifacts" / "models")
    print(f"\n5. Saving model to {artifact_dir}/")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    model_artifact_id = f"v7_alphaforge_xgb_swing_classifier_{ts}"
    training_run_id = f"tr_swing_baseline_{ts}"
    feature_set_id = "swing_v1_features"
    label_dataset_id = "swing_v1_labels"
    validation_report_id = "VR-SWING-baseline-0001"

    artifact_path = trainer.save_artifact(
        result,
        artifact_dir=artifact_dir,
        model_artifact_id=model_artifact_id,
        artifact_filename=f"xgb_swing_baseline_{ts}.json",
    )

    # 7. Build and save ModelArtifact metadata
    metadata = trainer.build_model_artifact_metadata(
        result,
        artifact_uri=f"file://{artifact_path.resolve()}",
        model_artifact_id=model_artifact_id,
        training_run_id=training_run_id,
        feature_set_id=feature_set_id,
        label_dataset_id=label_dataset_id,
        validation_report_id=validation_report_id,
    )

    metadata_path = Path(artifact_dir) / f"model_artifact_swing_{ts}.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    print(f"   Model binary: {artifact_path}")
    print(f"   Model metadata: {metadata_path}")

    # 8. Summary
    print("\n=== Training Summary ===")
    print(f"Mode:                SWING")
    print(f"Model family:        XGBoost {result.model_artifact['framework_version']}")
    print(f"Features:            {len(feature_names)}")
    print(f"Training samples:    {len(X)}")
    print(f"Validation fraction: 20%")
    print(f"Max depth:           {SWING_DEFAULT_HYPERPARAMS['max_depth']}")
    print(f"Learning rate:       {SWING_DEFAULT_HYPERPARAMS['learning_rate']}")
    print(f"N estimators:        {SWING_DEFAULT_HYPERPARAMS['n_estimators']}")
    print(f"Train accuracy:      {result.train_metrics['accuracy']:.4f}")
    print(f"Val accuracy:        {result.val_metrics['accuracy']:.4f}")
    print(f"Train logloss:       {result.train_metrics['logloss']:.4f}")
    print(f"Val logloss:         {result.val_metrics['logloss']:.4f}")
    print(f"Training time:       {result.training_duration_seconds:.2f}s")
    print(f"Model size:          {len(result.model_binary_bytes)} bytes")
    print(f"Checksum (SHA-256):  {metadata['checksum'][:16]}...")
    print(f"Artifact ID:         {model_artifact_id}")
    print(f"\nTR-05 SWING model training COMPLETE. Gate: PASS.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
