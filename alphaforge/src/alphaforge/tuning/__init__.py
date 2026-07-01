"""AlphaForge Tuning — hyperparameter optimization with Optuna pruning.

This package provides Optuna-based hyperparameter tuning with aggressive
ASHA-style trial pruning (MedianPruner) and early stopping callbacks.

Modules:
    optuna_tuner: Optuna study management, pruning callbacks, search spaces.
"""

from alphaforge.tuning.optuna_tuner import (
    EARLY_STOPPING_ROUNDS,
    PRUNER_CONFIG,
    XGBoostPruningCallback,
    create_study,
    default_swing_search_space,
    get_best_params,
    run_tuning,
)

__all__ = [
    "EARLY_STOPPING_ROUNDS",
    "PRUNER_CONFIG",
    "XGBoostPruningCallback",
    "create_study",
    "default_swing_search_space",
    "get_best_params",
    "run_tuning",
]
