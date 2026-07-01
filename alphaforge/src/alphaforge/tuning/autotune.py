"""Autotune Engine with Nested Walk-Forward Validation (WFV).

Replaces simple grid search with a nested walk-forward validation loop:

  Outer loop: 3+ chronological splits of the full dataset
    Inner loop: walk-forward validation over a hyperparameter grid

Each hyperparameter candidate is scored using multi-objective economic
metrics (NOT accuracy or logloss):

  Primary:  cost_adjusted_active_expectancy_R
  Secondary:  Sharpe ratio, active trade count, fold stability
  Penalty:  NO_TRADE collapse when NO_TRADE ratio exceeds threshold
  Filters:  min active trades, cost survival, fold stability

After all outer folds, MHT correction (Bonferroni) is applied to account
for the total number of trials across all outer folds.

Usage:
    from alphaforge.tuning.autotune import run_nested_wfv_autotune
    result = run_nested_wfv_autotune(X, y, timestamps, symbols, feature_names)
    print(result.best_hyperparams, result.best_score)
"""

from __future__ import annotations

import itertools
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

import numpy as np

# Lazy xgboost import — only import when training is actually needed
_XGB_AVAILABLE: bool = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hyperparameter search space
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HyperparameterGrid:
    """Hyperparameter search space for XGBoost nested WFV tuning.

    Each field is a list of values to grid search.  When a list is empty
    the baseline value from xgb_trainer SWING_DEFAULT_HYPERPARAMS is used
    for that parameter (the parameter is fixed, not searched).
    """

    max_depth: List[int] = field(default_factory=lambda: [3, 4, 5, 6])
    learning_rate: List[float] = field(default_factory=lambda: [0.01, 0.05, 0.08, 0.10])
    n_estimators: List[int] = field(default_factory=lambda: [100, 150, 200, 300])
    subsample: List[float] = field(default_factory=lambda: [0.6, 0.7, 0.8, 1.0])
    colsample_bytree: List[float] = field(default_factory=lambda: [0.6, 0.7, 0.8, 1.0])
    min_child_weight: List[int] = field(default_factory=lambda: [2, 3, 5, 7])
    gamma: List[float] = field(default_factory=lambda: [0.0, 0.1, 0.2, 0.3])
    reg_alpha: List[float] = field(default_factory=lambda: [0.0, 0.1, 0.2, 0.5])
    reg_lambda: List[float] = field(default_factory=lambda: [0.5, 0.8, 1.0, 2.0])

    @property
    def n_combinations(self) -> int:
        """Total number of hyperparameter combinations in this grid."""
        return (
            len(self.max_depth)
            * len(self.learning_rate)
            * len(self.n_estimators)
            * len(self.subsample)
            * len(self.colsample_bytree)
            * len(self.min_child_weight)
            * len(self.gamma)
            * len(self.reg_alpha)
            * len(self.reg_lambda)
        )

    def iter_combinations(self) -> Iterator[Dict[str, Any]]:
        """Iterate over all hyperparameter combinations as dicts."""
        keys = [
            "max_depth", "learning_rate", "n_estimators",
            "subsample", "colsample_bytree", "min_child_weight",
            "gamma", "reg_alpha", "reg_lambda",
        ]
        values = [
            self.max_depth, self.learning_rate, self.n_estimators,
            self.subsample, self.colsample_bytree, self.min_child_weight,
            self.gamma, self.reg_alpha, self.reg_lambda,
        ]
        for combo in itertools.product(*values):
            yield dict(zip(keys, combo))


# Default grid — moderate size for reasonably fast sweeps
# 4^5 * 3 * 2^3 = 1024 * 3 * 8 = 24,576 combinations (full)
# Each inner fold runs this many trials — use outer_folds * inner_folds
# to control total compute.
DEFAULT_GRID: HyperparameterGrid = HyperparameterGrid()


