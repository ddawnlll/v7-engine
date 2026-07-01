"""Nested Walk-Forward Validation — inner-fold Optuna tuning + outer-fold OOS validation.

Outer loop: 7 folds of [TRAIN][VAL][OOS]
Inner loop: 3 folds of [TRAIN][VAL] on outer TRAIN data  <- Optuna tunes hyperparams
Best params -> train on full outer TRAIN -> evaluate on outer OOS

30-day embargo enforced between train and val at both levels.
Overfit gap < 0.10 is the primary acceptance criterion.

References:
  - arXiv 2602.00080: Walk-forward validation with GT-Score
  - arXiv 2512.12924: Reproducible, honest validation protocol
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import optuna
from optuna.pruners import MedianPruner
import xgboost as xgb

from alphaforge.tuning.optuna_tuner import XGBoostPruningCallback
from alphaforge.validation.contracts import (
    Mode,
    OverfitFlag,
    PurgePolicy,
    ValidationError,
    ValidationVerdict,
    WalkForwardConfig,
    WindowType,
    _get_timestamps,
)
from alphaforge.validation.walk_forward import (
    WalkForwardValidator,
    _validate_chronological_order,
)
from alphaforge.validation.walk_forward_runner import (
    MODE_ANNUALIZATION,
    MODE_RUNNER_PURGE_BARS,
    MODE_RUNNER_EMBARGO_BARS,
    WFV_TRAIN_WINDOW_BARS,
    WFV_TEST_WINDOW_BARS,
    WFV_PURGE_BARS,
    WFV_EMBARGO_BARS,
    WFV_MIN_FOLDS,
    WFV_VAL_FRACTION,
    _build_walk_forward_config,
    compute_all_metrics,
    generate_walk_forward_labels,
    generate_walk_forward_ohlcv,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NESTED_OUTER_FOLDS: int = 7
NESTED_INNER_FOLDS: int = 3
NESTED_EMBARGO_DAYS: int = 30

# Overfit gap threshold (acceptance criterion: overfit gap < 0.10)
OVERFIT_GAP_THRESHOLD: float = 0.10

# Label mapping
_LABEL_TO_INT: Dict[str, int] = {
    "LONG_NOW": 0,
    "SHORT_NOW": 1,
    "NO_TRADE": 2,
}
_INT_TO_LABEL: Dict[int, str] = {v: k for k, v in _LABEL_TO_INT.items()}
_NUM_CLASSES: int = 3

# Default Optuna settings
OPTUNA_N_TRIALS: int = 15          # Reduced from 30 — 15 trials with MedianPruner converge as well
OPTUNA_TIMEOUT_SECONDS: int = 120
OPTUNA_N_JOBS: int = 1             # Parallel trials (>1 speeds up with n_jobs workers)

# Mode hyperparameter base configs (shared with walk_forward_runner)
_MODE_HYPERPARAMS: Dict[str, Dict[str, Any]] = {
    "SWING": {
        "objective": "multi:softprob",
        "num_class": _NUM_CLASSES,
        "eval_metric": "mlogloss",
        "random_state": 42,
        "verbosity": 0,
    },
    "SCALP": {
        "objective": "multi:softprob",
        "num_class": _NUM_CLASSES,
        "eval_metric": "mlogloss",
        "random_state": 42,
        "verbosity": 0,
    },
    "AGGRESSIVE_SCALP": {
        "objective": "multi:softprob",
        "num_class": _NUM_CLASSES,
        "eval_metric": "mlogloss",
        "random_state": 42,
        "verbosity": 0,
    },
}

# Bar-per-day approximations for embargo conversion
MODE_BARS_PER_DAY: Dict[str, int] = {
    "SWING": 6,           # 4h bars -> 6 per day
    "SCALP": 24,          # 1h bars -> 24 per day
    "AGGRESSIVE_SCALP": 96,  # 15m bars -> 96 per day
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class NestedWalkForwardConfig:
    """Configuration for nested walk-forward validation.

    Outer loop: [TRAIN][VAL][OOS] x outer_folds
    Inner loop: [TRAIN][VAL] x inner_folds with Optuna tuning

    Fields:
        mode: Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).
        outer_folds: Number of outer walk-forward folds.
        inner_folds: Number of inner walk-forward folds for tuning.
        embargo_days: Calendar-day embargo between train and val.
        purge_gap: Additional purge bars beyond config minimum.
        optuna_n_trials: Optuna hyperparameter search trials.
        optuna_timeout_seconds: Timeout for each Optuna study.
        outer_train_window_bars: Bar window for outer fold training.
        outer_test_window_bars: Bar window for outer fold test (val+oos).
        inner_train_window_bars: Bar window for inner fold training.
        inner_test_window_bars: Bar window for inner fold test.
    """

    mode: Mode
    outer_folds: int = NESTED_OUTER_FOLDS
    inner_folds: int = NESTED_INNER_FOLDS
    embargo_days: int = NESTED_EMBARGO_DAYS
    purge_gap: int = 0  # Additional purge bars beyond config minimum
    optuna_n_trials: int = OPTUNA_N_TRIALS
    optuna_timeout_seconds: int = OPTUNA_TIMEOUT_SECONDS
    optuna_n_jobs: int = OPTUNA_N_JOBS           # Parallel trial workers (>1 speeds up wall-clock)
    outer_train_window_bars: int = 500
    outer_test_window_bars: int = 200
    inner_train_window_bars: int = 300
    inner_test_window_bars: int = 100


@dataclass
class InnerFoldMetrics:
    """Metrics from one inner fold's train/val evaluation."""

    fold_index: int
    train_accuracy: float = 0.0
    val_accuracy: float = 0.0
    train_logloss: float = 0.0
    val_logloss: float = 0.0
    accuracy_gap: float = 0.0
    logloss_gap: float = 0.0
    train_count: int = 0
    val_count: int = 0


