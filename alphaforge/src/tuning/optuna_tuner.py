"""Optuna Tuning Engine — TPE sampler, ASHA pruning, study lifecycle.

Integrates Optuna as the core hyperparameter optimization engine for
AlphaForge mode-specific models.

Key features:
- TPE sampler (Tree-structured Parzen Estimator) for efficient search
- ASHA (SuccessiveHalvingAlgorithm) pruning via SuccessiveHalvingPruner
- SQLite persistence for study durability and resume capability
- Mode-specific search spaces for SWING, SCALP, AGGRESSIVE_SCALP
- Study lifecycle management (create, load, list, delete)

References:
    - Optuna: A Next-generation Hyperparameter Optimization Framework
      (arXiv: 1907.10902) — define-by-run API, TPE sampler, pruning
    - Walk-Forward Validation with Optuna Timing (arXiv: 2601.08896)
      — WFV integration patterns for time-series hyperparameter optimization
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import optuna
from optuna.pruners import SuccessiveHalvingPruner
from optuna.samplers import TPESampler
from optuna.storages import RDBStorage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default studies directory relative to project root
STUDIES_DIR: str = "data/studies"

# Default number of trials for optimization
DEFAULT_N_TRIALS: int = 50

# Default timeout for optimization in seconds (1 hour)
DEFAULT_TIMEOUT_SECONDS: int = 3600

# TPE sampler defaults
TPE_N_STARTUP_TRIALS: int = 10
TPE_SEED: int = 42

# ASHA pruner defaults
ASHA_MIN_RESOURCE: int = 1
ASHA_REDUCTION_FACTOR: int = 3
ASHA_MIN_EARLY_STOPPING_RATE: int = 0

# Supported trading modes
VALID_MODES: Tuple[str, ...] = ("SWING", "SCALP", "AGGRESSIVE_SCALP")

# ---------------------------------------------------------------------------
# Search space definitions
# ---------------------------------------------------------------------------

# Each search space defines hyperparameter distributions for Optuna trials.
# The keys match the XGBoost hyperparameter names used in xgb_trainer.py.
# Values are callables that take `trial: optuna.Trial` and return a float/int.


def _swing_search_space(trial: optuna.Trial) -> Dict[str, Any]:
    """SWING mode hyperparameter search space.

    Conservative ranges around the LOCKED_INITIAL_BASELINE defaults
    to avoid excessive exploration of unstable regions.
    """
    return {
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
        "n_estimators": trial.suggest_int("n_estimators", 100, 500),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 3, 10),
        "gamma": trial.suggest_float("gamma", 0.0, 0.5),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 1.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 5.0, log=True),
    }


def _scalp_search_space(trial: optuna.Trial) -> Dict[str, Any]:
    """SCALP mode hyperparameter search space.

    SCALP models need faster adaptation and lower latency, so we use
    higher learning rates and shallower trees with stronger regularization.
    """
    return {
        "max_depth": trial.suggest_int("max_depth", 2, 6),
        "learning_rate": trial.suggest_float("learning_rate", 0.05, 0.3, log=True),
        "n_estimators": trial.suggest_int("n_estimators", 50, 300),
        "subsample": trial.suggest_float("subsample", 0.5, 0.9),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 0.9),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 6),
        "gamma": trial.suggest_float("gamma", 0.0, 0.3),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 2.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 5.0, log=True),
    }


def _aggressive_scalp_search_space(trial: optuna.Trial) -> Dict[str, Any]:
    """AGGRESSIVE_SCALP mode hyperparameter search space.

    AGGRESSIVE_SCALP pushes further into fast-adaptation territory with
    even shallower trees and stronger regularization.
    """
    return {
        "max_depth": trial.suggest_int("max_depth", 2, 5),
        "learning_rate": trial.suggest_float("learning_rate", 0.05, 0.4, log=True),
        "n_estimators": trial.suggest_int("n_estimators", 30, 200),
        "subsample": trial.suggest_float("subsample", 0.4, 0.8),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 0.8),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 5),
        "gamma": trial.suggest_float("gamma", 0.0, 0.5),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 5.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 10.0, log=True),
    }


# Registry of search spaces per mode
_SEARCH_SPACE_REGISTRY: Dict[str, Callable[[optuna.Trial], Dict[str, Any]]] = {
    "SWING": _swing_search_space,
    "SCALP": _scalp_search_space,
    "AGGRESSIVE_SCALP": _aggressive_scalp_search_space,
}


def search_spaces(mode: str) -> Dict[str, Any]:
    """Return a description of the search space for a given mode.

    Args:
        mode: Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).

    Returns:
        Dict mapping parameter names to (type, range) descriptions.
    """
    if mode not in _SEARCH_SPACE_REGISTRY:
        raise ValueError(f"Unknown mode '{mode}'. Must be one of {VALID_MODES}")

    # Return a human-readable description by probing the search space
    # with a minimal trial stub (using TPESampler internals would be complex,
    # so we manually define the ranges here).
    descriptions: Dict[str, Dict[str, Any]] = {
        "SWING": {
            "max_depth": {"type": "int", "low": 3, "high": 8},
            "learning_rate": {"type": "float", "low": 0.01, "high": 0.15, "log": True},
            "n_estimators": {"type": "int", "low": 100, "high": 500},
            "subsample": {"type": "float", "low": 0.6, "high": 1.0},
            "colsample_bytree": {"type": "float", "low": 0.6, "high": 1.0},
            "min_child_weight": {"type": "int", "low": 3, "high": 10},
            "gamma": {"type": "float", "low": 0.0, "high": 0.5},
            "reg_alpha": {"type": "float", "low": 1e-8, "high": 1.0, "log": True},
            "reg_lambda": {"type": "float", "low": 0.1, "high": 5.0, "log": True},
        },
        "SCALP": {
            "max_depth": {"type": "int", "low": 2, "high": 6},
            "learning_rate": {"type": "float", "low": 0.05, "high": 0.3, "log": True},
            "n_estimators": {"type": "int", "low": 50, "high": 300},
            "subsample": {"type": "float", "low": 0.5, "high": 0.9},
            "colsample_bytree": {"type": "float", "low": 0.5, "high": 0.9},
            "min_child_weight": {"type": "int", "low": 1, "high": 6},
            "gamma": {"type": "float", "low": 0.0, "high": 0.3},
            "reg_alpha": {"type": "float", "low": 1e-8, "high": 2.0, "log": True},
            "reg_lambda": {"type": "float", "low": 0.1, "high": 5.0, "log": True},
        },
        "AGGRESSIVE_SCALP": {
            "max_depth": {"type": "int", "low": 2, "high": 5},
            "learning_rate": {"type": "float", "low": 0.05, "high": 0.4, "log": True},
            "n_estimators": {"type": "int", "low": 30, "high": 200},
            "subsample": {"type": "float", "low": 0.4, "high": 0.8},
            "colsample_bytree": {"type": "float", "low": 0.4, "high": 0.8},
            "min_child_weight": {"type": "int", "low": 1, "high": 5},
            "gamma": {"type": "float", "low": 0.0, "high": 0.5},
            "reg_alpha": {"type": "float", "low": 1e-8, "high": 5.0, "log": True},
            "reg_lambda": {"type": "float", "low": 0.1, "high": 10.0, "log": True},
        },
    }
    return descriptions.get(mode, {})


# ---------------------------------------------------------------------------
# Study storage helpers
# ---------------------------------------------------------------------------


def _resolve_studies_dir() -> Path:
    """Resolve the studies directory path.

    Checks V7_STUDIES_DIR env var first, then falls back to STUDIES_DIR
    relative to the project root (detected by looking for alphaforge/).
    """
    env_dir = os.environ.get("V7_STUDIES_DIR")
    if env_dir:
        return Path(env_dir)

    # Walk up from the current file location to find a project root marker
    # (alphaforge/ directory). This makes the path robust to import location.
    here = Path(__file__).resolve().parent
    for parent in [here] + list(here.parents):
        if (parent / "alphaforge").is_dir() or (parent / "v7").is_dir():
            return parent / STUDIES_DIR

    # Fallback to cwd-relative
    return Path.cwd() / STUDIES_DIR


def _storage_url(study_name: str) -> str:
    """Build a SQLite storage URL for a given study name."""
    studies_dir = _resolve_studies_dir()
    studies_dir.mkdir(parents=True, exist_ok=True)
    db_path = studies_dir / f"{study_name}.db"
    return f"sqlite:///{db_path.resolve()}"


def list_studies() -> List[Dict[str, Any]]:
    """List all Optuna studies found in the studies directory.

    Returns:
        List of dicts with study_name, db_path, trial_count, and best_value.
    """
    studies_dir = _resolve_studies_dir()
    if not studies_dir.exists():
        return []

    summaries: List[Dict[str, Any]] = []
    seen_names: set = set()

    for db_file in sorted(studies_dir.glob("*.db")):
        storage_url = f"sqlite:///{db_file.resolve()}"
        try:
            storage = RDBStorage(storage_url)
            study_names = optuna.get_all_study_names(storage)
            for name in study_names:
                if name in seen_names:
                    continue
                seen_names.add(name)
                try:
                    study = optuna.load_study(study_name=name, storage=storage_url)
                    trials = study.trials
                    best_trial = study.best_trial if len(trials) > 0 else None
                    summaries.append({
                        "study_name": name,
                        "db_path": str(db_file),
                        "trial_count": len(trials),
                        "best_value": best_trial.value if best_trial else None,
                        "direction": str(study.direction),
                        "datetime_start": (
                            best_trial.datetime_start.isoformat()
                            if best_trial and best_trial.datetime_start
                            else None
                        ),
                    })
                except Exception as e:
                    logger.warning("Failed to load study '%s': %s", name, e)
                    summaries.append({
                        "study_name": name,
                        "db_path": str(db_file),
                        "trial_count": -1,
                        "best_value": None,
                        "direction": "unknown",
                        "error": str(e),
                    })
        except Exception as e:
            logger.warning("Failed to read storage %s: %s", storage_url, e)

    return summaries


def delete_study(study_name: str) -> bool:
    """Delete an Optuna study and its SQLite database file.

    Args:
        study_name: Name of the study to delete.

    Returns:
        True if the study was deleted, False if not found.
    """
    db_path = _resolve_studies_dir() / f"{study_name}.db"
    if not db_path.exists():
        logger.warning("Study DB not found: %s", db_path)
        return False

    try:
        storage_url = f"sqlite:///{db_path.resolve()}"
        storage = RDBStorage(storage_url)
        optuna.delete_study(study_name=study_name, storage=storage_url)
        # Remove the db file after Optuna cleanup
        db_path.unlink(missing_ok=True)
        logger.info("Deleted study '%s' at %s", study_name, db_path)
        return True
    except Exception as e:
        logger.error("Failed to delete study '%s': %s", study_name, e)
        return False


# ---------------------------------------------------------------------------
# OptunaTuner
# ---------------------------------------------------------------------------


@dataclass
class TuningResult:
    """Result of a tuning optimization run.

    Attributes:
        study_name: Name of the Optuna study.
        best_params: Best hyperparameters found.
        best_value: Best objective value achieved.
        n_trials: Number of completed trials.
        n_pruned: Number of pruned trials.
        duration_seconds: Total wall-clock time for optimization.
        trial_details: List of per-trial details.
    """

    study_name: str
    best_params: Dict[str, Any]
    best_value: Optional[float]
    n_trials: int
    n_pruned: int
    duration_seconds: float
    trial_details: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StudySummary:
    """Summary of an Optuna study's current state.

    Attributes:
        study_name: Name of the study.
        direction: Optimization direction (minimize/maximize).
        n_trials: Number of completed trials.
        n_pruned: Number of pruned trials.
        best_params: Best hyperparameters found so far.
        best_value: Best objective value achieved.
        best_trial_number: Trial number of the best trial.
        storage_type: Type of storage (in-memory or sqlite).
    """

    study_name: str
    direction: str
    n_trials: int
    n_pruned: int
    best_params: Dict[str, Any]
    best_value: Optional[float]
    best_trial_number: Optional[int]
    storage_type: str


class OptunaTuner:
    """Optuna hyperparameter optimizer for AlphaForge mode-specific models.

    Configures TPE sampler + ASHA (SuccessiveHalving) pruning + SQLite
    persistence. Manages study lifecycle: create, load, optimize, summarize.

    Usage:
        # Create a tuner for SWING mode
        tuner = OptunaTuner(
            study_name="swing_tuning_v1",
            mode="SWING",
            direction="maximize",
            storage="sqlite:///data/studies/swing_tuning_v1.db",
        )

        # Define an objective function
        def objective(trial):
            params = tuner.suggest_params(trial)
            # train model with params
            return val_accuracy

        # Run optimization
        result = tuner.optimize(objective, n_trials=50)

        # Get results
        print(tuner.best_params)
        print(tuner.study_summary)

        # Save results to JSON
        tuner.save_results("tuning_results.json")
    """

    def __init__(
        self,
        study_name: str = "alphaforge_tuning",
        mode: str = "SWING",
        direction: str = "maximize",
        storage: Optional[str] = None,
        load_if_exists: bool = True,
        n_startup_trials: int = TPE_N_STARTUP_TRIALS,
        seed: int = TPE_SEED,
        pruner: Optional[optuna.pruners.BasePruner] = None,
        sampler: Optional[optuna.samplers.BaseSampler] = None,
    ):
        """Initialize the OptunaTuner.

        Args:
            study_name: Name for the Optuna study.
            mode: Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).
            direction: Optimization direction ('minimize' or 'maximize').
            storage: Storage URL (e.g. 'sqlite:///path/to/study.db').
                If None, auto-generates a SQLite URL based on study_name.
            load_if_exists: If True and the study already exists, load it
                instead of raising DuplicatedStudyError.
            n_startup_trials: Number of random trials before TPE kicks in.
            seed: Random seed for reproducibility.
            pruner: Optional pruner instance. Defaults to SuccessiveHalvingPruner.
            sampler: Optional sampler instance. Defaults to TPESampler.
        """
        if mode not in VALID_MODES:
            raise ValueError(
                f"Unsupported mode: '{mode}'. Must be one of {VALID_MODES}"
            )

        self._study_name = study_name
        self._mode = mode
        self._direction = direction
        self._seed = seed

        # Resolve storage
        self._storage = storage or _storage_url(study_name)

        # Create or load the study
        self._sampler = sampler or TPESampler(
            n_startup_trials=n_startup_trials,
            seed=seed,
            multivariate=False,
            group=False,
        )

        self._pruner = pruner or SuccessiveHalvingPruner(
            min_resource=ASHA_MIN_RESOURCE,
            reduction_factor=ASHA_REDUCTION_FACTOR,
            min_early_stopping_rate=ASHA_MIN_EARLY_STOPPING_RATE,
        )

        self._study = self._create_or_load_study(load_if_exists)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def study_name(self) -> str:
        return self._study_name

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def study(self) -> optuna.Study:
        return self._study

    @property
    def best_params(self) -> Dict[str, Any]:
        """Return the best hyperparameters found so far."""
        if len(self._study.trials) == 0:
            return {}
        try:
            return self._study.best_params
        except ValueError:
            return {}

    @property
    def best_value(self) -> Optional[float]:
        """Return the best objective value found so far."""
        if len(self._study.trials) == 0:
            return None
        try:
            return self._study.best_value
        except ValueError:
            return None

    @property
    def best_trial(self) -> Optional[optuna.FrozenTrial]:
        """Return the best trial found so far."""
        try:
            return self._study.best_trial
        except ValueError:
            return None

    @property
    def study_summary(self) -> StudySummary:
        """Return a summary of the current study state."""
        trials = self._study.trials
        n_pruned = sum(1 for t in trials if t.state == optuna.trial.TrialState.PRUNED)
        best_t = self.best_trial

        storage_type = "sqlite" if "sqlite" in str(self._storage) else "in_memory"

        return StudySummary(
            study_name=self._study_name,
            direction=str(self._study.direction),
            n_trials=len(trials),
            n_pruned=n_pruned,
            best_params=self.best_params,
            best_value=self.best_value,
            best_trial_number=best_t.number if best_t else None,
            storage_type=storage_type,
        )

    @property
    def trials_dataframe(self) -> "Any":
        """Return the trials as a pandas DataFrame (requires pandas)."""
        return self._study.trials_dataframe()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suggest_params(self, trial: optuna.Trial) -> Dict[str, Any]:
        """Suggest hyperparameters for a trial based on the current mode.

        Uses the mode-specific search space to suggest hyperparameters.

        Args:
            trial: An Optuna Trial object.

        Returns:
            Dict of suggested hyperparameters.
        """
        space_fn = _SEARCH_SPACE_REGISTRY.get(self._mode)
        if space_fn is None:
            raise ValueError(f"No search space defined for mode '{self._mode}'")
        return space_fn(trial)

    def optimize(
        self,
        objective: Callable[[optuna.Trial], float],
        n_trials: int = DEFAULT_N_TRIALS,
        timeout: Optional[int] = None,
        n_jobs: int = 1,
        show_progress_bar: bool = False,
    ) -> TuningResult:
        """Run hyperparameter optimization.

        Args:
            objective: Callable that takes a Trial and returns a float score.
            n_trials: Maximum number of trials to run.
            timeout: Maximum optimization time in seconds.
            n_jobs: Number of parallel jobs (1 = sequential).
            show_progress_bar: Whether to show a progress bar.

        Returns:
            TuningResult with best params, value, and trial details.
        """
        if timeout is None:
            timeout = DEFAULT_TIMEOUT_SECONDS

        start_time = time.monotonic()

        self._study.optimize(
            objective,
            n_trials=n_trials,
            timeout=timeout,
            n_jobs=n_jobs,
            show_progress_bar=show_progress_bar,
        )

        duration = time.monotonic() - start_time

        # Gather trial details
        trial_details: List[Dict[str, Any]] = []
        for t in self._study.trials:
            detail: Dict[str, Any] = {
                "number": t.number,
                "state": str(t.state),
                "value": t.value,
                "params": t.params,
                "datetime_start": (
                    t.datetime_start.isoformat() if t.datetime_start else None
                ),
                "datetime_complete": (
                    t.datetime_complete.isoformat() if t.datetime_complete else None
                ),
                "duration_seconds": (
                    (t.datetime_complete - t.datetime_start).total_seconds()
                    if t.datetime_start and t.datetime_complete
                    else None
                ),
            }
            trial_details.append(detail)

        n_pruned = sum(
            1 for t in self._study.trials
            if t.state == optuna.trial.TrialState.PRUNED
        )

        return TuningResult(
            study_name=self._study_name,
            best_params=self.best_params,
            best_value=self.best_value,
            n_trials=len(self._study.trials),
            n_pruned=n_pruned,
            duration_seconds=duration,
            trial_details=trial_details,
        )

    def save_results(self, path: str) -> str:
        """Save tuning results to a JSON file.

        Args:
            path: Output file path.

        Returns:
            The absolute path to the saved file.
        """
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)

        data: Dict[str, Any] = {
            "study_name": self._study_name,
            "mode": self._mode,
            "direction": self._direction,
            "best_params": self.best_params,
            "best_value": self.best_value,
            "n_trials": len(self._study.trials),
            "n_pruned": sum(
                1 for t in self._study.trials
                if t.state == optuna.trial.TrialState.PRUNED
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Add best trial details if available
        best_t = self.best_trial
        if best_t:
            data["best_trial"] = {
                "number": best_t.number,
                "value": best_t.value,
                "params": best_t.params,
                "datetime_start": (
                    best_t.datetime_start.isoformat()
                    if best_t.datetime_start
                    else None
                ),
                "datetime_complete": (
                    best_t.datetime_complete.isoformat()
                    if best_t.datetime_complete
                    else None
                ),
            }

        # Add storage info
        data["storage"] = str(self._storage)

        output.write_text(json.dumps(data, indent=2, default=str))
        logger.info("Tuning results saved to %s", output.resolve())
        return str(output.resolve())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_or_load_study(
        self, load_if_exists: bool = True
    ) -> optuna.Study:
        """Create or load an Optuna study.

        Args:
            load_if_exists: If True, load existing study instead of raising error.

        Returns:
            An Optuna Study object.
        """
        # Ensure the storage directory exists for SQLite
        if "sqlite" in str(self._storage):
            # Extract path from sqlite:///path
            parts = str(self._storage).replace("sqlite:///", "")
            db_path = Path(parts)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        return optuna.create_study(
            study_name=self._study_name,
            storage=self._storage,
            sampler=self._sampler,
            pruner=self._pruner,
            direction=self._direction,
            load_if_exists=load_if_exists,
        )
