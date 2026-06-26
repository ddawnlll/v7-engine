"""Ablation Study Framework — isolate contributions of features, modes, and symbols.

Implements three types of ablation studies:
1. Feature group ablation: remove one group, retrain, measure descriptive deltas
2. Mode comparison (cross-mode transfer): train on one mode, test on another
3. Symbol ablation: train on N-1 symbols, test on held-out symbol

ABLATION IS DESCRIPTIVE ONLY — no "this feature adds X% profit" claims.
All metrics are structural or classification-quality metrics (accuracy, logloss).
Profit, Sharpe, win rate, or expectancy claims are NEVER made by this module.

Design constraints:
- Uses alphaforge.training.xgb_trainer.XGBoostTrainer for training
- Works with numpy feature matrices and label vectors (no pandas dependency)
- Feature-to-group mapping is derived from the feature pipeline naming convention
- All results include explicit limitations lists
- No ML library imports beyond what xgb_trainer already uses
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from alphaforge.training.xgb_trainer import XGBoostTrainer


# ---------------------------------------------------------------------------
# Feature-to-group mapping — authoritative map derived from feature pipeline
# ---------------------------------------------------------------------------

FEATURE_NAME_TO_GROUP: Dict[str, str] = {
    # Returns group (4 features)
    "log_return_1": "returns",
    "log_return_N": "returns",
    "return_volatility_N": "returns",
    "return_zscore_N": "returns",
    # Volatility group (4 features)
    "realized_volatility_N": "volatility",
    "high_low_range_N": "volatility",
    "garman_klass_vol_N": "volatility",
    "parkinson_vol_N": "volatility",
    # ATR group (3 features)
    "atr_N": "atr",
    "atr_pct_N": "atr",
    "atr_expansion_N": "atr",
    # Momentum group (6 features)
    "momentum_N": "momentum",
    "roc_N": "momentum",
    "rsi_N": "momentum",
    "macd": "momentum",
    "macd_signal": "momentum",
    "macd_histogram": "momentum",
    # Volume group (4 features)
    "volume_ratio_N": "volume",
    "volume_trend_N": "volume",
    "vwap_deviation": "volume",
    "obv_N": "volume",
    # Breakout group (5 features)
    "bb_position": "breakout",
    "bb_width": "breakout",
    "highest_N": "breakout",
    "lowest_N": "breakout",
    "range_breakout_N": "breakout",
}

# Reverse: group name -> list of feature names
GROUP_TO_FEATURES: Dict[str, List[str]] = {}
for _fn, _gn in FEATURE_NAME_TO_GROUP.items():
    GROUP_TO_FEATURES.setdefault(_gn, []).append(_fn)

# Canonical group order for consistent iteration
ALL_GROUPS: Tuple[str, ...] = (
    "returns", "volatility", "atr", "momentum", "volume", "breakout",
)

# CPU-safe default hyperparameters for ablation training
# (gpu_hist may fail on systems without GPU; hist always works)
ABLATION_HYPERPARAMS: Dict[str, Any] = {
    "objective": "multi:softprob",
    "num_class": 3,
    "max_depth": 4,
    "learning_rate": 0.05,
    "n_estimators": 100,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "gamma": 0.1,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "eval_metric": "mlogloss",
    "early_stopping_rounds": 10,
    "random_state": 42,
    "verbosity": 0,
    "tree_method": "hist",
}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupAblationResult:
    """Result of removing one feature group and retraining.

    All metrics are DESCRIPTIVE classification-quality measures.
    No profit, Sharpe, win-rate, or expectancy claims.
    """

    group_name: str
    feature_count_removed: int
    features_removed: List[str]

    # Baseline (full model) metrics
    baseline_accuracy: float
    baseline_logloss: float

    # Ablated model metrics
    ablated_accuracy: float
    ablated_logloss: float

    # Deltas — descriptive only
    accuracy_delta: float       # ablated - baseline (negative = degradation)
    logloss_delta: float        # ablated - baseline (positive = worse)

    training_duration_seconds: float
    limitations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class CrossModeResult:
    """Cross-mode transfer result — DESCRIPTIVE only.

    Measures how a model trained on one mode's data performs on another mode's
    data.  Degradation is reported as a descriptive observation, not a profit
    claim.
    """

    train_mode: str
    test_mode: str
    train_accuracy: float
    train_logloss: float
    test_accuracy: float
    test_logloss: float
    accuracy_degradation: float       # train - test (positive = worse on test)
    logloss_increase: float           # test - train (positive = worse)
    training_duration_seconds: float
    limitations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SymbolAblationResult:
    """Symbol ablation result — DESCRIPTIVE only.

    Measures how a model trained on N-1 symbols performs on a held-out symbol.
    No claim about symbol-specific profit is made.
    """

    held_out_symbol: str
    train_symbols: List[str]
    in_sample_accuracy: float
    in_sample_logloss: float
    held_out_accuracy: float
    held_out_logloss: float
    accuracy_delta: float              # in_sample - held_out (positive = generalization gap)
    logloss_delta: float               # held_out - in_sample (positive = worse on held-out)
    held_out_sample_count: int
    training_duration_seconds: float
    limitations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class AblationStudy:
    """Complete ablation study — DESCRIPTIVE only.

    Aggregates results from one ablation type.  The summary dict and limitations
    list enforce that no profit claims are made.
    """

    study_type: str   # "feature_group", "cross_mode", "symbol"
    baseline_metrics: Dict[str, Any]
    results: List[Any]    # List of GroupAblationResult | CrossModeResult | SymbolAblationResult
    summary: Dict[str, Any] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=lambda: [
        "Ablation is DESCRIPTIVE only — no profit, Sharpe, win-rate, or expectancy claims",
        "Metrics are classification-quality measures (accuracy, logloss), not trading P&L",
        "Results are specific to the dataset and hyperparameters used",
        "Feature importance from ablation does NOT imply causal contribution to profit",
    ])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _train_and_evaluate(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Optional[List[str]] = None,
    trainer_kwargs: Optional[Dict[str, Any]] = None,
) -> Tuple[float, float, float]:
    """Train an XGBoost model and return (accuracy, logloss, duration_seconds).

    Args:
        X: Feature matrix (n_samples, n_features).
        y: Label vector (n_samples,). String or integer labels.
        feature_names: Optional list of feature names for importance.
        trainer_kwargs: Optional kwargs for XGBoostTrainer.

    Returns:
        (accuracy, logloss, training_duration_seconds)
    """
    hp = dict(ABLATION_HYPERPARAMS)
    if trainer_kwargs:
        hp.update(trainer_kwargs)

    trainer = XGBoostTrainer(mode="SWING", hyperparameters=hp)
    start = time.monotonic()
    result = trainer.train(X, y, feature_names=feature_names)
    duration = time.monotonic() - start

    accuracy = float(result.train_metrics.get("accuracy", 0.0))
    logloss = float(result.train_metrics.get("logloss", 0.0))

    return accuracy, logloss, duration


def _validate_ablation_inputs(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Optional[List[str]],
) -> None:
    """Validate inputs for ablation studies."""
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
    if len(X) < 10:
        raise ValueError(f"Need at least 10 samples, got {len(X)}")
    if np.all(np.isnan(X)):
        raise ValueError("X contains all NaN values")

    if feature_names is not None:
        if len(feature_names) != X.shape[1]:
            raise ValueError(
                f"feature_names length ({len(feature_names)}) must match "
                f"X columns ({X.shape[1]})"
            )


def _get_group_column_indices(
    feature_names: List[str],
    group_name: str,
) -> List[int]:
    """Get column indices belonging to a feature group.

    Returns indices sorted ascending.  Empty list if group has no known features
    in the provided feature_names.
    """
    group_features = set(GROUP_TO_FEATURES.get(group_name, []))
    indices = [
        i for i, name in enumerate(feature_names)
        if name in group_features
    ]
    return sorted(indices)


# ---------------------------------------------------------------------------
# Feature Group Ablation
# ---------------------------------------------------------------------------


def run_feature_group_ablation(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Optional[List[str]] = None,
    groups_to_ablate: Optional[List[str]] = None,
    trainer_kwargs: Optional[Dict[str, Any]] = None,
) -> AblationStudy:
    """Run feature group ablation study.

    For each feature group, removes all features belonging to that group,
    retrains, and measures the descriptive delta in accuracy and logloss.

    Args:
        X: Feature matrix (n_samples, n_features).  Must be float64.
        y: Label vector (n_samples,).  String or integer labels.
        feature_names: List of feature names matching X columns.
            If None, generic names f0..fN are generated.
        groups_to_ablate: Specific groups to ablate.  If None, ablates all
            groups found in feature_names via FEATURE_NAME_TO_GROUP.
        trainer_kwargs: Optional kwargs forwarded to XGBoostTrainer.

    Returns:
        AblationStudy with study_type="feature_group".

    Raises:
        ValueError: If inputs are invalid.
    """
    _validate_ablation_inputs(X, y, feature_names)

    n_features = X.shape[1]
    if feature_names is None:
        feature_names = [f"f{i}" for i in range(n_features)]

    # Determine which groups to ablate
    if groups_to_ablate is None:
        # Discover groups present in the feature names
        present_groups: List[str] = []
        seen: set = set()
        for name in feature_names:
            group = FEATURE_NAME_TO_GROUP.get(name)
            if group and group not in seen:
                seen.add(group)
                present_groups.append(group)
        groups_to_ablate = present_groups

    if not groups_to_ablate:
        raise ValueError(
            "No groups to ablate. Provide feature_names that match known "
            "pipeline features, or specify groups_to_ablate explicitly."
        )

    # Train baseline (full model)
    baseline_accuracy, baseline_logloss, baseline_duration = _train_and_evaluate(
        X, y, feature_names=feature_names, trainer_kwargs=trainer_kwargs,
    )

    results: List[GroupAblationResult] = []

    for group_name in groups_to_ablate:
        # Get column indices for this group
        col_indices = _get_group_column_indices(feature_names, group_name)

        if not col_indices:
            # No features for this group in the dataset — skip
            continue

        # Build ablated feature matrix (remove group columns)
        keep_mask = np.ones(n_features, dtype=bool)
        keep_mask[col_indices] = False
        X_ablated = X[:, keep_mask]

        ablated_feature_names = [
            name for i, name in enumerate(feature_names)
            if keep_mask[i]
        ]

        removed_features = [
            feature_names[i] for i in col_indices
        ]

        # Train ablated model
        ablated_accuracy, ablated_logloss, ablated_duration = _train_and_evaluate(
            X_ablated, y,
            feature_names=ablated_feature_names,
            trainer_kwargs=trainer_kwargs,
        )

        result = GroupAblationResult(
            group_name=group_name,
            feature_count_removed=len(col_indices),
            features_removed=removed_features,
            baseline_accuracy=baseline_accuracy,
            baseline_logloss=baseline_logloss,
            ablated_accuracy=ablated_accuracy,
            ablated_logloss=ablated_logloss,
            accuracy_delta=ablated_accuracy - baseline_accuracy,
            logloss_delta=ablated_logloss - baseline_logloss,
            training_duration_seconds=ablated_duration,
            limitations=[
                f"Accuracy delta is descriptive — does NOT measure profit contribution of '{group_name}' group",
                "Delta magnitudes depend on dataset size, label balance, and hyperparameters",
                "Small deltas may be indistinguishable from training noise",
                "Feature group importance != causal contribution to trading profit",
            ],
        )
        results.append(result)

    # Build summary
    summary: Dict[str, Any] = {
        "baseline_accuracy": baseline_accuracy,
        "baseline_logloss": baseline_logloss,
        "baseline_training_duration_seconds": baseline_duration,
        "groups_ablated": len(results),
        "groups_attempted": len(groups_to_ablate),
        "total_features": n_features,
        "samples": len(X),
        "description": (
            "Feature group ablation measures how removing each group affects "
            "classification accuracy and logloss.  Larger negative accuracy "
            "deltas suggest the group contributes descriptive signal for label "
            "prediction — NOT trading profit."
        ),
    }

    return AblationStudy(
        study_type="feature_group",
        baseline_metrics={
            "accuracy": baseline_accuracy,
            "logloss": baseline_logloss,
        },
        results=results,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Cross-Mode Ablation
# ---------------------------------------------------------------------------


def run_cross_mode_ablation(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    train_mode: str = "SWING",
    test_mode: str = "SCALP",
    feature_names: Optional[List[str]] = None,
    trainer_kwargs: Optional[Dict[str, Any]] = None,
) -> AblationStudy:
    """Run cross-mode transfer ablation.

    Trains a model on data from one mode and evaluates it on data from another
    mode.  Measures descriptive accuracy/logloss degradation — NOT profit impact.

    Args:
        X_train: Training feature matrix.
        y_train: Training labels.
        X_test: Test feature matrix (different mode's data).
        y_test: Test labels.
        train_mode: Label for the training data mode (e.g. "SWING").
        test_mode: Label for the test data mode (e.g. "SCALP").
        feature_names: Optional list of feature names.
        trainer_kwargs: Optional kwargs forwarded to XGBoostTrainer.

    Returns:
        AblationStudy with study_type="cross_mode".

    Raises:
        ValueError: If inputs are invalid.
    """
    _validate_ablation_inputs(X_train, y_train, feature_names)

    if not isinstance(X_test, np.ndarray) or X_test.ndim != 2:
        raise TypeError(f"X_test must be 2D numpy.ndarray")
    if not isinstance(y_test, np.ndarray) or y_test.ndim != 1:
        raise TypeError(f"y_test must be 1D numpy.ndarray")
    if len(X_test) != len(y_test):
        raise ValueError(
            f"X_test and y_test must have same length, "
            f"got {len(X_test)} and {len(y_test)}"
        )
    if X_train.shape[1] != X_test.shape[1]:
        raise ValueError(
            f"X_train and X_test must have same feature count, "
            f"got {X_train.shape[1]} and {X_test.shape[1]}"
        )

    # Train on train_mode data
    hp = dict(ABLATION_HYPERPARAMS)
    if trainer_kwargs:
        hp.update(trainer_kwargs)

    trainer = XGBoostTrainer(mode="SWING", hyperparameters=hp)
    start = time.monotonic()
    result = trainer.train(X_train, y_train, feature_names=feature_names)
    duration = time.monotonic() - start

    train_accuracy = float(result.train_metrics.get("accuracy", 0.0))
    train_logloss = float(result.train_metrics.get("logloss", 0.0))

    # Evaluate on test_mode data
    import xgboost as xgb
    dtest = xgb.DMatrix(X_test, label=_encode_labels_np(y_test))
    if feature_names:
        dtest.feature_names = feature_names

    test_pred = result.model.predict(dtest)
    test_pred_labels = np.argmax(test_pred, axis=1)
    test_true = _encode_labels_np(y_test)
    test_accuracy = float(np.mean(test_pred_labels == test_true))

    # Compute logloss manually
    eps = 1e-15
    test_probs = np.clip(test_pred, eps, 1.0 - eps)
    n_test = len(test_true)
    test_logloss = 0.0
    for i in range(n_test):
        test_logloss -= np.log(test_probs[i, test_true[i]])
    test_logloss = float(test_logloss / n_test)

    cross_result = CrossModeResult(
        train_mode=train_mode,
        test_mode=test_mode,
        train_accuracy=float(train_accuracy),
        train_logloss=float(train_logloss),
        test_accuracy=float(test_accuracy),
        test_logloss=test_logloss,
        accuracy_degradation=float(train_accuracy - test_accuracy),
        logloss_increase=float(test_logloss - train_logloss),
        training_duration_seconds=duration,
        limitations=[
            f"Cross-mode transfer from {train_mode} to {test_mode} is DESCRIPTIVE only",
            "Accuracy degradation does NOT measure profit impact of mode mismatch",
            "Transfer performance depends on feature overlap between modes",
            "Different modes may have different label distributions — "
            "degradation may reflect distribution shift, not feature quality",
        ],
    )

    return AblationStudy(
        study_type="cross_mode",
        baseline_metrics={
            "train_accuracy": train_accuracy,
            "train_logloss": train_logloss,
            "test_accuracy": test_accuracy,
            "test_logloss": test_logloss,
        },
        results=[cross_result],
        summary={
            "train_mode": train_mode,
            "test_mode": test_mode,
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "feature_count": X_train.shape[1],
            "accuracy_degradation": train_accuracy - test_accuracy,
            "description": (
                f"Cross-mode ablation: model trained on {train_mode} data, "
                f"evaluated on {test_mode} data. Accuracy degradation of "
                f"{train_accuracy - test_accuracy:.4f} is DESCRIPTIVE — it "
                f"measures classification label transferability, NOT trading "
                f"profit transfer."
            ),
        },
    )


# ---------------------------------------------------------------------------
# Symbol Ablation
# ---------------------------------------------------------------------------


def run_symbol_ablation(
    X_by_symbol: Dict[str, np.ndarray],
    y_by_symbol: Dict[str, np.ndarray],
    feature_names: Optional[List[str]] = None,
    trainer_kwargs: Optional[Dict[str, Any]] = None,
) -> AblationStudy:
    """Run symbol ablation study.

    For each symbol, trains on all OTHER symbols and tests on the held-out
    symbol.  Measures descriptive accuracy/logloss deltas — NOT profit impact.

    Args:
        X_by_symbol: Dict mapping symbol name to feature matrix.
        y_by_symbol: Dict mapping symbol name to label vector.
            Must have the same keys as X_by_symbol.
        feature_names: Optional list of feature names matching column count.
        trainer_kwargs: Optional kwargs forwarded to XGBoostTrainer.

    Returns:
        AblationStudy with study_type="symbol".

    Raises:
        ValueError: If fewer than 2 symbols provided or inputs invalid.
    """
    symbols = sorted(X_by_symbol.keys())
    y_symbols = set(y_by_symbol.keys())

    if symbols != sorted(y_symbols):
        raise ValueError(
            f"X_by_symbol and y_by_symbol must have the same symbol keys. "
            f"X has {symbols}, y has {sorted(y_symbols)}"
        )
    if len(symbols) < 2:
        raise ValueError(
            f"Need at least 2 symbols for symbol ablation, got {len(symbols)}"
        )

    # Validate all arrays
    n_features = None
    for sym in symbols:
        X = X_by_symbol[sym]
        y = y_by_symbol[sym]
        _validate_ablation_inputs(X, y, feature_names)
        if n_features is None:
            n_features = X.shape[1]
        elif X.shape[1] != n_features:
            raise ValueError(
                f"Symbol '{sym}' has {X.shape[1]} features, expected {n_features}"
            )

    results: List[SymbolAblationResult] = []

    for held_out in symbols:
        train_symbols = [s for s in symbols if s != held_out]

        # Build training set from all other symbols
        X_train_parts = [X_by_symbol[s] for s in train_symbols]
        y_train_parts = [y_by_symbol[s] for s in train_symbols]
        X_train = np.vstack(X_train_parts)
        y_train = np.concatenate(y_train_parts)

        # Held-out set
        X_held = X_by_symbol[held_out]
        y_held = y_by_symbol[held_out]

        if len(X_train) < 10:
            results.append(SymbolAblationResult(
                held_out_symbol=held_out,
                train_symbols=train_symbols,
                in_sample_accuracy=0.0,
                in_sample_logloss=0.0,
                held_out_accuracy=0.0,
                held_out_logloss=0.0,
                accuracy_delta=0.0,
                logloss_delta=0.0,
                held_out_sample_count=len(X_held),
                training_duration_seconds=0.0,
                limitations=[
                    f"Insufficient training samples ({len(X_train)}) for symbol ablation",
                ],
            ))
            continue

        # Train on N-1 symbols
        accuracy, logloss, duration = _train_and_evaluate(
            X_train, y_train,
            feature_names=feature_names,
            trainer_kwargs=trainer_kwargs,
        )

        # Evaluate on held-out symbol
        import xgboost as xgb
        hp = dict(ABLATION_HYPERPARAMS)
        if trainer_kwargs:
            hp.update(trainer_kwargs)
        trainer = XGBoostTrainer(mode="SWING", hyperparameters=hp)
        train_result = trainer.train(X_train, y_train, feature_names=feature_names)

        dheld = xgb.DMatrix(X_held, label=_encode_labels_np(y_held))
        if feature_names:
            dheld.feature_names = feature_names
        held_pred = train_result.model.predict(dheld)
        held_labels = np.argmax(held_pred, axis=1)
        held_true = _encode_labels_np(y_held)
        held_accuracy = float(np.mean(held_labels == held_true))

        # Logloss on held-out
        eps = 1e-15
        held_probs = np.clip(held_pred, eps, 1.0 - eps)
        held_logloss = 0.0
        for i in range(len(held_true)):
            held_logloss -= np.log(held_probs[i, held_true[i]])
        held_logloss = float(held_logloss / max(1, len(held_true)))

        results.append(SymbolAblationResult(
            held_out_symbol=held_out,
            train_symbols=train_symbols,
            in_sample_accuracy=accuracy,
            in_sample_logloss=logloss,
            held_out_accuracy=float(held_accuracy),
            held_out_logloss=held_logloss,
            accuracy_delta=float(accuracy - held_accuracy),
            logloss_delta=float(held_logloss - logloss),
            held_out_sample_count=len(X_held),
            training_duration_seconds=duration,
            limitations=[
                f"Symbol ablation of '{held_out}' is DESCRIPTIVE — "
                "accuracy delta does NOT measure profit per symbol",
                "Held-out performance depends on cross-symbol feature distribution similarity",
                "Small held-out sets produce noisier accuracy estimates",
                "Symbol-specific label distribution affects accuracy baseline",
            ],
        ))

    # Baseline: train on all symbols
    all_X = np.vstack([X_by_symbol[s] for s in symbols])
    all_y = np.concatenate([y_by_symbol[s] for s in symbols])
    all_accuracy, all_logloss, all_duration = _train_and_evaluate(
        all_X, all_y,
        feature_names=feature_names,
        trainer_kwargs=trainer_kwargs,
    )

    return AblationStudy(
        study_type="symbol",
        baseline_metrics={
            "all_symbols_accuracy": all_accuracy,
            "all_symbols_logloss": all_logloss,
        },
        results=results,
        summary={
            "symbols": symbols,
            "total_symbols": len(symbols),
            "ablations_run": len(results),
            "all_symbols_accuracy": all_accuracy,
            "description": (
                "Symbol ablation measures generalization across symbols. "
                "A model trained on N-1 symbols is evaluated on the held-out "
                "symbol.  Accuracy deltas describe cross-symbol label "
                "prediction transferability — NOT profit per symbol."
            ),
        },
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _encode_labels_np(y: np.ndarray) -> np.ndarray:
    """Encode string or integer labels to integer class indices 0, 1, 2.

    Handles both string labels (LONG_NOW/SHORT_NOW/NO_TRADE) and integer labels.
    """
    if y.dtype.kind in ("i", "u"):
        return y.astype(int)

    _LABEL_TO_INT: Dict[str, int] = {
        "LONG_NOW": 0,
        "SHORT_NOW": 1,
        "NO_TRADE": 2,
    }

    result = np.zeros(len(y), dtype=int)
    for i, label in enumerate(y):
        if isinstance(label, (bytes,)):
            label = label.decode("utf-8", errors="replace")
        if label in _LABEL_TO_INT:
            result[i] = _LABEL_TO_INT[label]
        else:
            raise ValueError(
                f"Unknown label at index {i}: '{label}'. "
                f"Expected LONG_NOW, SHORT_NOW, or NO_TRADE."
            )
    return result
