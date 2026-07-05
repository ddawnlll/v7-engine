"""Mode-specific hyperparameter search spaces for Optuna tuning.

Each canonical mode (SWING, SCALP, AGGRESSIVE_SCALP) has a distinct
parameter profile reflecting its trading horizon, risk posture, and
model complexity requirements.

Maps to simulation/docs/profiles.md authority and training/xgb_trainer.py
LOCKED_INITIAL_BASELINE hyperparameters.

Usage:
    from alphaforge.tuning.mode_profiles import get_tuning_profile, suggest_params

    profile = get_tuning_profile("SCALP")
    params = suggest_params(trial, profile)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import optuna

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TuningParamRange:
    """Float or integer range for Optuna suggest_float / suggest_int.

    Attributes:
        low: Lower bound (inclusive).
        high: Upper bound (inclusive for int, exclusive-configured for float via log).
        log: If True, sample on a log scale (float only).
    """
    low: float
    high: float
    log: bool = False


@dataclass(frozen=True)
class TuningCategoricalParam:
    """Categorical choices for Optuna suggest_categorical."""
    choices: List[Any]


@dataclass(frozen=True)
class ModeTuningProfile:
    """Immutable profile defining the Optuna search space for one mode.

    All parameter ranges are LOCKED per mode after initial empirical
    calibration. Changes require authority lock re-audit.
    """
    mode: str
    learning_rate: TuningParamRange
    max_depth: tuple[int, int]  # (low, high) integer range
    reg_alpha: TuningParamRange
    reg_lambda: TuningParamRange
    min_child_weight: TuningParamRange
    subsample: TuningParamRange
    colsample_bytree: TuningParamRange
    gamma: TuningParamRange
    n_estimators: TuningParamRange | tuple[int, int]

    def suggest_params(self, trial: optuna.trial.Trial) -> Dict[str, Any]:
        """Sample hyperparameters from this profile using an Optuna trial.

        Args:
            trial: An Optuna Trial object used for parameter suggestion.

        Returns:
            Dict of XGBoost-compatible hyperparameters.
        """
        params: Dict[str, Any] = {
            "learning_rate": trial.suggest_float(
                "learning_rate",
                self.learning_rate.low,
                self.learning_rate.high,
                log=self.learning_rate.log,
            ),
            "reg_alpha": trial.suggest_float(
                "reg_alpha",
                self.reg_alpha.low,
                self.reg_alpha.high,
                log=self.reg_alpha.log,
            ),
            "reg_lambda": trial.suggest_float(
                "reg_lambda",
                self.reg_lambda.low,
                self.reg_lambda.high,
                log=self.reg_lambda.log,
            ),
            "min_child_weight": trial.suggest_float(
                "min_child_weight",
                self.min_child_weight.low,
                self.min_child_weight.high,
                log=self.min_child_weight.log,
            ),
            "subsample": trial.suggest_float(
                "subsample",
                self.subsample.low,
                self.subsample.high,
            ),
            "colsample_bytree": trial.suggest_float(
                "colsample_bytree",
                self.colsample_bytree.low,
                self.colsample_bytree.high,
            ),
            "gamma": trial.suggest_float(
                "gamma",
                self.gamma.low,
                self.gamma.high,
            ),
        }

        # Max depth as integer
        low, high = self.max_depth
        params["max_depth"] = trial.suggest_int("max_depth", low, high)

        # N estimators
        if isinstance(self.n_estimators, tuple):
            low, high = self.n_estimators
            params["n_estimators"] = trial.suggest_int("n_estimators", low, high)
        else:
            params["n_estimators"] = trial.suggest_int(
                "n_estimators",
                int(self.n_estimators.low),
                int(self.n_estimators.high),
            )

        return params


# ---------------------------------------------------------------------------
# Canonical profiles — LOCKED per mode
# ---------------------------------------------------------------------------

# SWING — secondary baseline, conservative
#   lr: 0.01-0.05 (slow convergence, stable)
#   depth: 6-10 (deeper trees for higher-level patterns on 4h data)
#   reg: high (alpha 0.5-5.0, lambda 1.0-10.0) → strong regularisation
SWING_TUNING = ModeTuningProfile(
    mode="SWING",
    learning_rate=TuningParamRange(0.01, 0.05, log=True),
    max_depth=(6, 10),
    reg_alpha=TuningParamRange(0.5, 5.0, log=True),
    reg_lambda=TuningParamRange(1.0, 10.0, log=True),
    min_child_weight=TuningParamRange(3.0, 10.0),
    subsample=TuningParamRange(0.7, 0.9),
    colsample_bytree=TuningParamRange(0.7, 0.9),
    gamma=TuningParamRange(0.0, 0.5),
    n_estimators=(100, 300),
)

# SCALP — primary mode, medium-frequency
#   lr: 0.05-0.2 (faster adaptation to 1h patterns)
#   depth: 3-6 (shallower trees reduce overfitting on noisier data)
#   reg: medium (alpha 0.01-0.5, lambda 0.1-5.0)
SCALP_TUNING = ModeTuningProfile(
    mode="SCALP",
    learning_rate=TuningParamRange(0.05, 0.2, log=True),
    max_depth=(3, 6),
    reg_alpha=TuningParamRange(0.01, 0.5, log=True),
    reg_lambda=TuningParamRange(0.1, 5.0, log=True),
    min_child_weight=TuningParamRange(1.0, 5.0),
    subsample=TuningParamRange(0.8, 1.0),
    colsample_bytree=TuningParamRange(0.8, 1.0),
    gamma=TuningParamRange(0.0, 0.3),
    n_estimators=(100, 500),
)

# AGGRESSIVE_SCALP — primary mode, high-frequency
#   lr: 0.1-0.3 (fast learning for 15m/5m patterns)
#   depth: 3-5 (shallow trees minimise overfitting on high-noise data)
#   reg: low (alpha 0.001-0.1, lambda 0.01-1.0) → lighter regularisation
AGGRESSIVE_SCALP_TUNING = ModeTuningProfile(
    mode="AGGRESSIVE_SCALP",
    learning_rate=TuningParamRange(0.1, 0.3, log=True),
    max_depth=(3, 5),
    reg_alpha=TuningParamRange(0.001, 0.1, log=True),
    reg_lambda=TuningParamRange(0.01, 1.0, log=True),
    min_child_weight=TuningParamRange(1.0, 3.0),
    subsample=TuningParamRange(0.9, 1.0),
    colsample_bytree=TuningParamRange(0.9, 1.0),
    gamma=TuningParamRange(0.0, 0.1),
    n_estimators=(100, 500),
)

# Frozen lookup
_TUNING_PROFILES: Dict[str, ModeTuningProfile] = {
    "SWING": SWING_TUNING,
    "SCALP": SCALP_TUNING,
    "AGGRESSIVE_SCALP": AGGRESSIVE_SCALP_TUNING,
}

# Default output directory for saved params
DEFAULT_PARAMS_DIR: str = "artifacts/params"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_tuning_profile(mode: str) -> ModeTuningProfile:
    """Return the canonical ModeTuningProfile for a trading mode.

    Args:
        mode: One of 'SWING', 'SCALP', 'AGGRESSIVE_SCALP'.

    Returns:
        Frozen ModeTuningProfile with parameter search ranges.

    Raises:
        ValueError: If mode is unknown.
    """
    if mode not in _TUNING_PROFILES:
        raise ValueError(
            f"Unknown mode '{mode}'. "
            f"Valid modes: {sorted(_TUNING_PROFILES.keys())}"
        )
    return _TUNING_PROFILES[mode]


def suggest_params(
    trial: optuna.trial.Trial,
    profile: Optional[ModeTuningProfile] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Sample hyperparameters from a mode's tuning profile.

    Provide either a profile directly, or a mode name to look up the
    canonical profile.

    Args:
        trial: Optuna Trial for parameter suggestion.
        profile: A ModeTuningProfile (mutually exclusive with mode).
        mode: Mode name to look up (mutually exclusive with profile).

    Returns:
        Dict of XGBoost-compatible hyperparameters.
    """
    if profile is None and mode is None:
        raise ValueError("Provide either 'profile' or 'mode'")
    if profile is not None and mode is not None:
        raise ValueError("Provide only one of 'profile' or 'mode', not both")

    resolved = profile if profile is not None else get_tuning_profile(mode)
    return resolved.suggest_params(trial)


