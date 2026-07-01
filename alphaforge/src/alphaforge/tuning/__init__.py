"""AlphaForge Tuning — hyperparameter search space and Optuna integration.

This module defines mode-specific XGBoost hyperparameter search spaces
for financial time-series optimisation. It integrates with Optuna for
automated hyperparameter tuning.

Modules:
    search_space: XGBoost search space definitions per mode, Optuna
        integration via suggest_params() and build_objective().
"""

from alphaforge.tuning.search_space import (
    AGGRESSIVE_SCALP_SEARCH_SPACE,
    SCALP_SEARCH_SPACE,
    SWING_SEARCH_SPACE,
    ParameterRange,
    SearchSpace,
    all_search_spaces,
    build_objective,
    get_search_space,
    param_bounds,
    suggest_params,
)

__all__ = [
    "AGGRESSIVE_SCALP_SEARCH_SPACE",
    "ParameterRange",
    "SCALP_SEARCH_SPACE",
    "SearchSpace",
    "SWING_SEARCH_SPACE",
    "all_search_spaces",
    "build_objective",
    "get_search_space",
    "param_bounds",
    "suggest_params",
]