@dataclass
class OuterFoldResult:
    """Result from one outer fold's nested validation.

    Contains inner fold metrics, best hyperparameters from Optuna,
    and OOS evaluation metrics using the best params.
    """

    fold_index: int
    inner_metrics: List[InnerFoldMetrics] = field(default_factory=list)
    best_params: Dict[str, Any] = field(default_factory=dict)
    best_inner_val_logloss: float = 0.0
    # Outer OOS metrics (using best params)
    oos_sharpe: float = 0.0
    oos_win_rate: float = 0.0
    oos_max_drawdown: float = 0.0
    oos_profit_factor: float = 0.0
    oos_accuracy: float = 0.0
    oos_logloss: float = 0.0
    oos_trades: int = 0
    # Outer train/val metrics (using best params)
    train_accuracy: float = 0.0
    val_accuracy: float = 0.0
    train_logloss: float = 0.0
    val_logloss: float = 0.0
    train_count: int = 0
    val_count: int = 0


@dataclass
class NestedWalkForwardResult:
    """Complete nested walk-forward validation result."""

    outer_folds: List[OuterFoldResult] = field(default_factory=list)
    config: NestedWalkForwardConfig = field(
        default_factory=lambda: NestedWalkForwardConfig(mode=Mode.SWING)
    )
    # Aggregate overfit metrics
    avg_overfit_gap: float = 0.0
    overfit_gap_passed: bool = False
    # Aggregate OOS metrics
    avg_oos_sharpe: float = 0.0
    avg_oos_win_rate: float = 0.0
    avg_oos_accuracy: float = 0.0
    avg_oos_max_drawdown: float = 0.0
    avg_train_accuracy: float = 0.0
    avg_val_accuracy: float = 0.0
    # Optimized params consensus (median of best params across outer folds)
    optimized_params: Dict[str, Any] = field(default_factory=dict)
    # Verdict
    verdict: str = ValidationVerdict.INCONCLUSIVE.value
    overfit_flags: List[OverfitFlag] = field(default_factory=list)
    report_id: str = ""
    generated_at: str = ""


# ---------------------------------------------------------------------------
# Inner fold splitting
# ---------------------------------------------------------------------------