def save_tuning_params(
    params: Dict[str, Any],
    mode: str,
    output_dir: str = DEFAULT_PARAMS_DIR,
    trial_number: Optional[int] = None,
) -> Path:
    """Save best tuning parameters to a JSON file.

    The output file is named ``<mode>_tuning_params.json`` (or
    ``<mode>_tuning_params_trial<N>.json`` when trial_number is provided)
    and placed under ``output_dir/``.

    Args:
        params: Dict of hyperparameters to persist.
        mode: Trading mode these params are for (used in filename).
        output_dir: Directory to write the file into (created if absent).
        trial_number: Optional trial number to disambiguate files.

    Returns:
        Path to the saved file.
    """
    dir_path = Path(output_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    mode_key = mode.lower().replace(" ", "_")
    if trial_number is not None:
        filename = f"{mode_key}_tuning_params_trial{trial_number}.json"
    else:
        filename = f"{mode_key}_tuning_params.json"

    file_path = dir_path / filename
    with open(file_path, "w") as f:
        json.dump(params, f, indent=2)

    logger.info("Saved tuning params for %s to %s", mode, file_path)
    return file_path


def load_tuning_params(
    mode: str,
    output_dir: str = DEFAULT_PARAMS_DIR,
) -> Optional[Dict[str, Any]]:
    """Load previously saved tuning parameters from disk.

    Args:
        mode: Trading mode to load params for.
        output_dir: Directory where params were saved.

    Returns:
        Dict of hyperparameters, or None if no saved params exist.
    """
    dir_path = Path(output_dir)
    mode_key = mode.lower().replace(" ", "_")
    file_path = dir_path / f"{mode_key}_tuning_params.json"

    if not file_path.exists():
        logger.warning("No tuning params found for %s at %s", mode, file_path)
        return None

    with open(file_path) as f:
        return json.load(f)


def all_tuning_profiles() -> Dict[str, ModeTuningProfile]:
    """Return all canonical mode tuning profiles.

    Returns:
        Dict mapping mode name to frozen ModeTuningProfile.
    """
    return dict(_TUNING_PROFILES)
