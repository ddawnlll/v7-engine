"""AlphaForge Tuning — hyperparameter optimization via Optuna.

This package provides the core hyperparameter optimization engine for
AlphaForge mode-specific models. It integrates Optuna with TPE sampler
and ASHA pruning, SQLite study persistence, and study lifecycle management.

Design:
- TPE sampler (Tree-structured Parzen Estimator) for efficient search
- ASHA (Asynchronous Successive Halving Algorithm) pruning for early stopping
- SQLite persistence for study durability and resume capability
- Mode-specific search spaces for SWING, SCALP, AGGRESSIVE_SCALP

Usage:
    from tuning.optuna_tuner import OptunaTuner, search_spaces

    tuner = OptunaTuner(
        study_name="swing_tuning_v1",
        storage="sqlite:///studies/optuna_studies.db",
        direction="maximize",
    )
    tuner.optimize(objective_fn, n_trials=50)

    best_params = tuner.best_params
    print(tuner.study_summary)

Authority boundary: see alphaforge/docs/discovery_authority.md
"""

from alphaforge.src.tuning.optuna_tuner import (
    DEFAULT_N_TRIALS,
    DEFAULT_TIMEOUT_SECONDS,
    STUDIES_DIR,
    OptunaTuner,
    search_spaces,
    list_studies,
    delete_study,
)

__all__ = [
    "DEFAULT_N_TRIALS",
    "DEFAULT_TIMEOUT_SECONDS",
    "STUDIES_DIR",
    "OptunaTuner",
    "search_spaces",
    "list_studies",
    "delete_study",
]