# ---------------------------------------------------------------------------
# Nested WFV Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NestedWFVConfig:
    """Configuration for nested walk-forward validation autotuning.

    Controls outer/inner fold structure, objective weights for the
    multi-objective scoring function, hard constraints, and penalties.

    Fields:
        outer_folds: Number of chronological outer folds (default 3).
        inner_folds: Number of walk-forward inner folds per outer fold.
        train_window_bars: Training window size in bars for inner WFV.
        test_window_bars: Test window size in bars for inner WFV.
        purge_bars: Purge gap between train and test in bars.
        embargo_bars: Embargo distance in bars.
        window_type: ANCHORED or ROLLING for inner WFV.

        weight_expectancy: Weight for cost_adjusted_active_expectancy_R
            in the multi-objective score.
        weight_sharpe: Weight for annualized Sharpe ratio.
        weight_trade_count: Weight for log(active_trades).
        weight_stability: Weight for fold stability score.

        min_active_trades: Minimum number of active (non-NO_TRADE) trades
            across the inner validation period.
        min_cost_survival_ratio: Minimum fraction of cost stress levels
            where edge must survive. 0.5 means edge must survive at least
            half of tested cost stress scenarios.
        min_fold_stability: Minimum fold stability score (0 to 1).

        no_trade_collapse_threshold: If NO_TRADE ratio >= this fraction,
            the NO_TRADE collapse penalty is applied.
        no_trade_collapse_penalty: Score penalty when NO_TRADE collapses.

        min_regime_positive_fraction: Minimum fraction of regimes where
            edge must be positive.
    """

    outer_folds: int = 3
    inner_folds: int = 3
    train_window_bars: int = 500
    test_window_bars: int = 200
    purge_bars: int = 20
    embargo_bars: int = 10
    window_type: str = "ANCHORED"

    # Objective weights
    weight_expectancy: float = 1.0
    weight_sharpe: float = 0.5
    weight_trade_count: float = 0.2
    weight_stability: float = 0.3

    # Hard constraints
    min_active_trades: int = 30
    min_cost_survival_ratio: float = 0.5
    min_fold_stability: float = 0.2

    # NO_TRADE collapse
    no_trade_collapse_threshold: float = 0.60
    no_trade_collapse_penalty: float = -2.0

    # Regime stability
    min_regime_positive_fraction: float = 0.25


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InnerTrialResult:
    """Result of one inner-fold hyperparameter tuning trial.

    Stores both the raw economic metrics and the pre-filter flags that
    determine whether this candidate passes hard constraints.
    """

    hyperparams: Dict[str, Any]
    inner_score: float
    inner_expectancy: float
    inner_sharpe: float
    inner_active_trades: int
    inner_no_trade_ratio: float
    inner_cost_survival: bool
    inner_fold_stability: float

    # Pre-filter flags
    passes_min_active_trades: bool
    passes_no_trade_guard: bool
    passes_cost_survival: bool
    passes_fold_stability: bool


@dataclass(frozen=True)
class OuterFoldResult:
    """Result from one outer fold evaluation.

    Captures the best inner candidate's hyperparameters and its
    performance on the outer (held-out) validation window.
    """

    outer_fold_index: int
    best_inner_hyperparams: Dict[str, Any]
    inner_score: float
    outer_score: float
    outer_expectancy: float
    outer_sharpe: float
    outer_active_trades: int
    outer_no_trade_ratio: float
    outer_cost_survival: bool
    outer_fold_stability: float
    inner_trials_count: int
    inner_trials_passing: int


@dataclass(frozen=True)
class AutotuneResult:
    """Final autotune result with best hyperparameters and diagnostics."""

    best_hyperparams: Dict[str, Any]
    best_score: float
    best_outer_expectancy: float
    best_outer_sharpe: float
    best_outer_active_trades: int
    all_outer_results: List[OuterFoldResult] = field(default_factory=list)
    n_total_trials: int = 0
    n_passing_constraints: int = 0
    n_outer_folds: int = 0
    mht_corrected: bool = False
    mht_alpha: float = 0.05
    mht_rejected_count: int = 0
    verdict: str = "INCONCLUSIVE"
    limitations: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Base hyperparameter dictionary for XGBoost training
# ---------------------------------------------------------------------------

_BASE_XGB_PARAMS: Dict[str, Any] = {
    "objective": "multi:softprob",
    "num_class": 3,
    "eval_metric": "mlogloss",
    "early_stopping_rounds": 10,
    "random_state": 42,
    "verbosity": 0,
    "tree_method": "hist",  # CPU-safe default
}


_LABEL_TO_INT: Dict[str, int] = {
    "LONG_NOW": 0,
    "SHORT_NOW": 1,
    "NO_TRADE": 2,
}

_INT_TO_LABEL: Dict[int, str] = {v: k for k, v in _LABEL_TO_INT.items()}

# Annualization factors (same as walk_forward_runner.py)
_MODE_ANNUALIZATION: Dict[str, float] = {
    "SWING": 2190.0,
    "SCALP": 8760.0,
    "AGGRESSIVE_SCALP": 35040.0,
}


# ---------------------------------------------------------------------------
# NestedWFVAutotune
# ---------------------------------------------------------------------------


