"""Feature ablation with tuned model — minimum viable feature set.

P2 (Issue #151): Feature ablation using a tuned XGBoost model to identify
the minimum viable feature set. Uses gain-based importance (SHAP proxy)
and iterative removal with accuracy/logloss monitoring.

SHAP replacement note:
  In production, install the `shap` package and replace gain-based importance
  with `shap.TreeExplainer(booster).shap_values(X)` for per-sample attribution.
  The total_gain importance used here is an aggregate proxy.

This module complements the group-level ablation in
alphaforge.validation.ablation by operating at the individual feature level
with a tuned model rather than group removal with default hyperparameters.

Usage:
    from alphaforge.tuning.ablation import (
        compute_tuned_importance,
        run_feature_ablation,
        recommend_minimum_feature_set,
    )

    X, y = load_data()
    result = run_feature_ablation(X, y, feature_names=feature_names)
    mvf = result.minimum_viable_features  # ~15 features
    print(f"Reduced from {result.initial_feature_count} to {len(mvf)} features")
    print(f"Accuracy retained: {result.accuracy_retained:.2%}")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xgboost as xgb

from alphaforge.training.xgb_trainer import XGBoostTrainer


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default tuned hyperparameters (more aggressive than conservative SWING baseline)
# These approximate what an Optuna study would converge to for the SWING feature set.
TUNED_HYPERPARAMS: Dict[str, Any] = {
    "objective": "multi:softprob",
    "num_class": 3,
    "max_depth": 6,
    "learning_rate": 0.1,
    "n_estimators": 300,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "min_child_weight": 3,
    "gamma": 0.05,
    "reg_alpha": 0.05,
    "reg_lambda": 0.5,
    "eval_metric": "mlogloss",
    "early_stopping_rounds": 30,
    "random_state": 42,
    "verbosity": 0,
    "tree_method": "hist",
}

# Relative importance threshold: features below this fraction of max
# importance are candidates for ablation
DEFAULT_IMPORTANCE_THRESHOLD_REL: float = 0.05  # 5% of max importance

# Maximum allowed relative performance drop when removing a feature.
# If removing a feature causes accuracy to drop by more than this fraction
# relative to baseline, the feature is considered "important" and retained.
# Corresponds to the "sharpe_drop < 0.1" criterion adapted for classification
# accuracy as a proxy metric (Sharpe requires simulation integration).
DEFAULT_MAX_PERFORMANCE_DROP_REL: float = 0.10  # 10% relative accuracy drop

# Target feature count range for minimum viable feature set
TARGET_FEATURE_MIN: int = 12
TARGET_FEATURE_MAX: int = 18


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureAblationResult:
    """Result of feature ablation study.

    Records the complete iterative ablation process and the recommended
    minimum viable feature set.

    All metrics are DESCRIPTIVE classification-quality measures. No profit,
    Sharpe, win-rate, or expectancy claims are made.
    """

    # Feature importance ranking (descending by normalized gain importance)
    feature_importance_ranked: List[Dict[str, Any]] = field(default_factory=list)

    # Ablation steps: one entry per feature removal attempt
    ablation_steps: List[Dict[str, Any]] = field(default_factory=list)

    # Minimum viable feature set (the recommended subset)
    minimum_viable_features: List[str] = field(default_factory=list)

    # Features that were removed during ablation
    removed_features: List[str] = field(default_factory=list)

    # Baseline performance (all features)
    baseline_accuracy: float = 0.0
    baseline_logloss: float = 0.0

    # Final performance (minimum viable set)
    final_accuracy: float = 0.0
    final_logloss: float = 0.0
    accuracy_retained: float = 0.0  # final / baseline

    # Feature counts
    initial_feature_count: int = 0
    final_feature_count: int = 0
    target_feature_count: int = 15

    # Timing
    total_duration_seconds: float = 0.0

    # Limitations
    limitations: List[str] = field(default_factory=lambda: [
        "Feature ablation uses classification accuracy/logloss as proxy metrics "
        "— does NOT measure trading profit or Sharpe ratio",
        "Gain-based importance is a SHAP proxy; per-sample SHAP attribution may differ",
        "Iterative ablation results depend on removal order and may not be globally optimal",
        "Minimum viable feature set is specific to the dataset and hyperparameters used",
        "Accuracy retention threshold is heuristic — validate with walk-forward analysis",
    ])


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def compute_tuned_importance(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Optional[List[str]] = None,
    hyperparameters: Optional[Dict[str, Any]] = None,
) -> Tuple[xgb.Booster, Dict[str, float], float, float]:
    """Train a tuned model and compute per-feature gain importance.

    Uses XGBoost total_gain importance (sum of gain from all splits that use
    the feature), normalized to sum to 1.0 for cross-run comparability.

    Args:
        X: Feature matrix (n_samples, n_features). Must be float64.
        y: Label vector (n_samples,). String or integer labels.
        feature_names: Optional list of feature names for human-readable keys.
        hyperparameters: Optional hyperparameter overrides.
            If None, uses TUNED_HYPERPARAMS.

    Returns:
        Tuple of (booster, importance_dict, accuracy, logloss) where
        importance_dict maps feature name -> normalized gain importance [0, 1].
    """
    hp = dict(TUNED_HYPERPARAMS)
    if hyperparameters:
        hp.update(hyperparameters)

    trainer = XGBoostTrainer(mode="SWING", hyperparameters=hp)
    result = trainer.train(X, y, feature_names=feature_names)

    booster = result.model

    # Compute gain importance
    importance = _compute_gain_importance(booster, feature_names)

    # Normalize to sum to 1.0
    total = sum(importance.values())
    if total > 0:
        importance = {k: v / total for k, v in importance.items()}

    accuracy = float(result.train_metrics.get("accuracy", 0.0))
    logloss = float(result.train_metrics.get("logloss", 0.0))

    return booster, importance, accuracy, logloss


def run_feature_ablation(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Optional[List[str]] = None,
    hyperparameters: Optional[Dict[str, Any]] = None,
    max_performance_drop_rel: float = DEFAULT_MAX_PERFORMANCE_DROP_REL,
    target_feature_count: Optional[int] = None,
) -> FeatureAblationResult:
    """Run feature ablation to identify the minimum viable feature set.

    Process:
    1. Train a tuned model on all features and compute gain importance.
    2. Rank features by importance descending.
    3. Iteratively remove the lowest-ranked feature remaining.
    4. After each removal, retrain and measure accuracy.
    5. Stop when the next removal exceeds ``max_performance_drop_rel`` or
       ``target_feature_count`` is reached.

    The result includes the full ablation history so callers can analyze
    the trade-off curve and pick an alternative stopping point.

    Args:
        X: Feature matrix (n_samples, n_features). Must be float64.
        y: Label vector (n_samples,). String or integer labels.
        feature_names: List of feature names matching X columns.
            If None, generates f0..fN names.
        hyperparameters: Optional hyperparameter overrides forwarded to
            XGBoostTrainer. If None, uses TUNED_HYPERPARAMS.
        max_performance_drop_rel: Maximum allowed relative accuracy drop
            before stopping (default 0.10 = 10% of baseline accuracy).
        target_feature_count: Target number of features to aim for.
            If None, defaults to the midpoint of [TARGET_FEATURE_MIN,
            TARGET_FEATURE_MAX].

    Returns:
        FeatureAblationResult with complete ablation history and the
        minimum viable feature set that satisfies the performance constraint.

    Raises:
        ValueError: If inputs are invalid.
        TypeError: If X or y have wrong types.
    """
    _validate_ablation_inputs(X, y, feature_names)

    n_features = X.shape[1]
    if feature_names is None:
        feature_names = [f"f{i}" for i in range(n_features)]

    if target_feature_count is None:
        target_feature_count = (TARGET_FEATURE_MIN + TARGET_FEATURE_MAX) // 2

    # Clamp target to actual feature count
    target_feature_count = min(target_feature_count, n_features - 1)

    total_start = time.monotonic()

    # Step 1: Train tuned model on all features, compute importance
    _, importance, baseline_accuracy, baseline_logloss = compute_tuned_importance(
        X, y,
        feature_names=feature_names,
        hyperparameters=hyperparameters,
    )

    if baseline_accuracy <= 0:
        raise ValueError(
            f"Baseline accuracy is {baseline_accuracy}. "
            "Model failed to learn — check data quality."
        )

    # Rank features by importance descending
    ranked = sorted(importance.items(), key=lambda x: x[1], reverse=True)

    ranked_list: List[Dict[str, Any]] = [
        {
            "name": name,
            "importance": round(float(val), 6),
            "rank": i + 1,
        }
        for i, (name, val) in enumerate(ranked)
    ]

    # Step 2: Iteratively remove lowest-importance features
    # We maintain an ordered list of remaining features (sorted by importance)
    remaining_features = [name for name, _ in ranked]
    ablation_steps: List[Dict[str, Any]] = []
    removed_features: List[str] = []
    stop = False

    while len(remaining_features) > max(2, target_feature_count) and not stop:
        # The lowest-importance feature in the remaining set
        lowest_feat = remaining_features[-1]

        # Build reduced feature set (exclude lowest)
        reduced_features = remaining_features[:-1]
        reduced_indices = [feature_names.index(f) for f in reduced_features]
        X_reduced = X[:, reduced_indices]

        # Train and evaluate on reduced set
        reduced_accuracy, reduced_logloss = _train_and_evaluate_reduced(
            X_reduced, y,
            feature_names=reduced_features,
            hyperparameters=hyperparameters,
        )

        # Compute relative accuracy drop
        accuracy_drop = baseline_accuracy - reduced_accuracy
        rel_drop = accuracy_drop / max(baseline_accuracy, 1e-10)

        step: Dict[str, Any] = {
            "step": len(ablation_steps) + 1,
            "removed_feature": lowest_feat,
            "remaining_features": len(reduced_features),
            "accuracy": reduced_accuracy,
            "logloss": reduced_logloss,
            "accuracy_drop": accuracy_drop,
            "relative_accuracy_drop": rel_drop,
        }

        # Check stopping criterion: removing this feature drops accuracy too much
        if rel_drop > max_performance_drop_rel:
            step["stopping_reason"] = (
                f"Relative accuracy drop {rel_drop:.4f} exceeds threshold "
                f"{max_performance_drop_rel:.4f} — feature '{lowest_feat}' "
                f"is informative, not noise"
            )
            ablation_steps.append(step)
            # Do NOT add lowest_feat to removed_features — we backtracked.
            # The minimum viable set remains `remaining_features` (including
            # lowest_feat).
            stop = True
            break

        # Check if we reached target count
        if len(reduced_features) <= target_feature_count:
            step["stopping_reason"] = (
                f"Reached target feature count {target_feature_count}"
            )
            ablation_steps.append(step)
            removed_features.append(lowest_feat)
            remaining_features = reduced_features
            break

        # Commit the removal and continue
        ablation_steps.append(step)
        removed_features.append(lowest_feat)
        remaining_features = reduced_features

    # Step 3: Train final model on the minimum viable set
    final_indices = [feature_names.index(f) for f in remaining_features]
    X_final = X[:, final_indices]
    _, final_accuracy, final_logloss = _train_and_evaluate_return_accuracy(
        X_final, y,
        feature_names=remaining_features,
        hyperparameters=hyperparameters,
    )

    total_duration = time.monotonic() - total_start

    return FeatureAblationResult(
        feature_importance_ranked=ranked_list,
        ablation_steps=ablation_steps,
        minimum_viable_features=remaining_features,
        removed_features=removed_features,
        baseline_accuracy=baseline_accuracy,
        baseline_logloss=baseline_logloss,
        final_accuracy=final_accuracy,
        final_logloss=final_logloss,
        accuracy_retained=(
            final_accuracy / max(baseline_accuracy, 1e-10)
            if baseline_accuracy > 0 else 0.0
        ),
        initial_feature_count=n_features,
        final_feature_count=len(remaining_features),
        target_feature_count=target_feature_count,
        total_duration_seconds=total_duration,
    )


def recommend_minimum_feature_set(
    result: FeatureAblationResult,
    min_features: int = TARGET_FEATURE_MIN,
    max_features: int = TARGET_FEATURE_MAX,
    max_accuracy_drop_rel: float = DEFAULT_MAX_PERFORMANCE_DROP_REL,
) -> Dict[str, Any]:
    """Analyze ablation results and suggest the optimal feature set.

    Scans the ablation steps to find the best trade-off between feature
    reduction and accuracy retention within the given constraints.

    Args:
        result: FeatureAblationResult from run_feature_ablation().
        min_features: Minimum acceptable feature count.
        max_features: Maximum desired feature count.
        max_accuracy_drop_rel: Maximum acceptable relative accuracy drop.

    Returns:
        Dict with:
            recommended_feature_count (int): Number of features in the
                recommended set.
            recommended_features (List[str]): Feature names in the
                recommended set.
            expected_accuracy (float): Expected accuracy of the recommended
                set (from the ablation step).
            expected_accuracy_retained (float): Fraction of baseline accuracy
                retained.
            feature_reduction_ratio (float): final / initial feature count.
            step_used (int): Which ablation step the recommendation is based on.
    """
    steps = result.ablation_steps

    # Find the best step within constraints — prefer higher feature reduction
    # while staying within accuracy drop bounds
    best_step: Optional[Dict[str, Any]] = None

    for step in reversed(steps):
        remaining = step["remaining_features"]
        rel_drop = step["relative_accuracy_drop"]
        if min_features <= remaining <= max_features and rel_drop <= max_accuracy_drop_rel:
            best_step = step
            break

    # Fallback: step with lowest accuracy drop within feature range
    if best_step is None and steps:
        valid = [
            s for s in steps
            if min_features <= s["remaining_features"] <= max_features
        ]
        if valid:
            best_step = min(valid, key=lambda s: s["relative_accuracy_drop"])
        else:
            # Out of range — use the last step regardless
            best_step = steps[-1]

    # Determine recommended feature set
    if best_step is not None:
        rec_count = best_step["remaining_features"]
        expected_acc = best_step["accuracy"]
        expected_retained = 1.0 - best_step["relative_accuracy_drop"]
        step_used = best_step["step"]
    else:
        rec_count = result.final_feature_count
        expected_acc = result.final_accuracy
        expected_retained = result.accuracy_retained
        step_used = 0

    return {
        "recommended_feature_count": rec_count,
        "recommended_features": list(result.minimum_viable_features),
        "expected_accuracy": expected_acc,
        "expected_accuracy_retained": expected_retained,
        "feature_reduction_ratio": (
            rec_count / max(result.initial_feature_count, 1)
        ),
        "constraints_applied": {
            "min_features": min_features,
            "max_features": max_features,
            "max_accuracy_drop_rel": max_accuracy_drop_rel,
        },
        "step_used": step_used,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_gain_importance(
    booster: xgb.Booster,
    feature_names: Optional[List[str]] = None,
) -> Dict[str, float]:
    """Extract raw gain importance from a booster.

    Tries total_gain first, falls back to total_cover, then weight.
    """
    try:
        score_map = booster.get_score(importance_type="total_gain")
    except Exception:
        try:
            score_map = booster.get_score(importance_type="total_cover")
        except Exception:
            score_map = booster.get_score(importance_type="weight")

    if not score_map:
        return {}

    # Map XGBoost internal keys (f0, f1, ...) to human-readable names
    result: Dict[str, float] = {}
    for key, value in score_map.items():
        if feature_names:
            try:
                idx = int(key[1:])  # f0 -> 0, f12 -> 12
            except (ValueError, IndexError):
                result[key] = float(value)
                continue
            if 0 <= idx < len(feature_names):
                result[feature_names[idx]] = float(value)
            else:
                result[key] = float(value)
        else:
            result[key] = float(value)

    return result


def _validate_ablation_inputs(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Optional[List[str]] = None,
) -> None:
    """Validate inputs for feature ablation studies."""
    if not isinstance(X, np.ndarray):
        raise TypeError(f"X must be numpy.ndarray, got {type(X).__name__}")
    if not isinstance(y, np.ndarray):
        raise TypeError(f"y must be numpy.ndarray, got {type(y).__name__}")
    if X.ndim != 2:
        raise ValueError(f"X must be 2D, got {X.ndim}D")
    if y.ndim != 1:
        raise ValueError(f"y must be 1D, got {y.ndim}D")
    if len(X) != len(y):
        raise ValueError(
            f"X and y must have same length, got {len(X)} and {len(y)}"
        )
    if len(X) < 10:
        raise ValueError(f"Need at least 10 samples, got {len(X)}")
    if np.all(np.isnan(X)):
        raise ValueError("X contains all NaN values")
    if feature_names is not None:
        if len(feature_names) != X.shape[1]:
            raise ValueError(
                f"feature_names length ({len(feature_names)}) must match "
                f"X columns ({X.shape[1]})"
            )


def _train_and_evaluate_reduced(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Optional[List[str]] = None,
    hyperparameters: Optional[Dict[str, Any]] = None,
) -> Tuple[float, float]:
    """Train a tuned model on reduced data and return (accuracy, logloss)."""
    hp = dict(TUNED_HYPERPARAMS)
    if hyperparameters:
        hp.update(hyperparameters)

    trainer = XGBoostTrainer(mode="SWING", hyperparameters=hp)
    result = trainer.train(X, y, feature_names=feature_names)

    accuracy = float(result.train_metrics.get("accuracy", 0.0))
    logloss = float(result.train_metrics.get("logloss", 0.0))

    return accuracy, logloss


def _train_and_evaluate_return_accuracy(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Optional[List[str]] = None,
    hyperparameters: Optional[Dict[str, Any]] = None,
) -> Tuple[float, float, float]:
    """Train a tuned model and return (duration, accuracy, logloss).

    This is a convenience wrapper used for the final evaluation.
    It returns training duration as well as metrics.
    """
    hp = dict(TUNED_HYPERPARAMS)
    if hyperparameters:
        hp.update(hyperparameters)

    trainer = XGBoostTrainer(mode="SWING", hyperparameters=hp)
    start = time.monotonic()
    result = trainer.train(X, y, feature_names=feature_names)
    duration = time.monotonic() - start

    accuracy = float(result.train_metrics.get("accuracy", 0.0))
    logloss = float(result.train_metrics.get("logloss", 0.0))

    return duration, accuracy, logloss