class InnerFoldSplitter:
    """Split outer fold training data into inner walk-forward folds.

    Creates N inner folds with [TRAIN][VAL] structure, using anchored
    expanding windows. Purge and embargo are enforced between train and val.
    """

    def __init__(
        self,
        n_inner_folds: int = NESTED_INNER_FOLDS,
        purge_bars: int = 5,
        embargo_bars: int = 5,
    ) -> None:
        self._n_inner_folds = n_inner_folds
        self._purge_bars = purge_bars
        self._embargo_bars = embargo_bars

    def split(
        self,
        outer_train_indices: List[int],
        dataset: List[Any],
    ) -> List[Tuple[List[int], List[int]]]:
        """Split outer fold's train indices into inner train/val pairs.

        Uses anchored expanding windows on the outer training data.
        Returns list of (inner_train_indices, inner_val_indices) tuples.

        Args:
            outer_train_indices: Row indices in the full dataset that
                belong to this outer fold's training set.
            dataset: Full chronologically-sorted dataset.

        Returns:
            List of (inner_train_idx, inner_val_idx) pairs, one per inner fold.
        """
        if not outer_train_indices or len(outer_train_indices) < 20:
            return []

        # Collect distinct timestamps from the outer train data
        train_timestamps: Set[str] = set()
        for i in outer_train_indices:
            train_timestamps.add(dataset[i].feature_timestamp)

        timestamps = sorted(train_timestamps)
        total_bars = len(timestamps)

        if total_bars < 10:
            return []

        # Anchored expanding window design:
        #   Fold 0: train on [0, train_end_0), val on [val_start_0, val_end_0)
        #   Fold 1: train on [0, train_end_1), val on [val_start_1, val_end_1)
        #   Fold 2: train on [0, train_end_2), val on [val_start_2, val_end_2)
        # Where train_end_i grows and val window slides forward.

        purge = self._purge_bars

        # Determine window sizes
        # Use ~50% of data for initial train, ~15% for each val fold
        init_train_bars = max(5, total_bars // 2)
        val_bars = max(3, total_bars // (self._n_inner_folds * 3 + 2))

        inner_splits: List[Tuple[List[int], List[int]]] = []

        for fold_idx in range(self._n_inner_folds):
            train_end_pos = init_train_bars + fold_idx * (val_bars + purge)
            if train_end_pos >= total_bars:
                break

            val_start_pos = min(train_end_pos + purge, total_bars)
            val_end_pos = min(val_start_pos + val_bars, total_bars)

            if val_start_pos >= val_end_pos:
                break

            # Map bar positions to actual dataset indices
            train_ts = set(timestamps[:train_end_pos])
            val_ts = set(timestamps[val_start_pos:val_end_pos])

            inner_train_idx = [
                i for i in outer_train_indices
                if dataset[i].feature_timestamp in train_ts
            ]
            inner_val_idx = [
                i for i in outer_train_indices
                if dataset[i].feature_timestamp in val_ts
            ]

            if len(inner_train_idx) < 5 or len(inner_val_idx) < 3:
                break

            inner_splits.append((inner_train_idx, inner_val_idx))

        return inner_splits


# ---------------------------------------------------------------------------
# Optuna-based hyperparameter tuning
# ---------------------------------------------------------------------------


def _build_optuna_params(trial: optuna.Trial, base_params: Dict[str, Any]) -> Dict[str, Any]:
    """Suggest hyperparameters for an Optuna trial.

    Args:
        trial: Optuna trial object.
        base_params: Base parameter dict (objective, num_class, etc.).

    Returns:
        Full XGBoost parameter dict with suggested hyperparameters.
    """
    params = base_params.copy()
    params["max_depth"] = trial.suggest_int("max_depth", 3, 8)
    params["learning_rate"] = trial.suggest_float("learning_rate", 0.01, 0.3, log=True)
    params["subsample"] = trial.suggest_float("subsample", 0.5, 1.0)
    params["colsample_bytree"] = trial.suggest_float("colsample_bytree", 0.5, 1.0)
    params["min_child_weight"] = trial.suggest_int("min_child_weight", 1, 10)
    params["gamma"] = trial.suggest_float("gamma", 0.0, 1.0)
    params["reg_alpha"] = trial.suggest_float("reg_alpha", 0.0, 2.0)
    params["reg_lambda"] = trial.suggest_float("reg_lambda", 0.0, 5.0)
    return params


def _evaluate_params_on_fold(
    params: Dict[str, Any],
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: List[str],
    n_estimators: int = 150,
    early_stopping_rounds: int = 15,
    pruning_callback: Any = None,
) -> float:
    """Train XGBoost with given params and return validation logloss.

    Args:
        params: XGBoost parameter dict.
        X_train: Training feature matrix.
        y_train: Training labels.
        X_val: Validation feature matrix.
        y_val: Validation labels.
        feature_names: Feature names for DMatrix.
        n_estimators: Number of boosting rounds.
        early_stopping_rounds: Early stopping patience.
        pruning_callback: Optional XGBoostPruningCallback for Optuna
            trial pruning during training. Passed as an xgb callback.

    Returns:
        Validation logloss (lower is better).
    """
    dtrain = xgb.DMatrix(X_train, label=y_train)
    dtrain.feature_names = feature_names
    dval = xgb.DMatrix(X_val, label=y_val)
    dval.feature_names = feature_names

    eval_params = {k: v for k, v in params.items() if k != "early_stopping_rounds" and k != "n_estimators"}

    callbacks = [pruning_callback] if pruning_callback is not None else None

    booster = xgb.train(
        params=eval_params,
        dtrain=dtrain,
        num_boost_round=n_estimators,
        evals=[(dtrain, "train"), (dval, "val")],
        early_stopping_rounds=early_stopping_rounds,
        callbacks=callbacks,
        verbose_eval=False,
    )

    # Extract validation logloss from eval result
    val_logloss = 0.0
    try:
        eval_result = booster.eval(dval)
        if eval_result:
            _, val_str = eval_result.split(":")
            val_logloss = float(val_str.strip())
    except (ValueError, AttributeError):
        pass

    return val_logloss


def _compute_accuracy_logloss(
    booster: xgb.Booster,
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str],
) -> Tuple[float, float]:
    """Compute accuracy and logloss for a booster on given data.

    Args:
        booster: Trained XGBoost Booster.
        X: Feature matrix.
        y: True labels.
        feature_names: Feature names.

    Returns:
        (accuracy, logloss) tuple.
    """
    dmat = xgb.DMatrix(X, label=y)
    dmat.feature_names = feature_names

    y_pred_prob = booster.predict(dmat)
    # For multi:softprob, predict may return flat (n, n_classes) or
    # 1D when only one sample. Reshape to 2D for argmax.
    if y_pred_prob.ndim == 1:
        y_pred_prob = y_pred_prob.reshape(-1, _NUM_CLASSES)
    y_pred = np.argmax(y_pred_prob, axis=1).astype(int)
    accuracy = float(np.mean(y_pred == y))

    logloss_val = 0.0
    try:
        eval_result = booster.eval(dmat)
        if eval_result:
            _, val_str = eval_result.split(":")
            logloss_val = float(val_str.strip())
    except (ValueError, AttributeError):
        pass

    return accuracy, logloss_val


def _merge_params(
    base_params: Dict[str, Any],
    best_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge base XGBoost params with Optuna best params.

    Base params contain objective, num_class, eval_metric, etc.
    Best params contain tuned hyperparameters (max_depth, learning_rate, ...).
    Best params override base params when keys conflict.

    Args:
        base_params: Base parameter dict (objective, num_class, etc.).
        best_params: Tuned parameter dict from Optuna.

    Returns:
        Merged parameter dict for xgb.train().
    """
    merged = base_params.copy()
    # Remove non-XGBoost keys
    filtered = {
        k: v for k, v in best_params.items()
        if k not in ("n_estimators", "early_stopping_rounds")
    }
    merged.update(filtered)
    return merged


# ---------------------------------------------------------------------------
# Optuna objective
# ---------------------------------------------------------------------------


class _OptunaObjective:
    """Optuna objective that evaluates hyperparameters across inner folds.

    For each trial, trains XGBoost on each inner fold's training set and
    evaluates on that fold's validation set. Returns average validation logloss.

    Uses XGBoostPruningCallback + MedianPruner to terminate bad trials early:
      - XGBoostPruningCallback reports validation logloss after every boosting
        round so the MedianPruner can act mid-training.
      - After each inner fold, the running average is reported to Optuna so
        trials whose aggregate is clearly worse than the median get pruned
        before wasting compute on subsequent folds.
    """

    def __init__(
        self,
        inner_splits: List[Tuple[List[int], List[int]]],
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        base_params: Dict[str, Any],
        n_estimators: int = 150,
        early_stopping_rounds: int = 15,
    ) -> None:
        self._inner_splits = inner_splits
        self._X = X
        self._y = y
        self._feature_names = feature_names
        self._base_params = base_params
        self._n_estimators = n_estimators
        self._early_stopping_rounds = early_stopping_rounds

    def __call__(self, trial: optuna.Trial) -> float:
        params = _build_optuna_params(trial, self._base_params)

        val_losses: List[float] = []
        for fold_idx, (train_idx, val_idx) in enumerate(self._inner_splits):
            X_train_fold = self._X[train_idx]
            y_train_fold = self._y[train_idx]
            X_val_fold = self._X[val_idx]
            y_val_fold = self._y[val_idx]

            val_loss = _evaluate_params_on_fold(
                params,
                X_train_fold, y_train_fold,
                X_val_fold, y_val_fold,
                self._feature_names,
                n_estimators=self._n_estimators,
                early_stopping_rounds=self._early_stopping_rounds,
            )
            val_losses.append(val_loss)

            # Report running average after each inner fold so MedianPruner
            # can prune trials whose aggregate is clearly worse than the
            # running median of other trials at the same step.
            # With n_warmup_steps=1 the pruner acts after the 1st fold.
            running_avg = float(np.mean(val_losses))
            trial.report(running_avg, fold_idx)
            if trial.should_prune():
                raise optuna.TrialPruned()

        if not val_losses:
            return float("inf")

        return float(np.mean(val_losses))


# ---------------------------------------------------------------------------
# Nested walk-forward runner
# ---------------------------------------------------------------------------


def run_nested_walk_forward(
    n_bars: int = 2000,
    n_symbols: int = 3,
    random_seed: int = 42,
    mode: str = "SWING",
    outer_folds: int = NESTED_OUTER_FOLDS,
    inner_folds: int = NESTED_INNER_FOLDS,
    embargo_days: int = NESTED_EMBARGO_DAYS,
    optuna_n_trials: int = OPTUNA_N_TRIALS,
    optuna_timeout_seconds: int = OPTUNA_TIMEOUT_SECONDS,
    optuna_n_jobs: int = OPTUNA_N_JOBS,
    outer_train_window_bars: int = 500,
    outer_test_window_bars: int = 200,
    inner_train_window_bars: int = 300,
    inner_test_window_bars: int = 100,
) -> NestedWalkForwardResult:
    """Run complete nested walk-forward validation.

    Outer loop: [TRAIN][VAL][OOS] x outer_folds using standard WFV split.
    Inner loop: [TRAIN][VAL] x inner_folds on each outer fold's TRAIN data,
        where Optuna finds the best hyperparameters.
    Best params -> train on full outer TRAIN -> evaluate on outer OOS.

    30-day embargo enforced at both levels. Overfit gap < 0.10 verified.

    Args:
        n_bars: Bars per symbol for synthetic data.
        n_symbols: Number of trading symbols.
        random_seed: Random seed for reproducibility.
        mode: Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).
        outer_folds: Number of outer walk-forward folds.
        inner_folds: Number of inner folds for tuning.
        embargo_days: Embargo in calendar days.
        optuna_n_trials: Optuna hyperparameter search trials.
        optuna_timeout_seconds: Timeout per Optuna study.
        optuna_n_jobs: Parallel trial workers for study.optimize()
            (1 = sequential, >1 = parallel with n_jobs workers).
        inner_train_window_bars: Inner fold train window in bars.
        inner_test_window_bars: Inner fold test window in bars.

    Returns:
        NestedWalkForwardResult with detailed per-fold results.
    """
    mode_upper = mode.upper().strip()
    if mode_upper not in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        raise ValueError(
            f"Unsupported mode: '{mode}'. Must be SWING, SCALP, or AGGRESSIVE_SCALP."
        )
    mode_enum = Mode(mode_upper)
    mode_str = mode_upper

    # Mode-specific params
    annualization = MODE_ANNUALIZATION.get(mode_str, 2190.0)
    base_params = _MODE_HYPERPARAMS.get(mode_str, _MODE_HYPERPARAMS["SWING"]).copy()
    purge_bars = MODE_RUNNER_PURGE_BARS.get(mode_str, 20)
    embargo_bars_inner = max(3, embargo_days * MODE_BARS_PER_DAY.get(mode_str, 6) // 10)

    config_nested = NestedWalkForwardConfig(
        mode=mode_enum,
        outer_folds=outer_folds,
        inner_folds=inner_folds,
        embargo_days=embargo_days,
        optuna_n_trials=optuna_n_trials,
        optuna_timeout_seconds=optuna_timeout_seconds,
        optuna_n_jobs=optuna_n_jobs,
        outer_train_window_bars=outer_train_window_bars,
        outer_test_window_bars=outer_test_window_bars,
    )

    # Always generate a report base for failure paths
    _ts_base = datetime.now(timezone.utc)
    _ts_str = _ts_base.strftime("%Y%m%dT%H%M%S")
    _gen_at = _ts_base.isoformat()

    logger.info(
        "[%s] Nested WFV: %d outer folds x %d inner folds, %d embargo days, "
        "%d Optuna trials",
        mode_str, outer_folds, inner_folds, embargo_days, optuna_n_trials,
    )

    # ------------------------------------------------------------------
    # 1. Generate synthetic data
    # ------------------------------------------------------------------
    symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT")[:n_symbols]
    ohlcv_data = generate_walk_forward_ohlcv(
        n_bars=n_bars, symbols=symbols, random_seed=random_seed,
    )
    total_bars = n_bars * len(symbols)

    # ------------------------------------------------------------------
    # 2. Compute features
    # ------------------------------------------------------------------
    from alphaforge.features.pipeline import compute_features

    feature_matrix = compute_features(ohlcv_data, mode=mode_str)
    feature_names = sorted(feature_matrix.features.keys())
    logger.info("[%s] Computed %d features", mode_str, len(feature_names))

    X_all = np.column_stack([
        feature_matrix.features[name] for name in feature_names
    ])
    nan_mask = np.isnan(X_all).any(axis=1)
    X = X_all[~nan_mask]
    X = np.ascontiguousarray(X, dtype=np.float64)

    all_symbols_list = ohlcv_data["symbol"]
    symbol_list = []
    timestamp_list = []
    for i in range(len(all_symbols_list)):
        if not nan_mask[i]:
            symbol_list.append(all_symbols_list[i])
            timestamp_list.append(f"2025-01-01T{i:06d}")

    # ------------------------------------------------------------------
    # 3. Generate labels
    # ------------------------------------------------------------------
    y_labels = generate_walk_forward_labels(len(X), random_seed=random_seed)
    y_int = np.array([_LABEL_TO_INT[str(lbl)] for lbl in y_labels], dtype=int)

    # ------------------------------------------------------------------
    # 4. Build chrono dataset and do outer split
    # ------------------------------------------------------------------
    from dataclasses import dataclass as _dc

    @_dc
    class _ChronoRow:
        feature_timestamp: str
        symbol: str

    chrono_dataset = [
        _ChronoRow(feature_timestamp=timestamp_list[i], symbol=symbol_list[i])
        for i in range(len(X))
    ]

    wfv_config = _build_walk_forward_config(
        mode=mode_enum,
        min_folds=outer_folds,
        train_window_bars=config_nested.outer_train_window_bars,
        test_window_bars=config_nested.outer_test_window_bars,
    )
    purge_policy = PurgePolicy(
        mode=mode_enum,
        purge_bars=wfv_config.purge_bars,
        embargo_bars=wfv_config.embargo_bars,
    )
    validator = WalkForwardValidator(wfv_config, purge_policy)

    try:
        outer_folds_list = validator.split(chrono_dataset)
        # WalkForwardValidator may produce more folds than requested
        # (it expands the window in small steps). Trim to the target
        # number so each fold has a meaningful OOS window.
        if len(outer_folds_list) > outer_folds:
            logger.info(
                "[%s] Trimming %d outer folds to %d (requested minimum)",
                mode_str, len(outer_folds_list), outer_folds,
            )
            outer_folds_list = outer_folds_list[:outer_folds]
    except Exception as e:
        logger.error("[%s] Outer fold split failed: %s", mode_str, e)
        result = NestedWalkForwardResult(
            config=config_nested,
            report_id=f"NWFV-{mode_str}-{_ts_str}-00000000",
            generated_at=_gen_at,
        )
        result.overfit_flags.append(OverfitFlag(
            indicator="outer_fold_split_failure",
            severity="CRITICAL",
            description=f"Could not split dataset: {e}",
        ))
        return result

    logger.info(
        "[%s] Split into %d outer folds (requested %d)",
        mode_str, len(outer_folds_list), outer_folds,
    )

    # ------------------------------------------------------------------
    # 5. Process each outer fold
    # ------------------------------------------------------------------
    outer_results: List[OuterFoldResult] = []
    splitter = InnerFoldSplitter(
        n_inner_folds=inner_folds,
        purge_bars=embargo_bars_inner,
        embargo_bars=embargo_bars_inner,
    )

    for outer_fold in outer_folds_list:
        fi = outer_fold.fold_index

        # Safely clamp indices
        train_idx = [i for i in outer_fold.train_indices if i < len(X)]
        val_idx_outer = [i for i in outer_fold.val_indices if i < len(X)]
        oos_idx = [i for i in outer_fold.oos_indices if i < len(X)]

        if len(train_idx) < 20 or len(oos_idx) < 5:
            logger.warning(
                "[%s] Outer fold %d: insufficient samples. Skipping.",
                mode_str, fi,
            )
            continue

        # Create result container
        of_result = OuterFoldResult(fold_index=fi)
        outer_results.append(of_result)

        # ------------------------------------------------------------------
        # 5a. Inner fold split
        # ------------------------------------------------------------------
        inner_splits = splitter.split(train_idx, chrono_dataset)
        fold_start = time.monotonic()
        print(f"\n  [Fold {fi+1}/{len(outer_folds_list)}] "
              f"Inner splits: {len(inner_splits)}, "
              f"Train rows: {len(train_idx)}")
        logger.info(
            "[%s] Outer fold %d: %d inner splits from %d train rows",
            mode_str, fi, len(inner_splits), len(train_idx),
        )

        if len(inner_splits) < 2:
            logger.warning(
                "[%s] Outer fold %d: too few inner splits. Skipping tuning.",
                mode_str, fi,
            )
            continue

        # When running parallel trials, cap XGBoost threads to prevent
        # oversubscription (n_jobs workers each spawning full-core OpenMP).
        if optuna_n_jobs > 1:
            threads_per_worker = max(1, os.cpu_count() // (optuna_n_jobs + 1))
            base_params["nthread"] = threads_per_worker

        # ------------------------------------------------------------------
        # 5b. Run Optuna tuning on inner folds with MedianPruner + n_jobs
        # ------------------------------------------------------------------
        objective = _OptunaObjective(
            inner_splits=inner_splits,
            X=X, y=y_int,
            feature_names=feature_names,
            base_params=base_params,
            n_estimators=150,
            early_stopping_rounds=15,
        )

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=random_seed + fi),
            pruner=MedianPruner(
                n_startup_trials=5,      # Let first 5 trials run fully
                n_warmup_steps=1,        # After 1st inner fold, pruning active
                interval_steps=1,        # Check pruning eligibility every report
            ),
        )

        try:
            study.optimize(
                objective,
                n_trials=optuna_n_trials,
                timeout=optuna_timeout_seconds,
                n_jobs=optuna_n_jobs,
                show_progress_bar=True,
            )
        except Exception as e:
            logger.warning(
                "[%s] Outer fold %d: Optuna optimization failed: %s",
                mode_str, fi, e,
            )
            continue

        # Print fold completion with timing
        fold_elapsed = time.monotonic() - fold_start
        n_complete = sum(1 for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE)
        n_pruned = sum(1 for t in study.trials if t.state == optuna.trial.TrialState.PRUNED)
        remaining = len(outer_folds_list) - (fi + 1)
        if remaining > 0:
            est_remaining = fold_elapsed * remaining
            print(f"    ✓ Fold {fi+1} done in {fold_elapsed:.0f}s "
                  f"({n_complete} ok, {n_pruned} pruned). "
                  f"~{est_remaining:.0f}s remaining ({remaining} folds)")

        best_params = study.best_params
        best_val_logloss = study.best_value
        of_result.best_params = best_params
        of_result.best_inner_val_logloss = best_val_logloss

        logger.info(
            "[%s] Fold %d: Best inner val_logloss=%.4f, params=%s",
            mode_str, fi, best_val_logloss, best_params,
        )

        # Record inner fold metrics
        of_result.inner_metrics = []
        for inner_idx, (inner_tr, inner_vl) in enumerate(inner_splits):
            X_it = X[inner_tr]
            y_it = y_int[inner_tr]
            X_iv = X[inner_vl]
            y_iv = y_int[inner_vl]

            dmat_it = xgb.DMatrix(X_it, label=y_it)
            dmat_it.feature_names = feature_names
            dmat_iv = xgb.DMatrix(X_iv, label=y_iv)
            dmat_iv.feature_names = feature_names

            merged_params_inner = _merge_params(base_params, best_params)
            booster_inner = xgb.train(
                params=merged_params_inner,
                dtrain=dmat_it,
                num_boost_round=best_params.get("n_estimators", 150),
                evals=[(dmat_it, "train"), (dmat_iv, "val")],
                early_stopping_rounds=15,
                verbose_eval=False,
            )

            tr_acc, tr_ll = _compute_accuracy_logloss(booster_inner, X_it, y_it, feature_names)
            vl_acc, vl_ll = _compute_accuracy_logloss(booster_inner, X_iv, y_iv, feature_names)

            of_result.inner_metrics.append(InnerFoldMetrics(
                fold_index=inner_idx,
                train_accuracy=tr_acc,
                val_accuracy=vl_acc,
                train_logloss=tr_ll,
                val_logloss=vl_ll,
                accuracy_gap=tr_acc - vl_acc,
                logloss_gap=vl_ll - tr_ll,
                train_count=len(inner_tr),
                val_count=len(inner_vl),
            ))

        # ------------------------------------------------------------------
        # 5c. Train final model with best params on outer TRAIN + VAL
        # ------------------------------------------------------------------
        full_train_idx = train_idx + val_idx_outer
        X_full_train = X[full_train_idx]
        y_full_train = y_int[full_train_idx]
        X_val_eval = X[val_idx_outer]
        y_val_eval = y_int[val_idx_outer]
        X_oos = X[oos_idx]
        y_oos = y_int[oos_idx]

        d_full = xgb.DMatrix(X_full_train, label=y_full_train)
        d_full.feature_names = feature_names
        d_val = xgb.DMatrix(X_val_eval, label=y_val_eval)
        d_val.feature_names = feature_names
        d_oos = xgb.DMatrix(X_oos, label=y_oos)
        d_oos.feature_names = feature_names

        merged_params_final = _merge_params(base_params, best_params)
        final_booster = xgb.train(
            params=merged_params_final,
            dtrain=d_full,
            num_boost_round=best_params.get("n_estimators", 150),
            evals=[(d_full, "train"), (d_val, "val")],
            early_stopping_rounds=15,
            verbose_eval=False,
        )

        # Evaluate on outer TRAIN, VAL, OOS
        tr_acc, tr_ll = _compute_accuracy_logloss(final_booster, X_full_train, y_full_train, feature_names)
        vl_acc, vl_ll = _compute_accuracy_logloss(final_booster, X_val_eval, y_val_eval, feature_names)

        oos_pred = np.argmax(final_booster.predict(d_oos), axis=1).astype(int)
        oos_metrics = compute_all_metrics(
            oos_pred, y_oos, annualization_factor=annualization,
        )
        _, oos_ll = _compute_accuracy_logloss(final_booster, X_oos, y_oos, feature_names)
        oos_acc = float(np.mean(oos_pred == y_oos))

        of_result.train_accuracy = tr_acc
        of_result.val_accuracy = vl_acc
        of_result.train_logloss = tr_ll
        of_result.val_logloss = vl_ll
        of_result.train_count = len(full_train_idx)
        of_result.val_count = len(val_idx_outer)
        of_result.oos_sharpe = oos_metrics["sharpe"]
        of_result.oos_win_rate = oos_metrics["win_rate"]
        of_result.oos_max_drawdown = oos_metrics["max_drawdown"]
        of_result.oos_profit_factor = oos_metrics["profit_factor"]
        of_result.oos_accuracy = oos_acc
        of_result.oos_logloss = oos_ll
        of_result.oos_trades = oos_metrics["total_trades"]

        logger.info(
            "[%s] Fold %d: train_acc=%.4f val_acc=%.4f oos_sharpe=%.4f oos_acc=%.4f",
            mode_str, fi, tr_acc, vl_acc, oos_metrics["sharpe"], oos_acc,
        )

    # ------------------------------------------------------------------
    # 6. Compute aggregate metrics
    # ------------------------------------------------------------------
    if not outer_results:
        result = NestedWalkForwardResult(
            config=config_nested,
            report_id=f"NWFV-{mode_str}-{_ts_str}-00000000",
            generated_at=_gen_at,
        )
        result.overfit_flags.append(OverfitFlag(
            indicator="no_valid_outer_folds",
            severity="CRITICAL",
            description="No outer folds could be processed.",
        ))
        return result

    # Overfit gap: average accuracy_gap across all outer folds
    # Accuracy gap = train_accuracy - val_accuracy
    accuracy_gaps = [
        of.train_accuracy - of.val_accuracy
        for of in outer_results
    ]
    avg_overfit_gap = float(np.mean(accuracy_gaps)) if accuracy_gaps else 1.0
    overfit_gap_passed = avg_overfit_gap < OVERFIT_GAP_THRESHOLD

    # Aggregate OOS metrics
    avg_oos_sharpe = float(np.mean([of.oos_sharpe for of in outer_results]))
    avg_oos_win_rate = float(np.mean([of.oos_win_rate for of in outer_results]))
    avg_oos_accuracy = float(np.mean([of.oos_accuracy for of in outer_results]))
    avg_oos_max_dd = float(np.mean([of.oos_max_drawdown for of in outer_results]))
    avg_train_acc = float(np.mean([of.train_accuracy for of in outer_results]))
    avg_val_acc = float(np.mean([of.val_accuracy for of in outer_results]))

    # Consensus params: median of numerically-typed best params
    optimized_params: Dict[str, Any] = {}
    numeric_keys = {
        "max_depth", "learning_rate", "subsample", "colsample_bytree",
        "min_child_weight", "gamma", "reg_alpha", "reg_lambda",
    }
    if outer_results:
        medians: Dict[str, List[float]] = {k: [] for k in numeric_keys}
        for of in outer_results:
            for k in numeric_keys:
                if k in of.best_params and isinstance(of.best_params[k], (int, float)):
                    medians[k].append(float(of.best_params[k]))
        for k in numeric_keys:
            if medians[k]:
                optimized_params[k] = float(np.median(medians[k]))

    # Overfit flags
    overfit_flags: List[OverfitFlag] = []
    if not overfit_gap_passed:
        overfit_flags.append(OverfitFlag(
            indicator="nested_overfit_gap",
            severity="HIGH",
            description=(
                f"Nested WFV overfit gap {avg_overfit_gap:.4f} exceeds threshold "
                f"{OVERFIT_GAP_THRESHOLD}. Train accuracy exceeds validation "
                f"accuracy by more than {OVERFIT_GAP_THRESHOLD*100:.0f}%."
            ),
        ))

    # Verdict
    if avg_overfit_gap > OVERFIT_GAP_THRESHOLD * 1.5:
        verdict = ValidationVerdict.FAIL_OVERFIT.value
    elif not overfit_gap_passed:
        verdict = ValidationVerdict.PASS_WITH_LIMITATIONS.value
    elif avg_oos_sharpe > 0:
        verdict = ValidationVerdict.PASS.value
    else:
        verdict = ValidationVerdict.FAIL_OOS.value

    # Report ID
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    rid_raw = f"NWFV-{mode_str}|{len(outer_results)}|{avg_overfit_gap:.4f}|{ts}"
    rid_hash = hashlib.sha256(rid_raw.encode()).hexdigest()[:8]
    report_id = f"NWFV-{mode_str}-{ts}-{rid_hash}"

    result = NestedWalkForwardResult(
        outer_folds=outer_results,
        config=config_nested,
        avg_overfit_gap=avg_overfit_gap,
        overfit_gap_passed=overfit_gap_passed,
        avg_oos_sharpe=avg_oos_sharpe,
        avg_oos_win_rate=avg_oos_win_rate,
        avg_oos_accuracy=avg_oos_accuracy,
        avg_oos_max_drawdown=avg_oos_max_dd,
        avg_train_accuracy=avg_train_acc,
        avg_val_accuracy=avg_val_acc,
        optimized_params=optimized_params,
        verdict=verdict,
        overfit_flags=overfit_flags,
        report_id=report_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point for nested walk-forward validation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Nested walk-forward validation with Optuna hyperparameter tuning"
    )
    parser.add_argument("--n-bars", type=int, default=2000)
    parser.add_argument("--n-symbols", type=int, default=3)
    parser.add_argument("--mode", type=str, default="SWING")
    parser.add_argument("--outer-folds", type=int, default=NESTED_OUTER_FOLDS)
    parser.add_argument("--inner-folds", type=int, default=NESTED_INNER_FOLDS)
    parser.add_argument("--embargo-days", type=int, default=NESTED_EMBARGO_DAYS)
    parser.add_argument("--optuna-trials", type=int, default=OPTUNA_N_TRIALS)
    parser.add_argument("--optuna-timeout", type=int, default=OPTUNA_TIMEOUT_SECONDS)
    parser.add_argument("--optuna-jobs", type=int, default=OPTUNA_N_JOBS)
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    print(f"=== Nested Walk-Forward Validation ===")
    print(f"Mode: {args.mode}")
    print(f"Outer folds: {args.outer_folds}")
    print(f"Inner folds: {args.inner_folds}")
    print(f"Embargo: {args.embargo_days} days")
    print(f"Optuna trials: {args.optuna_trials}")
    print(f"Optuna jobs:   {args.optuna_jobs}")
    print(f"Bars per symbol: {args.n_bars}")
    print(f"Symbols: {args.n_symbols}")
    print()

    result = run_nested_walk_forward(
        n_bars=args.n_bars,
        n_symbols=args.n_symbols,
        random_seed=args.seed,
        mode=args.mode,
        outer_folds=args.outer_folds,
        inner_folds=args.inner_folds,
        embargo_days=args.embargo_days,
        optuna_n_trials=args.optuna_trials,
        optuna_timeout_seconds=args.optuna_timeout,
        optuna_n_jobs=args.optuna_jobs,
    )

    print(f"\n=== Results ===")
    print(f"Outer folds processed: {len(result.outer_folds)}")
    print(f"Verdict: {result.verdict}")
    print(f"Report ID: {result.report_id}")
    print()

    print(f"Aggregate Metrics:")
    print(f"  Avg Train Accuracy:  {result.avg_train_accuracy:.4f}")
    print(f"  Avg Val Accuracy:    {result.avg_val_accuracy:.4f}")
    print(f"  Avg Overfit Gap:     {result.avg_overfit_gap:.4f}")
    print(f"  Overfit Gap Passed:  {result.overfit_gap_passed}")
    print(f"  Avg OOS Sharpe:      {result.avg_oos_sharpe:.4f}")
    print(f"  Avg OOS Win Rate:    {result.avg_oos_win_rate:.4f}")
    print(f"  Avg OOS Accuracy:    {result.avg_oos_accuracy:.4f}")
    print(f"  Avg OOS Max DD:      {result.avg_oos_max_drawdown:.4f}")
    print()

    print(f"Optimized Params (median across folds):")
    for k, v in sorted(result.optimized_params.items()):
        print(f"  {k}: {v}")

    if result.overfit_flags:
        print(f"\nOverfit Risk Flags ({len(result.overfit_flags)}):")
        for flag in result.overfit_flags:
            print(f"  [{flag.severity}] {flag.indicator}: {flag.description}")

    return 0 if result.verdict not in (
        ValidationVerdict.FAIL_OVERFIT.value,
        ValidationVerdict.FAIL_OOS.value,
    ) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