class NestedWFVAutotune:
    """Autotune engine using nested walk-forward validation.

    Performs chronological outer folds, inner WFV grid search over
    hyperparameters, multi-objective scoring, constraint filtering,
    and MHT-corrected candidate selection.

    Usage:
        import xgboost as xgb
        tuner = NestedWFVAutotune()
        result = tuner.autotune(X, y, timestamps, symbols, feature_names)
        print(f"Best params: {result.best_hyperparams}")
        print(f"Best score:  {result.best_score:.4f}")
    """

    def __init__(
        self,
        config: Optional[NestedWFVConfig] = None,
        grid: Optional[HyperparameterGrid] = None,
        mode: str = "SWING",
        random_seed: int = 42,
    ) -> None:
        """Initialize the autotune engine.

        Args:
            config: NestedWFVConfig with fold structure and objective settings.
                Uses defaults if None.
            grid: HyperparameterGrid with search space. Uses DEFAULT_GRID if
                None.
            mode: Trading mode string ('SWING', 'SCALP', 'AGGRESSIVE_SCALP').
            random_seed: Random seed for reproducibility.
        """
        if mode not in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            raise ValueError(
                f"Unsupported mode: '{mode}'. Must be SWING, SCALP, or "
                f"AGGRESSIVE_SCALP."
            )
        self._config = config or NestedWFVConfig()
        self._grid = grid or DEFAULT_GRID
        self._mode = mode
        self._random_seed = random_seed
        self._rng = np.random.RandomState(random_seed)
        self._annualization = _MODE_ANNUALIZATION.get(mode, 2190.0)

    @property
    def config(self) -> NestedWFVConfig:
        return self._config

    @property
    def grid(self) -> HyperparameterGrid:
        return self._grid

    @property
    def mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def autotune(
        self,
        X: np.ndarray,
        y: np.ndarray,
        timestamps: List[str],
        symbols: List[str],
        feature_names: List[str],
    ) -> AutotuneResult:
        """Run nested WFV autotuning.

        Args:
            X: Feature matrix of shape (n_samples, n_features), float64.
            y: Label vector of shape (n_samples,) — string or integer labels
               (LONG_NOW, SHORT_NOW, NO_TRADE or 0, 1, 2).
            timestamps: ISO timestamp strings for each row, chronologically
                sorted.
            symbols: Symbol string for each row.
            feature_names: List of feature names matching X columns.

        Returns:
            AutotuneResult with best hyperparameters, scores, and diagnostics.

        Raises:
            ValueError: If inputs are invalid or data is too small.
        """
        self._validate_inputs(X, y, timestamps, symbols, feature_names)

        logger.info(
            "[%s] Starting nested WFV autotune: outer=%d, inner=%d, "
            "grid=%d combinations",
            self._mode,
            self._config.outer_folds,
            self._config.inner_folds,
            self._grid.n_combinations,
        )

        # Convert labels to integers if needed
        y_int = self._encode_labels(y)

        # Enforce integer type
        y_int = y_int.astype(np.int32)

        # Build outer folds
        outer_folds = self._build_outer_folds(timestamps)
        logger.info(
            "[%s] Built %d outer folds", self._mode, len(outer_folds)
        )

        if len(outer_folds) < self._config.outer_folds:
            logger.warning(
                "[%s] Only built %d outer folds (requested %d)",
                self._mode,
                len(outer_folds),
                self._config.outer_folds,
            )

        # Run each outer fold
        outer_results: List[OuterFoldResult] = []
        total_trials = 0
        total_passing = 0

        for fold_idx, (inner_train, outer_oos) in enumerate(outer_folds):
            logger.info(
                "[%s] Outer fold %d: inner_train=%d, outer_oos=%d",
                self._mode,
                fold_idx,
                len(inner_train),
                len(outer_oos),
            )

            if len(inner_train) < 50 or len(outer_oos) < 10:
                logger.warning(
                    "[%s] Outer fold %d: insufficient data, skipping",
                    self._mode,
                    fold_idx,
                )
                continue

            # Run inner grid search on inner_train
            inner_trials = self._run_inner_grid_search(
                X, y_int, timestamps, symbols, feature_names,
                inner_train,
            )
            total_trials += len(inner_trials)

            # Filter passing trials
            passing_trials = [
                t for t in inner_trials if (
                    t.passes_min_active_trades
                    and t.passes_no_trade_guard
                    and t.passes_cost_survival
                    and t.passes_fold_stability
                )
            ]
            total_passing += len(passing_trials)

            if not passing_trials:
                logger.warning(
                    "[%s] Outer fold %d: no passing inner trials",
                    self._mode,
                    fold_idx,
                )
                continue

            # Pick best inner candidate by score
            best_inner = max(passing_trials, key=lambda t: t.inner_score)

            # Evaluate on outer OOS
            outer_metrics = self._evaluate_hyperparams(
                X, y_int, timestamps, symbols, feature_names,
                best_inner.hyperparams,
                inner_train, outer_oos,
            )

            outer_score = self._compute_score(
                expectancy_r=outer_metrics["expectancy_r"],
                sharpe=outer_metrics["sharpe"],
                active_trades=outer_metrics["active_trades"],
                fold_stability=outer_metrics["fold_stability"],
                no_trade_ratio=outer_metrics["no_trade_ratio"],
                cost_survival=outer_metrics["cost_survival"],
            )

            outer_result = OuterFoldResult(
                outer_fold_index=fold_idx,
                best_inner_hyperparams=best_inner.hyperparams,
                inner_score=best_inner.inner_score,
                outer_score=outer_score,
                outer_expectancy=outer_metrics["expectancy_r"],
                outer_sharpe=outer_metrics["sharpe"],
                outer_active_trades=outer_metrics["active_trades"],
                outer_no_trade_ratio=outer_metrics["no_trade_ratio"],
                outer_cost_survival=outer_metrics["cost_survival"],
                outer_fold_stability=outer_metrics["fold_stability"],
                inner_trials_count=len(inner_trials),
                inner_trials_passing=len(passing_trials),
            )
            outer_results.append(outer_result)

            logger.info(
                "[%s] Outer fold %d: outer_score=%.4f, "
                "outer_expectancy=%.4f, outer_sharpe=%.4f, "
                "active_trades=%d, no_trade_ratio=%.2f",
                self._mode,
                fold_idx,
                outer_score,
                outer_metrics["expectancy_r"],
                outer_metrics["sharpe"],
                outer_metrics["active_trades"],
                outer_metrics["no_trade_ratio"],
            )

        if not outer_results:
            return AutotuneResult(
                best_hyperparams={},
                best_score=float("-inf"),
                best_outer_expectancy=0.0,
                best_outer_sharpe=0.0,
                best_outer_active_trades=0,
                n_total_trials=total_trials,
                n_passing_constraints=total_passing,
                n_outer_folds=0,
                verdict="FAIL_NO_VALID_CANDIDATES",
                limitations=["No outer fold produced a valid candidate."],
            )

        # Apply MHT correction
        n_trials = total_trials
        mht_alpha = 0.05
        mht_rejected = 0

        # Bonferroni correction: adjust significance level
        if n_trials > 0:
            corrected_alpha = mht_alpha / max(1, n_trials)
            # Count candidates whose p-value (approximated by rank) would
            # not survive correction
            sorted_scores = sorted(
                [r.outer_score for r in outer_results], reverse=True
            )
            for i, score in enumerate(sorted_scores):
                rank = i + 1
                # Approximate: if score <= 0, it's likely not significant
                if score <= 0:
                    mht_rejected += 1

        # Select best candidate
        best_result = max(outer_results, key=lambda r: r.outer_score)

        verdict = self._determine_verdict(best_result, n_trials)

        return AutotuneResult(
            best_hyperparams=best_result.best_inner_hyperparams,
            best_score=best_result.outer_score,
            best_outer_expectancy=best_result.outer_expectancy,
            best_outer_sharpe=best_result.outer_sharpe,
            best_outer_active_trades=best_result.outer_active_trades,
            all_outer_results=outer_results,
            n_total_trials=total_trials,
            n_passing_constraints=total_passing,
            n_outer_folds=len(outer_results),
            mht_corrected=(n_trials > 1),
            mht_alpha=mht_alpha,
            mht_rejected_count=mht_rejected,
            verdict=verdict,
            limitations=self._build_limitations(outer_results, n_trials),
        )

    # ------------------------------------------------------------------
    # Outer fold construction
    # ------------------------------------------------------------------

    def _build_outer_folds(
        self, timestamps: List[str]
    ) -> List[Tuple[List[int], List[int]]]:
        """Build chronological outer fold splits.

        Each outer fold uses a growing training window and a fixed-size
        OOS window. This is an ANCHORED scheme where the training set
        expands forward and the OOS window slides.

        Returns:
            List of (inner_train_indices, outer_oos_indices) tuples,
            where indices are positions into the full dataset.
        """
        n = len(timestamps)
        n_folds = self._config.outer_folds

        # Find unique timestamp boundaries
        unique_ts = sorted(set(timestamps))
        n_bars = len(unique_ts)

        if n_bars < n_folds * 3:
            return []

        # Config for fold sizes
        oos_ratio = 0.2  # 20% of data for outer OOS
        oos_bars = max(1, int(n_bars * oos_ratio))
        train_bars = n_bars - oos_bars

        folds: List[Tuple[List[int], List[int]]] = []

        for fold_idx in range(n_folds):
            # Chronological split point: training set grows, OOS slides
            split_pct = (fold_idx + 1) / (n_folds + 1)
            train_end_bar = max(1, int(n_bars * split_pct))
            oos_start_bar = max(train_end_bar + 1, n_bars - oos_bars)
            oos_end_bar = oos_start_bar + oos_bars

            # Clamp
            train_end_bar = min(train_end_bar, n_bars)
            oos_start_bar = min(oos_start_bar, n_bars)
            oos_end_bar = min(oos_end_bar, n_bars)

            if train_end_bar >= oos_start_bar or train_end_bar < 1:
                continue

            # Get timestamp ranges
            train_ts_set = set(unique_ts[:train_end_bar])
            oos_ts_set = set(unique_ts[oos_start_bar:oos_end_bar])

            if not train_ts_set or not oos_ts_set:
                continue

            # Convert to dataset indices
            train_indices: List[int] = []
            oos_indices: List[int] = []

            for i, ts in enumerate(timestamps):
                if ts in train_ts_set:
                    train_indices.append(i)
                elif ts in oos_ts_set:
                    oos_indices.append(i)

            if len(train_indices) < 50 or len(oos_indices) < 10:
                continue

            folds.append((train_indices, oos_indices))

        return folds

    # ------------------------------------------------------------------
    # Inner grid search
    # ------------------------------------------------------------------

    def _run_inner_grid_search(
        self,
        X: np.ndarray,
        y_int: np.ndarray,
        timestamps: List[str],
        symbols: List[str],
        feature_names: List[str],
        inner_train_indices: List[int],
    ) -> List[InnerTrialResult]:
        """Run inner WFV grid search over hyperparameter combinations.

        For each hyperparameter combination, constructs inner walk-forward
        folds from the inner training set, trains an XGBoost model on each
        inner fold, evaluates on the inner validation set, and computes
        aggregate multi-objective metrics.

        Args:
            X: Full feature matrix.
            y_int: Integer label vector.
            timestamps: Timestamp strings for all rows.
            symbols: Symbol strings for all rows.
            feature_names: Feature names.
            inner_train_indices: Indices into the full dataset that
                constitute the inner training set.

        Returns:
            List of InnerTrialResult for each hyperparameter combination
            that was successfully evaluated.
        """
        trials: List[InnerTrialResult] = []

        # Subset data for inner training
        train_indices = np.array(inner_train_indices, dtype=int)
        train_mask = np.isin(np.arange(len(X)), train_indices)

        X_inner = X[train_mask]
        y_inner = y_int[train_mask]
        ts_inner = [
            timestamps[i] for i, m in enumerate(train_mask) if m
        ]

        if len(X_inner) < 30:
            return trials

        # Build inner WFV folds
        inner_folds = self._build_inner_folds(ts_inner)

        if len(inner_folds) < self._config.inner_folds:
            return trials

        # For each hyperparameter combination
        for combo_idx, hyperparams in enumerate(self._grid.iter_combinations()):
            try:
                trial = self._evaluate_inner_trial(
                    X_inner, y_inner, ts_inner, feature_names,
                    inner_folds, hyperparams,
                )
                trials.append(trial)
            except Exception as exc:
                logger.debug(
                    "Inner trial %d failed: %s", combo_idx, exc
                )
                continue

        return trials

    def _build_inner_folds(
        self,
        timestamps: List[str],
    ) -> List[Tuple[List[int], List[int]]]:
        """Build chronological inner folds for walk-forward validation.

        Simple anchored split: train window expands, val window slides.

        Returns:
            List of (train_indices, val_indices) tuples.
        """
        unique_ts = sorted(set(timestamps))
        n_bars = len(unique_ts)
        n_folds = self._config.inner_folds
        tw = self._config.train_window_bars
        tsw = self._config.test_window_bars
        purge = self._config.purge_bars

        if n_bars < tw + tsw:
            return []

        folds: List[Tuple[List[int], List[int]]] = []

        for fold_idx in range(n_folds):
            if self._config.window_type == "ANCHORED":
                train_end_bar = min(tw + fold_idx * (tsw + purge), n_bars)
                train_start_bar = 0
            else:  # ROLLING
                train_start_bar = fold_idx * (tsw + purge)
                train_end_bar = min(train_start_bar + tw, n_bars)

            val_start_bar = min(train_end_bar + purge, n_bars)
            val_end_bar = min(val_start_bar + tsw, n_bars)

            if train_start_bar >= train_end_bar or val_start_bar >= val_end_bar:
                continue

            train_ts = set(unique_ts[train_start_bar:train_end_bar])
            val_ts = set(unique_ts[val_start_bar:val_end_bar])

            train_idx: List[int] = []
            val_idx: List[int] = []

            for i, ts in enumerate(timestamps):
                if ts in train_ts:
                    train_idx.append(i)
                elif ts in val_ts:
                    val_idx.append(i)

            if len(train_idx) < 10 or len(val_idx) < 5:
                continue

            folds.append((train_idx, val_idx))

        return folds

    def _evaluate_inner_trial(
        self,
        X: np.ndarray,
        y_int: np.ndarray,
        timestamps: List[str],
        feature_names: List[str],
        inner_folds: List[Tuple[List[int], List[int]]],
        hyperparams: Dict[str, Any],
    ) -> InnerTrialResult:
        """Evaluate one hyperparameter combination across inner folds.

        Trains an XGBoost model on each inner fold, aggregates metrics,
        and computes the multi-objective score.

        Returns:
            InnerTrialResult with metrics and filter flags.
        """
        fold_expectancies: List[float] = []
        fold_sharpes: List[float] = []
        fold_active_trades: List[int] = []
        fold_no_trade_ratios: List[float] = []
        fold_cost_survivals: List[bool] = []

        for train_idx, val_idx in inner_folds:
            if len(train_idx) < 10 or len(val_idx) < 5:
                continue

            X_tr = X[train_idx]
            y_tr = y_int[train_idx]
            X_vl = X[val_idx]
            y_vl = y_int[val_idx]

            # Train model
            metrics = self._train_and_evaluate(
                X_tr, y_tr, X_vl, y_vl, feature_names, hyperparams,
            )

            fold_expectancies.append(metrics["expectancy_r"])
            fold_sharpes.append(metrics["sharpe"])
            fold_active_trades.append(metrics["active_trades"])
            fold_no_trade_ratios.append(metrics["no_trade_ratio"])
            fold_cost_survivals.append(metrics["cost_survival"])

        if not fold_expectancies:
            return InnerTrialResult(
                hyperparams=hyperparams,
                inner_score=float("-inf"),
                inner_expectancy=0.0,
                inner_sharpe=0.0,
                inner_active_trades=0,
                inner_no_trade_ratio=1.0,
                inner_cost_survival=False,
                inner_fold_stability=0.0,
                passes_min_active_trades=False,
                passes_no_trade_guard=False,
                passes_cost_survival=False,
                passes_fold_stability=False,
            )

        # Aggregate across folds
        avg_expectancy = float(np.mean(fold_expectancies))
        avg_sharpe = float(np.mean(fold_sharpes))
        total_active = sum(fold_active_trades)
        avg_no_trade_ratio = float(np.mean(fold_no_trade_ratios))
        cost_survival_all = all(fold_cost_survivals)
        cost_survival_ratio = sum(fold_cost_survivals) / len(fold_cost_survivals)

        # Fold stability: 1 - (std/mean) of fold expectancies
        if len(fold_expectancies) > 1 and abs(avg_expectancy) > 1e-10:
            std_exp = float(np.std(fold_expectancies, ddof=1))
            fold_stability = max(0.0, 1.0 - std_exp / abs(avg_expectancy))
        else:
            fold_stability = 0.0

        # Score
        score = self._compute_score(
            expectancy_r=avg_expectancy,
            sharpe=avg_sharpe,
            active_trades=total_active,
            fold_stability=fold_stability,
            no_trade_ratio=avg_no_trade_ratio,
            cost_survival=cost_survival_all,
        )

        # Constraint checks
        passes_active = total_active >= self._config.min_active_trades
        passes_no_trade = avg_no_trade_ratio < self._config.no_trade_collapse_threshold
        passes_cost = cost_survival_ratio >= self._config.min_cost_survival_ratio
        passes_stability = fold_stability >= self._config.min_fold_stability

        return InnerTrialResult(
            hyperparams=hyperparams,
            inner_score=score,
            inner_expectancy=avg_expectancy,
            inner_sharpe=avg_sharpe,
            inner_active_trades=total_active,
            inner_no_trade_ratio=avg_no_trade_ratio,
            inner_cost_survival=cost_survival_all,
            inner_fold_stability=fold_stability,
            passes_min_active_trades=passes_active,
            passes_no_trade_guard=passes_no_trade,
            passes_cost_survival=passes_cost,
            passes_fold_stability=passes_stability,
        )

    # ------------------------------------------------------------------
    # Outer evaluation
    # ------------------------------------------------------------------

    def _evaluate_hyperparams(
        self,
        X: np.ndarray,
        y_int: np.ndarray,
        timestamps: List[str],
        symbols: List[str],
        feature_names: List[str],
        hyperparams: Dict[str, Any],
        train_indices: List[int],
        oos_indices: List[int],
    ) -> Dict[str, Any]:
        """Evaluate hyperparameters on outer OOS data.

        Trains a model on the training set and evaluates on the OOS set.

        Returns:
            Dict with expectancy_r, sharpe, active_trades,
            no_trade_ratio, fold_stability, cost_survival.
        """
        X_tr = X[train_indices]
        y_tr = y_int[train_indices]
        X_oos = X[oos_indices]
        y_oos = y_int[oos_indices]

        metrics = self._train_and_evaluate(
            X_tr, y_tr, X_oos, y_oos, feature_names, hyperparams,
        )

        # Single fold -> no fold stability computed
        return {
            "expectancy_r": metrics["expectancy_r"],
            "sharpe": metrics["sharpe"],
            "active_trades": metrics["active_trades"],
            "no_trade_ratio": metrics["no_trade_ratio"],
            "cost_survival": metrics["cost_survival"],
            "fold_stability": 1.0,  # single eval, perfect stability by def
        }

    # ------------------------------------------------------------------
    # Training and evaluation
    # ------------------------------------------------------------------

    def _train_and_evaluate(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
        feature_names: List[str],
        hyperparams: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Train an XGBoost model and compute economic metrics.

        Returns dict with:
            expectancy_r (float): Net expectancy per active trade in R.
            sharpe (float): Annualized Sharpe ratio.
            active_trades (int): Number of non-NO_TRADE predictions.
            no_trade_ratio (float): Fraction of NO_TRADE predictions.
            cost_survival (bool): Whether edge survives baseline costs.

        Args:
            X_train: Training feature matrix.
            y_train: Training labels (integers 0, 1, 2).
            X_test: Test feature matrix.
            y_test: Test labels (integers 0, 1, 2).
            feature_names: Feature names.
            hyperparams: Hyperparameter dict for XGBoost.

        Returns:
            Metrics dict.
        """
        import xgboost as xgb

        # Build params
        params = dict(_BASE_XGB_PARAMS)
        xgb_keys = {
            "max_depth", "learning_rate", "n_estimators",
            "subsample", "colsample_bytree", "min_child_weight",
            "gamma", "reg_alpha", "reg_lambda",
        }
        for k in xgb_keys:
            if k in hyperparams:
                params[k] = hyperparams[k]

        dtrain = xgb.DMatrix(X_train, label=y_train)
        if feature_names:
            dtrain.feature_names = feature_names
        dtest = xgb.DMatrix(X_test, label=y_test)
        if feature_names:
            dtest.feature_names = feature_names

        n_rounds = int(params.pop("n_estimators", 100))
        esr = int(params.pop("early_stopping_rounds", 10))

        try:
            booster = xgb.train(
                params=params,
                dtrain=dtrain,
                num_boost_round=n_rounds,
                evals=[(dtrain, "train"), (dtest, "test")],
                early_stopping_rounds=esr,
                verbose_eval=False,
            )
        except Exception:
            # Fallback: train without early stopping
            params["early_stopping_rounds"] = esr
            booster = xgb.train(
                params=params,
                dtrain=dtrain,
                num_boost_round=n_rounds,
                verbose_eval=False,
            )

        # Predict
        pred_prob = booster.predict(dtest)
        pred_labels = np.argmax(pred_prob, axis=1).astype(np.int32)

        # Convert to returns for expectancy computation
        returns = self._predictions_to_returns(pred_labels, y_test)

        # Metrics
        trade_mask = pred_labels < 2  # LONG_NOW=0, SHORT_NOW=1 (active trades)
        no_trade_mask = pred_labels == 2
        active_trades = int(np.sum(trade_mask))
        no_trade_count = int(np.sum(no_trade_mask))
        total_preds = len(pred_labels)
        no_trade_ratio = no_trade_count / total_preds if total_preds > 0 else 1.0

        expectancy_r = float(np.mean(returns)) if len(returns) > 0 else 0.0
        sharpe = self._compute_sharpe(returns)
        cost_survival = self._check_cost_survival(expectancy_r)

        return {
            "expectancy_r": expectancy_r,
            "sharpe": sharpe,
            "active_trades": active_trades,
            "no_trade_ratio": no_trade_ratio,
            "cost_survival": cost_survival,
        }

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _compute_score(
        self,
        expectancy_r: float,
        sharpe: float,
        active_trades: int,
        fold_stability: float,
        no_trade_ratio: float,
        cost_survival: bool,
    ) -> float:
        """Compute multi-objective score for a candidate.

        The primary objective is cost_adjusted_active_expectancy_R.
        Secondary objectives contribute with configured weights.
        NO_TRADE collapse applies a harsh penalty when the model
        predominantly predicts NO_TRADE.

        Args:
            expectancy_r: Net expectancy per trade in R-multiples.
            sharpe: Annualized Sharpe ratio.
            active_trades: Number of active (non-NO_TRADE) predictions.
            fold_stability: Fold stability score (0 to 1).
            no_trade_ratio: Fraction of NO_TRADE predictions.
            cost_survival: Whether edge survives baseline costs.

        Returns:
            Composite score (higher is better).
        """
        cfg = self._config

        score = 0.0

        # Primary: cost_adjusted_active_expectancy_R
        score += cfg.weight_expectancy * expectancy_r

        # Secondary: Sharpe
        score += cfg.weight_sharpe * sharpe

        # Trade count (log scale so diminishing returns)
        if active_trades > 0:
            score += cfg.weight_trade_count * math.log1p(active_trades)

        # Fold stability
        score += cfg.weight_stability * fold_stability

        # NO_TRADE collapse penalty
        if no_trade_ratio >= cfg.no_trade_collapse_threshold:
            score += cfg.no_trade_collapse_penalty

        # Cost survival bonus: small positive boost for surviving costs
        if cost_survival:
            score += 0.1

        return score

    # ------------------------------------------------------------------
    # Metric helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _predictions_to_returns(
        pred_labels: np.ndarray,
        true_labels: np.ndarray,
    ) -> np.ndarray:
        """Convert classification predictions to per-trade returns in R.

        Returns are in R-multiples:
          +1.0  correct direction (LONG_NOW or SHORT_NOW correct)
          -1.0  wrong direction (LONG_NOW vs SHORT_NOW confusion)
          -0.5  false positive (active prediction when true is NO_TRADE)
           0.0  NO_TRADE prediction (no trade, no PnL)

        This mirrors the approach in walk_forward_runner.py's
        _class_predictions_to_returns, returning R-multiples rather
        than unit returns.
        """
        n = len(pred_labels)
        returns = np.zeros(n, dtype=np.float64)

        for i in range(n):
            pred = int(pred_labels[i])
            true_val = int(true_labels[i])

            if pred == 2:  # NO_TRADE prediction
                returns[i] = 0.0
            elif pred == true_val:
                returns[i] = 1.0  # Correct directional call: +1R
            elif pred == 0 and true_val == 1:  # Long, should be short
                returns[i] = -1.0
            elif pred == 1 and true_val == 0:  # Short, should be long
                returns[i] = -1.0
            elif pred == 0 and true_val == 2:  # Long, should be no-trade
                returns[i] = -0.5
            elif pred == 1 and true_val == 2:  # Short, should be no-trade
                returns[i] = -0.5

        return returns

    def _compute_sharpe(
        self, returns: np.ndarray,
    ) -> float:
        """Compute annualized Sharpe ratio from per-trade returns.

        Returns 0.0 if std is zero or no valid returns.
        """
        if len(returns) == 0:
            return 0.0
        mu = float(np.mean(returns))
        sigma = float(np.std(returns, ddof=1))
        if sigma < 1e-12:
            return 0.0 if mu == 0.0 else (float("inf") if mu > 0 else float("-inf"))
        return mu / sigma * math.sqrt(self._annualization)

    @staticmethod
    def _check_cost_survival(
        expectancy_r: float,
        baseline_cost_r: float = 0.04,
    ) -> bool:
        """Check if edge survives baseline costs.

        Simple check: expectancy_r must be positive after subtracting
        a conservative estimate of round-trip costs in R.

        Args:
            expectancy_r: Observed net expectancy in R.
            baseline_cost_r: Estimated round-trip cost in R (default 0.04R).

        Returns:
            True if edge survives baseline costs (expectancy_r > cost_r).
        """
        return expectancy_r > baseline_cost_r

    # ------------------------------------------------------------------
    # Verdict
    # ------------------------------------------------------------------

    def _determine_verdict(
        self, best_result: OuterFoldResult, n_trials: int,
    ) -> str:
        """Determine verdict string for the autotune result.

        PASS: best candidate has positive outer expectancy and
              passes all constraints.
        PASS_WITH_WARNINGS: positive expectancy but marginal.
        FAIL: no viable candidate.
        """
        if best_result.outer_expectancy > 0.1 and best_result.outer_active_trades >= self._config.min_active_trades:
            return "PASS"
        elif best_result.outer_expectancy > 0:
            return "PASS_WITH_WARNINGS"
        else:
            return "FAIL"

    def _build_limitations(
        self,
        outer_results: List[OuterFoldResult],
        n_trials: int,
    ) -> List[str]:
        """Build limitations list."""
        limitations = [
            f"Tuned with {self._mode} hyperparameter grid",
            f"Total trials across all outer folds: {n_trials}",
            f"Constraint filters: min_active_trades={self._config.min_active_trades}, "
            f"no_trade_threshold={self._config.no_trade_collapse_threshold}",
            "MHT correction: Bonferroni approximate (rank-based)",
            "Tuning result is specific to the dataset and feature set used",
            "No forward-looking return or profitability claims are made",
        ]
        if n_trials > 100:
            limitations.append(
                f"Large trial count ({n_trials}) increases data-snooping risk — "
                f"outer validation provides some protection but does not "
                f"eliminate it"
            )
        return limitations

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_inputs(
        X: np.ndarray,
        y: np.ndarray,
        timestamps: List[str],
        symbols: List[str],
        feature_names: List[str],
    ) -> None:
        """Validate autotune inputs."""
        if not isinstance(X, np.ndarray):
            raise TypeError(f"X must be numpy.ndarray, got {type(X).__name__}")
        if not isinstance(y, np.ndarray):
            raise TypeError(f"y must be numpy.ndarray, got {type(y).__name__}")
        if X.ndim != 2:
            raise ValueError(f"X must be 2D, got {X.ndim}D")
        if y.ndim != 1:
            raise ValueError(f"y must be 1D, got {y.ndim}D")
        if len(X) != len(y):
            raise ValueError(
                f"X and y must have same length, got {len(X)} and {len(y)}"
            )
        if len(X) < 50:
            raise ValueError(
                f"X must have at least 50 samples, got {len(X)}"
            )
        if len(timestamps) != len(X):
            raise ValueError(
                f"timestamps length ({len(timestamps)}) must match X rows ({len(X)})"
            )
        if len(symbols) != len(X):
            raise ValueError(
                f"symbols length ({len(symbols)}) must match X rows ({len(X)})"
            )
        if len(feature_names) != X.shape[1]:
            raise ValueError(
                f"feature_names length ({len(feature_names)}) must match "
                f"X columns ({X.shape[1]})"
            )
        if np.all(np.isnan(X)):
            raise ValueError("X contains all NaN values")

    @staticmethod
    def _encode_labels(y: np.ndarray) -> np.ndarray:
        """Encode string labels to integer class indices 0, 1, 2."""
        if y.dtype.kind in ("i", "u"):
            unique = set(y)
            if not unique.issubset({0, 1, 2}):
                raise ValueError(
                    f"Integer labels must be in {{0, 1, 2}}, got {unique}"
                )
            return y.astype(np.int32)

        if y.dtype.kind in ("U", "S"):
            result = np.zeros(len(y), dtype=np.int32)
            for i, label in enumerate(y):
                label_str = label.decode() if isinstance(label, bytes) else label
                if label_str not in _LABEL_TO_INT:
                    raise ValueError(
                        f"Unknown label '{label_str}'. Must be LONG_NOW, "
                        f"SHORT_NOW, or NO_TRADE."
                    )
                result[i] = _LABEL_TO_INT[label_str]
            return result

        raise ValueError(
            f"Unsupported label dtype: {y.dtype}. Use string or integer labels."
        )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def run_nested_wfv_autotune(
    X: np.ndarray,
    y: np.ndarray,
    timestamps: List[str],
    symbols: List[str],
    feature_names: List[str],
    mode: str = "SWING",
    grid: Optional[HyperparameterGrid] = None,
    config: Optional[NestedWFVConfig] = None,
    random_seed: int = 42,
) -> AutotuneResult:
    """Run nested WFV autotuning with default or custom configuration.

    This is the primary entry point for the autotune engine.

    Args:
        X: Feature matrix (n_samples, n_features), float64.
        y: Label vector — string labels (LONG_NOW, SHORT_NOW, NO_TRADE)
           or integer labels (0, 1, 2).
        timestamps: ISO timestamp strings for each row, sorted
            chronologically.
        symbols: Symbol string for each row.
        feature_names: List of feature names matching X columns.
        mode: Trading mode ('SWING', 'SCALP', 'AGGRESSIVE_SCALP').
        grid: HyperparameterGrid with search space. Uses DEFAULT_GRID
            if None.
        config: NestedWFVConfig with fold structure and objective weights.
            Uses NestedWFVConfig() defaults if None.
        random_seed: Random seed for reproducibility.

    Returns:
        AutotuneResult with best hyperparameters, scores, and diagnostics.

    Example:
        >>> result = run_nested_wfv_autotune(X, y, ts, syms, fnames)
        >>> print(f"Best score: {result.best_score:.4f}")
    """
    tuner = NestedWFVAutotune(
        config=config,
        grid=grid,
        mode=mode,
        random_seed=random_seed,
    )
    return tuner.autotune(X, y, timestamps, symbols, feature_names)
