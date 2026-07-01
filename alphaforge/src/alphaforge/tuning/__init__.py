"""AlphaForge Tuning — mode-specific hyperparameter optimisation.

This package defines canonical parameter search spaces for Optuna-based
hyperparameter tuning. Each mode (SWING, SCALP, AGGRESSIVE_SCALP) has a
dedicated profile encoding its learning rate range, tree depth bounds,
and regularisation levels.

Modules:
    mode_profiles: ModeTuningProfile, canonical profiles, suggest + save helpers.
"""

from alphaforge.tuning.mode_profiles import (
    AGGRESSIVE_SCALP_TUNING,
    DEFAULT_PARAMS_DIR,
    ModeTuningProfile,
    SCALP_TUNING,
    SWING_TUNING,
    TuningCategoricalParam,
    TuningParamRange,
    all_tuning_profiles,
    get_tuning_profile,
    load_tuning_params,
    save_tuning_params,
    suggest_params,
)

__all__ = [
    "AGGRESSIVE_SCALP_TUNING",
    "DEFAULT_PARAMS_DIR",
    "ModeTuningProfile",
    "SCALP_TUNING",
    "SWING_TUNING",
    "TuningCategoricalParam",
    "TuningParamRange",
    "all_tuning_profiles",
    "get_tuning_profile",
    "load_tuning_params",
    "save_tuning_params",
    "suggest_params",
]
