"""XGBoost Hyperparameter Search Space for Financial Time-Series.

This module defines mode-specific XGBoost hyperparameter search spaces
for Optuna-based hyperparameter optimization. Ranges are informed by:

- arXiv 2601.08896 (NEPSE XGBoost forecasting framework)
- XGBoost official documentation on regularization parameters
- Financial time-series best practices: conservative tree complexity,
  log-uniform sampling for regularization parameters, mode-specific
  constraints based on primary timeframe

Design constraints (LOCKED_INITIAL_BASELINE):
  - Search spaces are defined per-mode (SWING, SCALP, AGGRESSIVE_SCALP)
  - Regularization parameters (reg_alpha, reg_lambda, learning_rate)
    use log-uniform sampling to handle wide ranges
  - Tree complexity parameters (max_depth, n_estimators) are bounded
    conservatively for financial TS to prevent overfitting
  - Higher-frequency modes (SCALP, AGGRESSIVE_SCALP) apply stronger
    regularization defaults
  - All spaces integrate with Optuna's suggest_* API
  - Optuna is an optional dependency; the module functions without it

Example:
    >>> from alphaforge.tuning.search_space import get_search_space, suggest_params
    >>> space = get_search_space("SWING")
    >>> # With Optuna:
    >>> import optuna
    >>> study = optuna.create_study(direction="minimize")
    >>> objective = build_objective(X_train, y_train, mode="SWING")
    >>> study.optimize(objective, n_trials=space.n_trials)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Optuna import
# ---------------------------------------------------------------------------

try:
    import optuna
    from optuna.trial import Trial

    _HAS_OPTUNA = True
except ImportError:
    _HAS_OPTUNA = False

    # Minimal stub for type-checking when Optuna is absent
    class Trial:  # type: ignore[no-redef]
        """Stand-in stub when optuna is not installed."""

        def suggest_float(
            self, name: str, low: float, high: float, *, log: bool = False
        ) -> float:
            raise ImportError("Optuna is required for suggest_float")

        def suggest_int(
            self,
            name: str,
            low: int,
            high: int,
            *,
            step: int = 1,
            log: bool = False,
        ) -> int:
            raise ImportError("Optuna is required for suggest_int")


# ---------------------------------------------------------------------------
# Search Space Data Structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParameterRange:
    """Definition of a single hyperparameter's search range.

    Fields:
        name: Hyperparameter name (XGBoost param key, e.g. 'max_depth').
        low: Lower bound of the search range.
        high: Upper bound of the search range.
        log: Sample in log-uniform space (for wide-range params).
        param_type: 'int' for integer, 'float' for float parameters.
        step: Step size for integer parameters (None = 1).
    """

    name: str
    low: float
    high: float
    log: bool = False
    param_type: str = "float"
    step: Optional[int] = None


@dataclass(frozen=True)
class SearchSpace:
    """Complete XGBoost hyperparameter search space for a single trading mode.

    Fields:
        mode: Trading mode identifier (SWING, SCALP, AGGRESSIVE_SCALP).
        description: Human-readable description of this search space.
        ranges: List of ParameterRange definitions for Optuna.
        n_trials: Default number of Optuna trials for this mode.
        timeout_seconds: Default timeout per study in seconds.
        fixed_params: Parameters that are fixed (not tuned by Optuna).
    """

    mode: str
    description: str = ""
    ranges: List[ParameterRange] = field(default_factory=list)
    n_trials: int = 100
    timeout_seconds: int = 600
    fixed_params: Dict[str, Any] = field(default_factory=dict)

    def fixed_params_without(self, *keys: str) -> Dict[str, Any]:
        """Return fixed_params excluding specified keys.

        Args:
            *keys: Parameter keys to exclude.

        Returns:
            Filtered fixed params dict.
        """
        return {k: v for k, v in self.fixed_params.items() if k not in keys}


# ---------------------------------------------------------------------------
# Base XGBoost fixed parameters (shared across all modes)
# ---------------------------------------------------------------------------

_BASE_XGB_PARAMS: Dict[str, Any] = {
    "objective": "multi:softprob",
    "num_class": 3,
    "eval_metric": "mlogloss",
    "random_state": 42,
    "tree_method": "hist",
    "verbosity": 0,
}

# ---------------------------------------------------------------------------
# Per-Mode Search Space Definitions
# ---------------------------------------------------------------------------

SWING_SEARCH_SPACE = SearchSpace(
    mode="SWING",
    description=(
        "SWING mode — conservative baseline for 4h primary timeframe. "
        "Moderate tree depth (3-10) and estimators (50-500) with "
        "log-uniform regularization sampling. Appropriate for lower-frequency "
        "strategies where noise per bar is lower."
    ),
    ranges=[
        ParameterRange(
            name="learning_rate", low=0.01, high=0.3, log=True, param_type="float"
        ),
        ParameterRange(
            name="max_depth", low=3, high=10, param_type="int"
        ),
        ParameterRange(
            name="n_estimators", low=50, high=500, param_type="int"
        ),
        ParameterRange(
            name="subsample", low=0.5, high=1.0, param_type="float"
        ),
        ParameterRange(
            name="colsample_bytree", low=0.3, high=1.0, param_type="float"
        ),
        ParameterRange(
            name="min_child_weight", low=1, high=15, param_type="int"
        ),
        ParameterRange(
            name="gamma", low=0.0, high=5.0, param_type="float"
        ),
        ParameterRange(
            name="reg_alpha", low=1e-8, high=5.0, log=True, param_type="float"
        ),
        ParameterRange(
            name="reg_lambda", low=1e-8, high=5.0, log=True, param_type="float"
        ),
    ],
    n_trials=100,
    timeout_seconds=600,
    fixed_params=dict(_BASE_XGB_PARAMS),
)

SCALP_SEARCH_SPACE = SearchSpace(
    mode="SCALP",
    description=(
        "SCALP mode — tighter regularization for 1h primary timeframe. "
        "Higher noise per bar requires stronger regularization: lower "
        "max_depth cap (3-8), fewer estimators (50-300), higher "
        "min_child_weight floor (3)."
    ),
    ranges=[
        ParameterRange(
            name="learning_rate", low=0.01, high=0.3, log=True, param_type="float"
        ),
        ParameterRange(
            name="max_depth", low=3, high=8, param_type="int"
        ),
        ParameterRange(
            name="n_estimators", low=50, high=300, param_type="int"
        ),
        ParameterRange(
            name="subsample", low=0.5, high=1.0, param_type="float"
        ),
        ParameterRange(
            name="colsample_bytree", low=0.3, high=1.0, param_type="float"
        ),
        ParameterRange(
            name="min_child_weight", low=3, high=15, param_type="int"
        ),
        ParameterRange(
            name="gamma", low=0.0, high=5.0, param_type="float"
        ),
        ParameterRange(
            name="reg_alpha", low=1e-8, high=5.0, log=True, param_type="float"
        ),
        ParameterRange(
            name="reg_lambda", low=1e-8, high=5.0, log=True, param_type="float"
        ),
    ],
    n_trials=100,
    timeout_seconds=600,
    fixed_params=dict(_BASE_XGB_PARAMS),
)

AGGRESSIVE_SCALP_SEARCH_SPACE = SearchSpace(
    mode="AGGRESSIVE_SCALP",
    description=(
        "AGGRESSIVE_SCALP mode — strongest regularization for 15m primary "
        "timeframe. Highest noise regime: lowest max_depth (2-6), fewest "
        "estimators (30-200), highest min_child_weight floor (5), wider "
        "gamma (0-8) and regularization penalty ranges (1e-8 to 10.0)."
    ),
    ranges=[
        ParameterRange(
            name="learning_rate", low=0.005, high=0.2, log=True, param_type="float"
        ),
        ParameterRange(
            name="max_depth", low=2, high=6, param_type="int"
        ),
        ParameterRange(
            name="n_estimators", low=30, high=200, param_type="int"
        ),
        ParameterRange(
            name="subsample", low=0.4, high=1.0, param_type="float"
        ),
        ParameterRange(
            name="colsample_bytree", low=0.2, high=1.0, param_type="float"
        ),
        ParameterRange(
            name="min_child_weight", low=5, high=20, param_type="int"
        ),
        ParameterRange(
            name="gamma", low=0.0, high=8.0, param_type="float"
        ),
        ParameterRange(
            name="reg_alpha", low=1e-8, high=10.0, log=True, param_type="float"
        ),
        ParameterRange(
            name="reg_lambda", low=1e-8, high=10.0, log=True, param_type="float"
        ),
    ],
    n_trials=80,
    timeout_seconds=900,
    fixed_params=dict(_BASE_XGB_PARAMS),
)

# Frozen lookup dict — maps mode → SearchSpace
_SEARCH_SPACES: Dict[str, SearchSpace] = {
    "SWING": SWING_SEARCH_SPACE,
    "SCALP": SCALP_SEARCH_SPACE,
    "AGGRESSIVE_SCALP": AGGRESSIVE_SCALP_SEARCH_SPACE,
}


# ---------------------------------------------------------------------------
# Public API — space lookup
# ---------------------------------------------------------------------------


def get_search_space(mode: str) -> SearchSpace:
    """Return the SearchSpace for a given trading mode.

    Args:
        mode: Trading mode ('SWING', 'SCALP', 'AGGRESSIVE_SCALP').

    Returns:
        Frozen SearchSpace for the mode.

    Raises:
        ValueError: Unknown mode.
    """
    if mode not in _SEARCH_SPACES:
        raise ValueError(
            f"Unknown mode: '{mode}'. Valid modes: {sorted(_SEARCH_SPACES.keys())}"
        )
    return _SEARCH_SPACES[mode]


def all_search_spaces() -> Dict[str, SearchSpace]:
    """Return all mode-specific search spaces.

    Returns:
        Dict mapping mode -> SearchSpace.
    """
    return dict(_SEARCH_SPACES)


def param_bounds(mode: str) -> Dict[str, Tuple[float, float]]:
    """Return (low, high) bounds for every tuned parameter in a mode.

    Useful for visualising or documenting the search space without
    instantiating an Optuna trial.

    Args:
        mode: Trading mode.

    Returns:
        Dict mapping param name -> (low, high).
    """
    space = get_search_space(mode)
    bounds: Dict[str, Tuple[float, float]] = {}
    for rng in space.ranges:
        bounds[rng.name] = (rng.low, rng.high)
    return bounds


# ---------------------------------------------------------------------------
# Optuna Integration
# ---------------------------------------------------------------------------


def suggest_params(trial: Trial, space: SearchSpace) -> Dict[str, Any]:
    """Sample hyperparameters from a SearchSpace using an Optuna trial.

    Converts each ParameterRange in the space into the corresponding
    ``trial.suggest_*`` call and merges with fixed params.

    Args:
        trial: An active Optuna Trial object.
        space: The SearchSpace to sample from.

    Returns:
        Dict of hyperparameter name -> sampled value, including fixed params.

    Raises:
        ImportError: If Optuna is not installed.
    """
    if not _HAS_OPTUNA:
        raise ImportError(
            "Optuna is required for suggest_params. "
            "Install it with: pip install optuna"
        )

    params: Dict[str, Any] = dict(space.fixed_params)

    for rng in space.ranges:
        if rng.param_type == "int":
            low = int(rng.low)
            high = int(rng.high)
            params[rng.name] = trial.suggest_int(
                rng.name, low, high, step=rng.step or 1, log=rng.log
            )
        else:
            params[rng.name] = trial.suggest_float(
                rng.name, rng.low, rng.high, log=rng.log
            )

    return params


def build_objective(
    X: np.ndarray,
    y: np.ndarray,
    mode: str = "SWING",
    feature_names: Optional[List[str]] = None,
    val_fraction: float = 0.2,
    random_seed: int = 42,
    early_stopping_rounds: int = 20,
) -> Callable[[Trial], float]:
    """Build an Optuna objective function for XGBoost hyperparameter tuning.

    The objective samples params from the mode's search space, trains an
    XGBoost model with a train/validation split, and returns the validation
    log-loss (minimised by Optuna).

    This function delays the xgboost import so that merely importing
    search_space does NOT pull in xgboost.

    Args:
        X: Feature matrix of shape (n_samples, n_features).
        y: Label vector — string or integer labels.
        mode: Trading mode for search space selection.
        feature_names: Optional list of feature names.
        val_fraction: Fraction of data to hold out for validation.
        random_seed: Random seed for reproducibility.
        early_stopping_rounds: Early stopping patience.

    Returns:
        Callable ``objective(trial) -> float`` suitable for
        ``study.optimize()``.

    Raises:
        ImportError: If Optuna is not installed.
    """
    if not _HAS_OPTUNA:
        raise ImportError(
            "Optuna is required for build_objective. "
            "Install it with: pip install optuna"
        )

    space = get_search_space(mode)

    def objective(trial: Trial) -> float:
        # Sample hyperparameters
        params = suggest_params(trial, space)

        # --- Lazy xgboost import ---
        import xgboost as xgb

        # --- Prepare data ---
        # Convert string labels to integers if needed
        from alphaforge.training.xgb_trainer import LABEL_TO_INT, NUM_CLASSES

        if y.dtype.kind in ("U", "S"):
            y_int = np.array([LABEL_TO_INT.get(v, -1) for v in y], dtype=int)
            if (y_int == -1).any():
                raise ValueError("Unknown label found in y")
        elif y.dtype.kind in ("i", "u"):
            y_int = y.astype(int)
        else:
            raise ValueError(f"Unsupported label dtype: {y.dtype}")

        n_samples = len(y_int)
        n_val = max(1, int(n_samples * val_fraction))

        rng = np.random.RandomState(random_seed)
        indices = np.arange(n_samples)
        rng.shuffle(indices)

        val_indices = indices[:n_val]
        train_indices = indices[n_val:]

        X_train = X[train_indices]
        y_train = y_int[train_indices]
        X_val = X[val_indices]
        y_val = y_int[val_indices]

        dtrain = xgb.DMatrix(X_train, label=y_train)
        dval = xgb.DMatrix(X_val, label=y_val)
        if feature_names:
            dtrain.feature_names = feature_names
            dval.feature_names = feature_names

        # --- Extract xgboost params (remove non-xgb keys) ---
        xgb_param_keys = {
            "objective", "num_class", "max_depth", "learning_rate",
            "subsample", "colsample_bytree", "min_child_weight",
            "gamma", "reg_alpha", "reg_lambda", "eval_metric",
            "random_state", "verbosity", "tree_method", "device",
        }
        train_params = {k: v for k, v in params.items() if k in xgb_param_keys}

        num_boost_round = params.get("n_estimators", 100)

        evals_result: Dict[str, Any] = {}
        booster: Any = xgb.train(
            params=train_params,
            dtrain=dtrain,
            num_boost_round=num_boost_round,
            evals=[(dtrain, "train"), (dval, "val")],
            evals_result=evals_result,
            early_stopping_rounds=early_stopping_rounds,
            verbose_eval=False,
        )

        # Return validation log-loss as the minimisation target
        val_mlogloss = float(evals_result.get("val", {}).get("mlogloss", [1.0])[-1])
        return val_mlogloss

    return objective
