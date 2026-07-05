"""AlphaForge Tuning — hyperparameter optimization, search spaces, and model tuning.

This package provides:
1. XGBoost hyperparameter search spaces per trading mode (search_space module)
2. Mode-specific tuning profiles (mode_profiles module)
3. Optuna integration with ASHA-style Median Pruning (optuna_tuner module)
4. Multi-objective Pareto optimization (moo module)
5. Feature ablation with tuned models (ablation module)
6. Nested walk-forward autotune engine (autotune module)
7. Objective functions for multi-objective tuning (objectives module)

Domain boundary: AlphaForge owns tuning evidence. V7 owns final acceptance.
"""

# ---------------------------------------------------------------------------
# Search spaces — canonical hyperparameter ranges per mode
# ---------------------------------------------------------------------------
from alphaforge.tuning.search_space import (
    AGGRESSIVE_SCALP_SEARCH_SPACE,
    ParameterRange,
    SCALP_SEARCH_SPACE,
    SearchSpace,
    SWING_SEARCH_SPACE,
    all_search_spaces,
    build_objective,
    get_search_space,
    param_bounds,
    suggest_params,
)

# ---------------------------------------------------------------------------
# Feature ablation with tuned models
# ---------------------------------------------------------------------------
from alphaforge.tuning.ablation import (
    DEFAULT_IMPORTANCE_THRESHOLD_REL,
    DEFAULT_MAX_PERFORMANCE_DROP_REL,
    TUNED_HYPERPARAMS,
    FeatureAblationResult,
    compute_tuned_importance,
    recommend_minimum_feature_set,
    run_feature_ablation,
)

# ---------------------------------------------------------------------------
# Autotune engine — nested walk-forward validation
# ---------------------------------------------------------------------------
from alphaforge.tuning.autotune import (
    AutotuneResult,
    DEFAULT_GRID,
    HyperparameterGrid,
    InnerTrialResult,
    NestedWFVAutotune,
    NestedWFVConfig,
    OuterFoldResult,
    run_nested_wfv_autotune,
)

# ---------------------------------------------------------------------------
# Package-level exports — search spaces is the canonical public API
# ---------------------------------------------------------------------------
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
