"""
End-to-end AlphaForge training pipeline.

Orchestrates: simulation → labels → features → dataset → model → calibration → evaluation

⚠️ DEPRECATED: This module is a spec-correct reference implementation.
Its sole consumer is ``alphaforge.tests.test_pipeline``.
Production training uses ``alphaforge.train.main()`` via the centralized entrypoint.
Will be removed after v0.4 consolidation (tracked in #319).
"""

from __future__ import annotations

from typing import Any

from alphaforge.dataset.builder import align_features_and_labels, build_dataset, get_feature_keys
from alphaforge.labels.builder import build_labels
from alphaforge.features.engine import compute_all_features
from alphaforge.model.trainer import ModelTrainer
from alphaforge.calibration.engine import Calibrator
from alphaforge.evaluation.engine import (
    evaluate_classification,
    evaluate_regression,
    evaluate_trading,
    regression_reliability,
)

from simulation.adapter import run_training


def run_pipeline(
    simulation_inputs: list[dict[str, Any]],
    mode: str = "SWING",
    *,
    fold_config: dict[str, int] | None = None,
    model_params: dict | None = None,
    calibration_method: str = "platt",
    exclude_ambiguous: bool = True,
    exclude_invalid: bool = True,
) -> dict[str, Any]:
    """Run the full AlphaForge training pipeline.

    Args:
        simulation_inputs: List of SimulationInput dicts (from market data).
        mode: Trading mode for training.
        fold_config: Override fold parameters.
        model_params: Override XGBoost hyperparameters.
        calibration_method: 'platt' or 'isotonic'.
        exclude_ambiguous: Exclude AMBIGUOUS labels from training.
        exclude_invalid: Exclude INVALID labels from training.

    Returns:
        Dict with trained bundles, calibration, and evaluation results.
    """
    # Step 1: Run simulation → get SimulationOutput dicts
    from simulation.adapter import run_training
    sim_outputs = [run_training(inp) for inp in simulation_inputs]

    # Step 2: Build labels from simulation outputs
    labels = build_labels(sim_outputs)

    # Step 3: Build features from raw market data
    # (assumes each sim_input has 'ohlcv' key with candle data)
    all_features = []
    for inp in simulation_inputs:
        ohlcv = inp.get("ohlcv", inp.get("future_path", {}).get("candles", []))
        feat_result = compute_all_features(
            ohlcv,
            context_ohlcv=inp.get("context_ohlcv"),
            refinement_ohlcv=inp.get("refinement_ohlcv"),
        )
        all_features.append({
            "symbol": inp["symbol"],
            "timestamp": inp["decision_timestamp"],
            "features": feat_result["features"],
        })

    # Step 4: Align features + labels → merged dataset
    merged = align_features_and_labels(all_features, labels)
    if not merged:
        return {"status": "no_aligned_rows", "total": 0}

    # Step 5: Build dataset with walk-forward folds
    dataset = build_dataset(
        merged, mode,
        exclude_ambiguous=exclude_ambiguous,
        exclude_invalid=exclude_invalid,
        fold_config=fold_config,
    )
    if dataset["status"] != "ready":
        return dataset

    # Step 6: Train models across all folds
    trainer = ModelTrainer(**(model_params or {}))
    feature_keys = get_feature_keys(merged)
    bundles = trainer.train_from_dataset(dataset, mode, feature_keys)

    if not bundles:
        return {"status": "training_failed", "dataset": dataset}

    # Step 7: Calibrate using the last fold's validation set
    last_fold = dataset["folds"][-1]
    calibrator = Calibrator(method=calibration_method)
    from alphaforge.model.trainer import _dicts_to_arrays
    val_rows = last_fold.get("val_rows", [])
    X_val, y_class_val, _, _ = _dicts_to_arrays(val_rows, feature_keys)
    if len(val_rows) >= 20 and y_class_val is not None and len(X_val) == len(y_class_val):
        last_bundle = bundles[-1]
        clf = last_bundle["classifier"]["model"]
        raw_probs = clf.predict_proba(X_val)
        cal_metrics = calibrator.fit(raw_probs, y_class_val)
    else:
        cal_metrics = {"status": "skipped_insufficient_validation_data", "val_rows": len(val_rows)}

    # Step 8: Evaluate
    all_realized_r = []
    all_y_true = []
    all_y_pred = []
    all_long_true = []
    all_long_pred = []

    for bundle, fold in zip(bundles, dataset["folds"]):
        val_rows = fold.get("val_rows", [])
        if not val_rows:
            continue
        X_v, y_c, y_l, y_s = _dicts_to_arrays(val_rows, feature_keys)
        if len(X_v) == 0:
            continue

        clf = bundle["classifier"]["model"]
        y_p = clf.predict(X_v)
        all_y_true.extend(y_c.tolist() if y_c is not None else [])
        all_y_pred.extend(y_p.tolist())

        for row in val_rows:
            r = row.get("label", {}).get("long_R_net", 0.0)
            all_realized_r.append(float(r))

        long_reg = bundle.get("long_regressor", {}).get("model")
        if long_reg is not None and y_l is not None:
            l_pred = long_reg.predict(X_v)
            all_long_true.extend(y_l.tolist())
            all_long_pred.extend(l_pred.tolist())

    eval_cls = evaluate_classification(all_y_true, all_y_pred) if all_y_true else {}
    eval_reg = evaluate_regression(all_long_true, all_long_pred) if all_long_true else {}
    eval_trd = evaluate_trading(all_realized_r)
    eval_rel = regression_reliability(all_long_true, all_long_pred) if all_long_true else {}

    return {
        "status": "complete",
        "mode": mode,
        "num_folds": len(bundles),
        "total_rows": dataset["total_rows"],
        "excluded_counts": dataset.get("excluded_counts", {}),
        "model_bundles": bundles,
        "calibration": cal_metrics,
        "evaluation": {
            "classification": eval_cls,
            "regression": eval_reg,
            "trading": eval_trd,
            "reliability": eval_rel,
        },
        "dataset": dataset,
    }
