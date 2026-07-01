"""Optuna hyperparameter tuner with ASHA-style Median Pruning.

Designed for aggressive early termination of bad hyperparameter trials
during XGBoost alpha model training.

Key design decisions:
  - MedianPruner prunes trials whose intermediate performance falls below
    the running median of other trials at the same boosting round.
  - Custom XGBoostPruningCallback translates xgboost eval metrics into
    Optuna intermediate reports so the pruner can make per-round decisions.
  - Trials are expected to complete or be pruned in ~2s each, enabling
    60+ trial studies well under the 120s budget.
  - The objective function uses xgb.train() directly (not XGBoostTrainer)
    to avoid coupling the search to production-mode defaults.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import optuna
import xgboost as xgb
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler
from xgboost.callback import TrainingCallback

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default MedianPruner configuration (ASHA-style aggressive pruning)
PRUNER_CONFIG: Dict[str, Any] = {
    "n_startup_trials": 5,  # Let first 5 trials run fully before pruning
    "n_warmup_steps": 3,    # Let first 3 boosting rounds complete before pruning
    "interval_steps": 1,    # Check pruning eligibility every round
}

# Early stopping rounds for XGBoost training within each trial
EARLY_STOPPING_ROUNDS: int = 10

# Default number of tuning trials
DEFAULT_N_TRIALS: int = 60

# Target: 60 trials < 120s total
TARGET_TRIALS: int = 60
TARGET_DURATION_SECONDS: int = 120

# Observation key for pruning (matches xgboost eval metric name)
PRUNING_OBSERVATION_KEY: str = "val-mlogloss"

LABEL_TO_INT: Dict[str, int] = {
    "LONG_NOW": 0,
    "SHORT_NOW": 1,
    "NO_TRADE": 2,
}

NUM_CLASSES: int = 3

RANDOM_SEED: int = 42

# ---------------------------------------------------------------------------
# Custom XGBoostPruningCallback (standalone — avoids optuna-integration dep)
# ---------------------------------------------------------------------------


class XGBoostPruningCallback(TrainingCallback):
    """XGBoost training callback that reports metrics to an Optuna trial.

    At each boosting iteration, the callback reads the evaluation metric
    from the xgboost evals log and reports it to the Optuna trial via
    ``trial.report()``. If the trial should be pruned (determined by the
    study's pruner), the callback returns ``True`` to halt training early.

    Args:
        trial: The Optuna trial to report intermediate values to.
        observation_key: The metric key to monitor in the evals log.
            Uses ``"data_name-metric_name"`` or bare ``"metric_name"``
            format. Default is ``"val-mlogloss"``.

    Usage::

        pruning_cb = XGBoostPruningCallback(trial=trial)
        xgb.train(params, dtrain, evals=[(dtrain, "train"), (dval, "val")],
                  callbacks=[pruning_cb])
    """

    def __init__(
        self,
        trial: optuna.Trial,
        observation_key: str = PRUNING_OBSERVATION_KEY,
    ) -> None:
        super().__init__()
        self._trial = trial
        self._observation_key = observation_key
        self.pruned: bool = False

    def after_iteration(
        self,
        model: xgb.Booster,
        epoch: int,
        evals_log: xgb.callback.EvalsLog,
    ) -> bool:
        """Check if trial should be pruned after each boosting round.

        Sets ``self.pruned = True`` and returns ``True`` to stop xgboost
        when the pruner decides to kill this trial. The caller's objective
        function is responsible for raising ``optuna.TrialPruned()`` after
        training finishes (checked via ``callback.pruned``).

        Args:
            model: The trained booster (or CVPack for cv).
            epoch: Current boosting round (0-indexed).
            evals_log: Evaluation history dict, structured as
                ``{"data_name": {"metric_name": [values_list]}}``.

        Returns:
            ``True`` if training should stop (trial pruned), ``False`` otherwise.
        """
        for data_name, metrics in evals_log.items():
            for metric_name, values in metrics.items():
                full_key = f"{data_name}-{metric_name}"
                if full_key == self._observation_key or metric_name == self._observation_key:
                    if values:
                        score = values[-1]
                        self._trial.report(score, epoch)
                        if self._trial.should_prune():
                            self.pruned = True
                            logger.debug(
                                "Trial %d pruned at epoch %d (score=%.4f)",
                                self._trial.number,
                                epoch,
                                score,
                            )
                            return True  # signal xgboost to stop
        return False


# ---------------------------------------------------------------------------
# Study creation
# ---------------------------------------------------------------------------


def create_study(
    study_name: Optional[str] = None,
    direction: str = "minimize",
    n_startup_trials: int = PRUNER_CONFIG["n_startup_trials"],
    n_warmup_steps: int = PRUNER_CONFIG["n_warmup_steps"],
    interval_steps: int = PRUNER_CONFIG["interval_steps"],
    seed: int = RANDOM_SEED,
    load_if_exists: bool = False,
) -> optuna.Study:
    """Create an Optuna study configured with MedianPruner.

    The MedianPruner implements ASHA-style pruning: it tracks the median
    intermediate value across all completed trials at each step and prunes
    any trial that falls below that median.

    Args:
        study_name: Optional name for storage/recall.
        direction: ``"minimize"`` (default) for loss metrics like logloss;
            ``"maximize"`` for accuracy-like metrics.
        n_startup_trials: Number of trials that run fully before pruning
            begins (default 5).
        n_warmup_steps: Number of initial boosting rounds where pruning
            is disabled (default 3). Prevents premature pruning of trials
            that start poorly but improve later.
        interval_steps: Check pruning eligibility every N steps (default 1).
        seed: Random seed for the TPE sampler.
        load_if_exists: If True and study_name is given, load existing
            study instead of creating a new one.

    Returns:
        Configured Optuna study ready for ``study.optimize()``.
    """
    pruner = MedianPruner(
        n_startup_trials=n_startup_trials,
        n_warmup_steps=n_warmup_steps,
        interval_steps=interval_steps,
    )
    sampler = TPESampler(seed=seed)

    study = optuna.create_study(
        study_name=study_name,
        direction=direction,
        pruner=pruner,
        sampler=sampler,
        load_if_exists=load_if_exists,
    )
    logger.info(
        "Created study '%s' (direction=%s, pruner=MedianPruner(%d,%d,%d))",
        study.study_name,
        direction,
        n_startup_trials,
        n_warmup_steps,
        interval_steps,
    )
    return study


# ---------------------------------------------------------------------------
# Search spaces
# ---------------------------------------------------------------------------


def default_swing_search_space(trial: optuna.Trial) -> Dict[str, Any]:
    """Default hyperparameter search space for SWING mode XGBoost.

    Provides a reasonable range for each hyperparameter. Uses Optuna's
    ``suggest_*`` methods so the TPE sampler can explore efficiently.

    Args:
        trial: Optuna trial for suggesting parameter values.

    Returns:
        Dict of XGBoost-compatible hyperparameters (without objective/num_class
        which are set by the caller).
    """
    return {
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "learning_rate": trial.suggest_float(
            "learning_rate", 0.01, 0.3, log=True
        ),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
        "gamma": trial.suggest_float("gamma", 0.0, 1.0),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        "n_estimators": trial.suggest_int("n_estimators", 100, 500),
    }


def default_scalp_search_space(trial: optuna.Trial) -> Dict[str, Any]:
    """Hyperparameter search space for SCALP mode XGBoost.

    SCALP models typically benefit from deeper trees and faster learning
    compared to SWING, since they operate on shorter timeframes.

    Args:
        trial: Optuna trial for suggesting parameter values.

    Returns:
        Dict of XGBoost-compatible hyperparameters.
    """
    return {
        "max_depth": trial.suggest_int("max_depth", 4, 10),
        "learning_rate": trial.suggest_float(
            "learning_rate", 0.05, 0.4, log=True
        ),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 8),
        "gamma": trial.suggest_float("gamma", 0.0, 0.5),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 5.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 5.0, log=True),
        "n_estimators": trial.suggest_int("n_estimators", 50, 300),
    }


# ---------------------------------------------------------------------------
# Core tuning function
# ---------------------------------------------------------------------------


def _encode_labels(y: np.ndarray) -> np.ndarray:
    """Encode string labels to integers for training."""
    if y.dtype.kind in ("i", "u"):
        return y.astype(int)
    if y.dtype.kind in ("U", "S"):
        result = np.zeros(len(y), dtype=int)
        for i, label in enumerate(y):
            result[i] = LABEL_TO_INT[str(label)]
        return result
    raise ValueError(f"Unsupported label dtype: {y.dtype}")


def run_tuning(
    X: np.ndarray,
    y: np.ndarray,
    n_trials: int = DEFAULT_N_TRIALS,
    search_space: Optional[Callable[[optuna.Trial], Dict[str, Any]]] = None,
    study: Optional[optuna.Study] = None,
    study_name: Optional[str] = None,
    feature_names: Optional[List[str]] = None,
    val_fraction: float = 0.2,
    random_state: int = RANDOM_SEED,
    early_stopping_rounds: int = EARLY_STOPPING_ROUNDS,
    direction: str = "minimize",
) -> optuna.Study:
    """Run hyperparameter tuning with aggressive MedianPruning.

    Splits data once (fixed train/val split), then runs ``n_trials``
    Optuna trials. Each trial trains an XGBoost model and reports
    intermediate validation logloss to the study's pruner. Bad trials
    are pruned early, typically by fold/round 3.

    Args:
        X: Feature matrix of shape ``(n_samples, n_features)``.
        y: Label vector — string or integer labels mapped to {0, 1, 2}.
        n_trials: Maximum number of hyperparameter trials (default 60).
        search_space: Function defining the search space. If ``None``,
            uses :func:`default_swing_search_space`.
        study: Existing Optuna study. If ``None``, creates one with
            MedianPruner via :func:`create_study`.
        study_name: Optional study name (used when creating new study).
        feature_names: Optional feature names for the DMatrix.
        val_fraction: Fraction of data to hold out for validation.
        random_state: Random seed for reproducibility.
        early_stopping_rounds: XGBoost ``early_stopping_rounds`` per trial.
        direction: ``"minimize"`` (logloss) or ``"maximize"`` (accuracy).

    Returns:
        Completed Optuna study with ``study.best_params``,
        ``study.best_value``, and ``study.trials_dataframe()`` available.

    Raises:
        ValueError: If inputs are invalid.
        RuntimeError: If no trials complete successfully.
    """
    # --- Validate inputs ---
    if not isinstance(X, np.ndarray) or not isinstance(y, np.ndarray):
        raise TypeError("X and y must be numpy arrays")
    if X.ndim != 2:
        raise ValueError(f"X must be 2D, got {X.ndim}D")
    if y.ndim != 1:
        raise ValueError(f"y must be 1D, got {y.ndim}D")
    if len(X) != len(y):
        raise ValueError(
            f"X and y must have same length, got {len(X)} and {len(y)}"
        )
    if len(X) < 10:
        raise ValueError(
            f"Need at least 10 samples for tuning, got {len(X)}"
        )

    y_int = _encode_labels(y)

    # --- Fixed train/val split ---
    n_samples = len(y_int)
    n_val = max(1, int(n_samples * val_fraction))
    indices = np.arange(n_samples)
    rng = np.random.RandomState(random_state)
    rng.shuffle(indices)

    val_idx = indices[:n_val]
    train_idx = indices[n_val:]

    X_train = X[train_idx]
    y_train = y_int[train_idx]
    X_val = X[val_idx]
    y_val = y_int[val_idx]

    # --- Create study if needed ---
    if study is None:
        study = create_study(
            study_name=study_name,
            direction=direction,
            seed=random_state,
        )

    if search_space is None:
        search_space = default_swing_search_space

    # --- Objective function ---
    def objective(trial: optuna.Trial) -> float:
        params = search_space(trial)

        xgb_params = {
            "objective": "multi:softprob",
            "num_class": NUM_CLASSES,
            "verbosity": 0,
            "random_state": random_state,
            **params,
        }

        dtrain = xgb.DMatrix(X_train, label=y_train)
        dval = xgb.DMatrix(X_val, label=y_val)
        if feature_names:
            dtrain.feature_names = feature_names
            dval.feature_names = feature_names

        pruning_cb = XGBoostPruningCallback(
            trial=trial,
            observation_key=PRUNING_OBSERVATION_KEY,
        )

        evals_result: Dict[str, Any] = {}

        booster = xgb.train(
            params=xgb_params,
            dtrain=dtrain,
            num_boost_round=params.get("n_estimators", 200),
            evals=[(dtrain, "train"), (dval, "val")],
            evals_result=evals_result,
            early_stopping_rounds=early_stopping_rounds,
            callbacks=[pruning_cb],
            verbose_eval=False,
        )

        # Raise TrialPruned so Optuna marks this trial as PRUNED instead of
        # COMPLETE. This is required because the callback stops xgboost early
        # but does not itself raise the exception (xgboost handles the return
        # value cleanly).
        if pruning_cb.pruned:
            raise optuna.TrialPruned()

        # Return best validation score
        val_mlogloss = evals_result.get("val", {}).get("mlogloss", [])
        if val_mlogloss:
            return float(min(val_mlogloss))
        # Fallback: compute from booster
        y_pred_prob = booster.predict(dval)
        return float(np.mean((y_pred_prob.argmax(axis=1) != y_val).astype(float)))

    # --- Run optimization ---
    logger.info(
        "Starting tuning: %d trials, early_stopping_rounds=%d, val_fraction=%.2f",
        n_trials,
        early_stopping_rounds,
        val_fraction,
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    n_completed = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
    n_pruned = len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])
    logger.info(
        "Tuning complete: %d trials (%d complete, %d pruned). Best value: %.4f",
        len(study.trials),
        n_completed,
        n_pruned,
        study.best_value,
    )

    return study


def get_best_params(
    study: optuna.Study,
    with_fixed: bool = True,
) -> Dict[str, Any]:
    """Extract best hyperparameters from a completed study.

    Args:
        study: Completed Optuna study.
        with_fixed: If True, includes fixed params like ``objective``,
            ``num_class``, ``random_state``, and ``verbosity``.

    Returns:
        Dict of best hyperparameters ready to pass to XGBoostTrainer
        or directly to ``xgb.train()``.
    """
    params = study.best_params.copy()

    if with_fixed:
        params["objective"] = "multi:softprob"
        params["num_class"] = NUM_CLASSES
        params["random_state"] = RANDOM_SEED
        params["verbosity"] = 0

    return params
