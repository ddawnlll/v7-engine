"""AlphaForge Tuning — model hyperparameter optimization and feature ablation.

This package provides tools for:
1. Hyperparameter tuning (Optuna integration)
2. Feature ablation with tuned models — identifying minimum viable feature sets

Modules:
    ablation: Feature ablation using tuned XGBoost models to identify the
        minimum viable feature set. Complements the group-level ablation in
        alphaforge.validation.ablation by operating at individual feature
        level with tuned hyperparameters.
"""

from alphaforge.tuning.ablation import (
    DEFAULT_IMPORTANCE_THRESHOLD_REL,
    DEFAULT_MAX_PERFORMANCE_DROP_REL,
    TUNED_HYPERPARAMS,
    FeatureAblationResult,
    compute_tuned_importance,
    recommend_minimum_feature_set,
    run_feature_ablation,
)

__all__ = [
    "DEFAULT_IMPORTANCE_THRESHOLD_REL",
    "DEFAULT_MAX_PERFORMANCE_DROP_REL",
    "TUNED_HYPERPARAMS",
    "FeatureAblationResult",
    "compute_tuned_importance",
    "recommend_minimum_feature_set",
    "run_feature_ablation",
]
