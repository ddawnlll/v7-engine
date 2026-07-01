"""Walk-Forward Validation Runner — actual model training and metric computation.

Performs walk-forward validation with real XGBoost models trained per fold
using mode-specific hyperparameter configurations. Computes per-fold
financial metrics (Sharpe, win rate, max drawdown, profit factor) and
overfitting diagnostics (train vs validation gap).

Supports all three modes: SWING (4h baseline), SCALP (1h), AGGRESSIVE_SCALP (15m).
Mode-specific annualization factors and window defaults are applied automatically.

This module IMPORTS xgboost and numpy. It is intended for the training
environment, NOT the gate-check environment.

Usage:
    from alphaforge.validation.walk_forward_runner import run_walk_forward
    report = run_walk_forward(n_bars=4000, n_symbols=3)
    # report is a dict with fold_metrics, overfit_flags, aggregate_metrics

    # Mode-specific:
    scalp_report = run_walk_forward(n_bars=6000, n_symbols=3, mode="SCALP")
    agg_report = run_walk_forward(n_bars=6000, n_symbols=3, mode="AGGRESSIVE_SCALP")
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xgboost as xgb

from alphaforge.validation.contracts import (
    DEFAULT_FOLD_CONFIGS,
    DEFAULT_PURGE_POLICIES,
    MODE_PURGE_BARS,
    Fold,
    Mode,
    OverfitFlag,
    PurgePolicy,
    ValidationVerdict,
    WalkForwardConfig,
    WindowType,
)
from alphaforge.validation.walk_forward import WalkForwardValidator
# ---------------------------------------------------------------------------
# Mode-specific hyperparameters (LOCKED_INITIAL_BASELINE)
# SWING: widest windows, deepest memory — established baseline
# SCALP: 1h bars, slightly faster — match intraday horizon
# AGGRESSIVE_SCALP: 15m bars, fastest reaction — microstructure aware
# ---------------------------------------------------------------------------

# Label mapping for multi-class classification
_LABEL_TO_INT: Dict[str, int] = {
    "LONG_NOW": 0,
    "SHORT_NOW": 1,
    "NO_TRADE": 2,
}

_INT_TO_LABEL: Dict[int, str] = {v: k for k, v in _LABEL_TO_INT.items()}
_NUM_CLASSES: int = 3

# Conservative SWING hyperparameters (LOCKED_INITIAL_BASELINE)
SWING_DEFAULT_HYPERPARAMS: Dict[str, Any] = {
    "objective": "multi:softprob",
    "num_class": _NUM_CLASSES,
    "max_depth": 4,
    "learning_rate": 0.05,
    "n_estimators": 200,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "gamma": 0.1,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "eval_metric": "mlogloss",
    "early_stopping_rounds": 20,
    "random_state": 42,
    "verbosity": 0,
}

# SCALP hyperparameters (LOCKED_INITIAL_BASELINE)
# Slightly faster learning rate, shallower trees for 1h micro-patterns.
# Reduced n_estimators to prevent overfitting on shorter lookback windows.
SCALP_DEFAULT_HYPERPARAMS: Dict[str, Any] = {
    "objective": "multi:softprob",
    "num_class": _NUM_CLASSES,
    "max_depth": 3,
    "learning_rate": 0.08,
    "n_estimators": 150,
    "subsample": 0.7,
    "colsample_bytree": 0.7,
    "min_child_weight": 3,
    "gamma": 0.2,
    "reg_alpha": 0.2,
    "reg_lambda": 0.8,
    "eval_metric": "mlogloss",
    "early_stopping_rounds": 15,
    "random_state": 42,
    "verbosity": 0,
}

# AGGRESSIVE_SCALP hyperparameters (LOCKED_INITIAL_BASELINE)
# Highest learning rate, shallowest trees for fast microstructure adaptation.
# Stronger regularization to combat noise at 15m resolution.
AGGRESSIVE_SCALP_DEFAULT_HYPERPARAMS: Dict[str, Any] = {
    "objective": "multi:softprob",
    "num_class": _NUM_CLASSES,
    "max_depth": 3,
    "learning_rate": 0.10,
    "n_estimators": 100,
    "subsample": 0.65,
    "colsample_bytree": 0.65,
    "min_child_weight": 2,
    "gamma": 0.3,
    "reg_alpha": 0.3,
    "reg_lambda": 0.5,
    "eval_metric": "mlogloss",
    "early_stopping_rounds": 10,
    "random_state": 42,
    "verbosity": 0,
}

# Mode hyperparameter lookup
_MODE_HYPERPARAMS: Dict[str, Dict[str, Any]] = {
    "SWING": SWING_DEFAULT_HYPERPARAMS,
    "SCALP": SCALP_DEFAULT_HYPERPARAMS,
    "AGGRESSIVE_SCALP": AGGRESSIVE_SCALP_DEFAULT_HYPERPARAMS,
}

RANDOM_SEED: int = 42

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Walk-forward config — smaller windows so we can construct 6+ folds from
# moderate amounts of synthetic data.
WFV_TRAIN_WINDOW_BARS: int = 500
WFV_TEST_WINDOW_BARS: int = 200
WFV_PURGE_BARS: int = MODE_PURGE_BARS[Mode.SWING]  # 20
WFV_EMBARGO_BARS: int = 20
WFV_MIN_FOLDS: int = 3  # Per issue spec: >= 3 folds
WFV_VAL_FRACTION: float = 0.25  # fraction of test window used for validation

# Overfitting thresholds
OVERFIT_ACCURACY_GAP_THRESHOLD: float = 0.15  # train - val accuracy > this => flagged
OVERFIT_LOGLOSS_GAP_THRESHOLD: float = 0.10  # val - train logloss > this => flagged

# Mode-specific parameters (LOCKED_INITIAL_BASELINE)
# Periods per year for annualized Sharpe computation:
#   SWING: 4h bars   → 365 * 6 = 2190
#   SCALP: 1h bars   → 365 * 24 = 8760
#   AGGRESSIVE_SCALP: 15m bars → 365 * 96 = 35040
MODE_ANNUALIZATION: Dict[str, float] = {
    "SWING": 2190.0,
    "SCALP": 8760.0,
    "AGGRESSIVE_SCALP": 35040.0,
}

# Backward-compatible alias for SWING annualization (used in function defaults)
ANNUALIZATION_FACTOR: float = 2190.0

# Default purge/embargo bars per mode for walk_forward_runner test configs
MODE_RUNNER_PURGE_BARS: Dict[str, int] = {
    "SWING": 20,
    "SCALP": 100,
    "AGGRESSIVE_SCALP": 200,
}
MODE_RUNNER_EMBARGO_BARS: Dict[str, int] = {
    "SWING": 20,
    "SCALP": 100,
    "AGGRESSIVE_SCALP": 200,
}


# ---------------------------------------------------------------------------
# Data classes for walk-forward results
# ---------------------------------------------------------------------------


@dataclass
class FoldMetrics:
    """Per-fold financial and training metrics."""

    fold_index: int
    # Sample counts
    train_count: int
    val_count: int
    oos_count: int
    # Training metrics
    train_accuracy: float
    val_accuracy: float
    train_logloss: float
    val_logloss: float
    # OOS financial metrics
    sharpe: float
    win_rate: float
    max_drawdown: float
    profit_factor: float
    # OOS trade counts
    total_trades: int
    long_trades: int
    short_trades: int
    no_trade_count: int
    # Overfitting indicators
    accuracy_gap: float  # train_acc - val_acc
    logloss_gap: float  # val_logloss - train_logloss


@dataclass
class WalkForwardResult:
    """Complete walk-forward validation result."""

    folds: List[FoldMetrics] = field(default_factory=list)
    overfit_flags: List[OverfitFlag] = field(default_factory=list)
    aggregate_metrics: Dict[str, Any] = field(default_factory=dict)
    feature_importance: Dict[str, Any] = field(default_factory=dict)
    verdict: str = "INCONCLUSIVE"
    report_id: str = ""
    generated_at: str = ""
    config_summary: Dict[str, Any] = field(default_factory=dict)
    data_summary: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------


def generate_walk_forward_ohlcv(
    n_bars: int = 4000,
    symbols: Tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
    random_seed: int = 42,
) -> Dict[str, np.ndarray]:
    """Generate synthetic multi-symbol OHLCV data for walk-forward validation.

    Args:
        n_bars: Number of bars per symbol.
        symbols: Trading pair symbols.
        random_seed: Random seed for reproducibility.

    Returns:
        Dict with keys 'open', 'high', 'low', 'close', 'volume' — each a 1D
        numpy array of length n_bars * len(symbols), interleaved by symbol.
    """
    rng = np.random.RandomState(random_seed)

    all_open: List[np.ndarray] = []
    all_high: List[np.ndarray] = []
    all_low: List[np.ndarray] = []
    all_close: List[np.ndarray] = []
    all_volume: List[np.ndarray] = []
    all_symbol: List[str] = []

    for sym in symbols:
        # Random walk for close prices
        returns = rng.randn(n_bars) * 0.02
        close = 100.0 * np.exp(np.cumsum(returns))
        close = np.maximum(close, 0.01)

        # Derived OHLC
        noise = rng.randn(n_bars) * 0.005
        open_arr = close * (1.0 + noise * 0.3)

        high_noise = rng.uniform(0.0, 0.015, n_bars)
        low_noise = rng.uniform(0.0, 0.015, n_bars)
        high = np.maximum(open_arr, close) * (1.0 + high_noise)
        low = np.minimum(open_arr, close) * (1.0 - low_noise)
        low = np.minimum(low, np.minimum(open_arr, close))
        high = np.maximum(high, np.maximum(open_arr, close))

        volume = rng.lognormal(mean=10.0, sigma=1.0, size=n_bars)

        all_open.append(open_arr)
        all_high.append(high)
        all_low.append(low)
        all_close.append(close)
        all_volume.append(volume)
        all_symbol.extend([sym] * n_bars)

    return {
        "open": np.concatenate(all_open),
        "high": np.concatenate(all_high),
        "low": np.concatenate(all_low),
        "close": np.concatenate(all_close),
        "volume": np.concatenate(all_volume),
        "symbol": all_symbol,
    }


def generate_walk_forward_labels(
    n_samples: int,
    random_seed: int = 42,
) -> np.ndarray:
    """Generate synthetic label vector for walk-forward validation.

    Produces a roughly balanced 3-class label distribution.

    Args:
        n_samples: Number of label rows.
        random_seed: Random seed.

    Returns:
        numpy array of string labels (LONG_NOW, SHORT_NOW, NO_TRADE).
    """
    rng = np.random.RandomState(random_seed)
    labels = rng.choice(["LONG_NOW", "SHORT_NOW", "NO_TRADE"], size=n_samples)
    return labels


# ---------------------------------------------------------------------------
# Financial metrics computation
# ---------------------------------------------------------------------------


def _class_predictions_to_returns(
    y_pred: np.ndarray,
    y_true: np.ndarray,
) -> np.ndarray:
    """Convert classification predictions to trade returns.

    The return for each prediction is:
      - +1 if predicted class matches true class AND true class is LONG_NOW
      - +1 if predicted class matches true class AND true class is SHORT_NOW
      - -0.5 if predicted LONG_NOW but true is NO_TRADE (false positive long)
      - -0.5 if predicted SHORT_NOW but true is NO_TRADE (false positive short)
      - -1 if predicted LONG_NOW but true is SHORT_NOW (wrong direction)
      - -1 if predicted SHORT_NOW but true is LONG_NOW (wrong direction)
      - 0 if predicted NO_TRADE (staying out — no PnL impact)

    This is a simplified PnL attribution: a correct directional call yields
    a positive unit return; an incorrect directional call yields a negative
    unit return.
    """
    n = len(y_pred)
    returns = np.zeros(n, dtype=np.float64)

    for i in range(n):
        pred = y_pred[i]
        true_val = y_true[i]

        if pred == 2:  # NO_TRADE prediction — no PnL
            returns[i] = 0.0
        elif pred == true_val:
            # Correct directional call
            returns[i] = 1.0
        else:
            # Incorrect call
            if pred == 0 and true_val == 1:  # Long but should be short
                returns[i] = -1.0
            elif pred == 1 and true_val == 0:  # Short but should be long
                returns[i] = -1.0
            elif pred == 0 and true_val == 2:  # Long but should be no-trade
                returns[i] = -0.5
            elif pred == 1 and true_val == 2:  # Short but should be no-trade
                returns[i] = -0.5

    return returns


def compute_sharpe_ratio(
    returns: np.ndarray,
    annualization_factor: float = ANNUALIZATION_FACTOR,
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
    return mu / sigma * np.sqrt(annualization_factor)


def compute_win_rate(y_pred: np.ndarray, y_true: np.ndarray) -> float:
    """Compute win rate: fraction of predictions where direction was correct.

    A prediction is a "win" if the predicted class matches the true class
    exactly. NO_TRADE predictions matching NO_TRADE truth are not counted
    as wins (they are neutral, not trades).
    """
    # Only count actual trade predictions (LONG_NOW=0 or SHORT_NOW=1)
    trade_mask = (y_pred == 0) | (y_pred == 1)
    if not np.any(trade_mask):
        return 0.0

    trades_correct = np.sum((y_pred == y_true) & trade_mask)
    total_trades = int(np.sum(trade_mask))
    return float(trades_correct) / total_trades if total_trades > 0 else 0.0


def compute_max_drawdown(returns: np.ndarray) -> float:
    """Compute maximum drawdown from cumulative returns.

    Returns a negative number (e.g., -0.15 = 15% drawdown). 0.0 if no drawdown.
    """
    if len(returns) == 0:
        return 0.0

    cumulative = np.cumsum(returns)
    peak = np.maximum.accumulate(cumulative)
    drawdowns = cumulative - peak
    return float(np.min(drawdowns))


def compute_profit_factor(returns: np.ndarray) -> float:
    """Compute profit factor: gross profit / gross loss.

    Returns inf if no losses, 0.0 if no profits and no losses.
    """
    positive = np.sum(returns[returns > 0])
    negative = abs(np.sum(returns[returns < 0]))
    if negative < 1e-12:
        return float("inf") if positive > 0 else 1.0
    return float(positive / negative)


def compute_all_metrics(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    annualization_factor: float = ANNUALIZATION_FACTOR,
) -> Dict[str, Any]:
    """Compute all financial metrics from classification predictions.

    Args:
        y_pred: Integer predicted labels (0/1/2).
        y_true: Integer true labels (0/1/2).
        annualization_factor: Periods per year for Sharpe annualization.
            Defaults to ANNUALIZATION_FACTOR (2190 for SWING 4h bars).

    Returns:
        Dict with sharpe, win_rate, max_drawdown, profit_factor, and trade counts.
    """
    returns = _class_predictions_to_returns(y_pred, y_true)

    trade_mask = (y_pred == 0) | (y_pred == 1)
    total_trades = int(np.sum(trade_mask))
    long_trades = int(np.sum(y_pred == 0))
    short_trades = int(np.sum(y_pred == 1))
    no_trade_count = int(np.sum(y_pred == 2))

    return {
        "sharpe": compute_sharpe_ratio(returns, annualization_factor=annualization_factor),
        "win_rate": compute_win_rate(y_pred, y_true),
        "max_drawdown": compute_max_drawdown(returns),
        "profit_factor": compute_profit_factor(returns),
        "total_trades": total_trades,
        "long_trades": long_trades,
        "short_trades": short_trades,
        "no_trade_count": no_trade_count,
    }


# ---------------------------------------------------------------------------
# Walk-Forward Runner
# ---------------------------------------------------------------------------


def _build_walk_forward_config(
    mode: Mode = Mode.SWING,
    min_folds: int = WFV_MIN_FOLDS,
    train_window_bars: int | None = None,
    test_window_bars: int | None = None,
    purge_bars: int | None = None,
    embargo_bars: int | None = None,
    val_fraction: float = WFV_VAL_FRACTION,
) -> WalkForwardConfig:
    """Build a walk-forward config suitable for synthetic data evaluation.

    When optional bar parameters are None, mode-specific defaults from
    DEFAULT_FOLD_CONFIGS are used. This ensures each mode gets appropriate
    window sizes, purge/embargo bars, and window type.

    Args:
        mode: Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).
        min_folds: Minimum fold count.
        train_window_bars: Training window in bars. None = mode default.
        test_window_bars: Test window in bars. None = mode default.
        purge_bars: Purge gap in bars. None = mode default.
        embargo_bars: Embargo in bars. None = mode default.
        val_fraction: Fraction of test window for validation.

    Returns:
        WalkForwardConfig with appropriate mode-specific parameters.
    """
    mode_str = mode.value
    default_config = DEFAULT_FOLD_CONFIGS.get(mode)

    if train_window_bars is None:
        train_window_bars = (
            default_config.train_window_bars if default_config else WFV_TRAIN_WINDOW_BARS
        )
    if test_window_bars is None:
        test_window_bars = (
            default_config.test_window_bars if default_config else WFV_TEST_WINDOW_BARS
        )
    if purge_bars is None:
        purge_bars = MODE_RUNNER_PURGE_BARS.get(mode_str, WFV_PURGE_BARS)
    if embargo_bars is None:
        embargo_bars = MODE_RUNNER_EMBARGO_BARS.get(mode_str, WFV_EMBARGO_BARS)

    window_type = WindowType.ANCHORED
    if default_config is not None:
        window_type = default_config.window_type

    return WalkForwardConfig(
        mode=mode,
        min_folds=min_folds,
        train_ratio=0.50,
        val_ratio=val_fraction,
        oos_ratio=0.25,
        train_window_bars=train_window_bars,
        test_window_bars=test_window_bars,
        purge_bars=purge_bars,
        embargo_bars=embargo_bars,
        window_type=window_type,
    )


def run_walk_forward(
    n_bars: int = 2000,
    n_symbols: int = 3,
    random_seed: int = 42,
    train_window_bars: int | None = None,
    test_window_bars: int | None = None,
    min_folds: int = WFV_MIN_FOLDS,
    mode: str = "SWING",
) -> WalkForwardResult:
    """Run complete walk-forward validation for a specified trading mode.

    1. Generate synthetic OHLCV data with the specified bar count.
    2. Compute features via the feature pipeline (mode-aware).
    3. Generate synthetic labels.
    4. Assemble a chronological dataset (feature rows sorted by timestamp).
    5. Split into walk-forward folds using WalkForwardValidator.
    6. For each fold, train an XGBoost classifier with mode-appropriate
       hyperparameters on the training subset, evaluate on validation
       and OOS subsets.
    7. Compute per-fold financial metrics.
    8. Check for overfitting (train vs val accuracy/logloss gap).
    9. Assemble aggregate metrics and verdict.

    Args:
        n_bars: Number of bars per symbol. Total bars = n_bars * n_symbols.
        n_symbols: Number of trading symbols.
        random_seed: Random seed for reproducibility.
        train_window_bars: Training window size in bars. None = mode default.
        test_window_bars: Test window size in bars. None = mode default.
        min_folds: Minimum number of folds.
        mode: Trading mode ('SWING', 'SCALP', 'AGGRESSIVE_SCALP').

    Returns:
        WalkForwardResult with folds, overfit_flags, aggregate_metrics, verdict.
    """
    # Validate mode and get mode-specific config
    mode_upper = mode.upper().strip()
    if mode_upper not in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        raise ValueError(
            f"Unsupported mode: '{mode}'. Must be SWING, SCALP, or AGGRESSIVE_SCALP."
        )
    mode_enum = Mode(mode_upper)
    mode_str = mode_upper

    # Get mode-specific hyperparameters
    hyperparams = _MODE_HYPERPARAMS.get(mode_str, SWING_DEFAULT_HYPERPARAMS).copy()

    # Get mode-specific annualization factor
    annualization = MODE_ANNUALIZATION.get(mode_str, 2190.0)

    # ------------------------------------------------------------------
    # 1. Generate synthetic data
    # ------------------------------------------------------------------
    symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT")[:n_symbols]
    ohlcv_data = generate_walk_forward_ohlcv(
        n_bars=n_bars,
        symbols=symbols,
        random_seed=random_seed,
    )
    total_bars = n_bars * len(symbols)
    logger.info(f"[{mode_str}] Generated {total_bars} bars across {len(symbols)} symbols")

    # ------------------------------------------------------------------
    # 2. Compute features (mode-aware)
    # ------------------------------------------------------------------
    from alphaforge.features.pipeline import compute_features

    feature_matrix = compute_features(ohlcv_data, mode=mode_str)
    feature_names = sorted(feature_matrix.features.keys())
    logger.info(f"[{mode_str}] Computed {len(feature_names)} features: {feature_names}")

    # Assemble feature array
    X_all = np.column_stack([
        feature_matrix.features[name] for name in feature_names
    ])

    # Remove rows with NaN (lookback gaps)
    nan_mask = np.isnan(X_all).any(axis=1)
    valid_count = int((~nan_mask).sum())
    X = X_all[~nan_mask]
    X = np.ascontiguousarray(X, dtype=np.float64)
    logger.info(f"Feature matrix: {valid_count} valid rows out of {len(X_all)}")

    # Build timestamp and symbol arrays for valid rows
    all_symbols_list = ohlcv_data["symbol"]
    symbol_list = []
    timestamp_list = []
    for i in range(len(all_symbols_list)):
        if not nan_mask[i]:
            symbol_list.append(all_symbols_list[i])
            # Each row gets a chronologically sorted ISO timestamp
            # Format: 2025-01-01T{row_index:06d}
            timestamp_list.append(f"2025-01-01T{i:06d}")

    # ------------------------------------------------------------------
    # 3. Generate synthetic labels
    # ------------------------------------------------------------------
    y_labels = generate_walk_forward_labels(len(X), random_seed=random_seed)
    y_int = np.array([_LABEL_TO_INT[str(lbl)] for lbl in y_labels], dtype=int)

    # ------------------------------------------------------------------
    # 4. Build chronological dataset for WalkForwardValidator
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

    # ------------------------------------------------------------------
    # 5. Split into walk-forward folds
    # ------------------------------------------------------------------
    config = _build_walk_forward_config(
        mode=mode_enum,
        min_folds=min_folds,
        train_window_bars=train_window_bars,
        test_window_bars=test_window_bars,
    )
    purge_policy = PurgePolicy(
        mode=mode_enum,
        purge_bars=config.purge_bars,
        embargo_bars=config.embargo_bars,
    )
    validator = WalkForwardValidator(config, purge_policy)

    try:
        folds = validator.split(chrono_dataset)
    except Exception as e:
        logger.error(f"[{mode_str}] Fold split failed: {e}")
        return WalkForwardResult(
            overfit_flags=[
                OverfitFlag(
                    indicator="fold_split_failure",
                    severity="CRITICAL",
                    description=f"Could not split dataset: {e}",
                )
            ],
            verdict=ValidationVerdict.INCONCLUSIVE.value,
        )

    logger.info(f"[{mode_str}] Split into {len(folds)} walk-forward folds")

    # ------------------------------------------------------------------
    # 6. Train and evaluate per fold
    # ------------------------------------------------------------------
    fold_metrics: List[FoldMetrics] = []
    overfit_flags: List[OverfitFlag] = []
    last_booster: Any = None

    for fold in folds:
        fi = fold.fold_index
        train_idx = fold.train_indices
        val_idx = fold.val_indices
        oos_idx = fold.oos_indices

        # Ensure indices are within bounds
        train_idx = [i for i in train_idx if i < len(X)]
        val_idx = [i for i in val_idx if i < len(X)]
        oos_idx = [i for i in oos_idx if i < len(X)]

        if len(train_idx) < 10 or len(val_idx) < 5 or len(oos_idx) < 5:
            logger.warning(f"[{mode_str}] Fold {fi}: insufficient samples. Skipping.")
            continue

        X_train = X[train_idx]
        y_train = y_int[train_idx]
        X_val = X[val_idx]
        y_val = y_int[val_idx]
        X_oos = X[oos_idx]
        y_oos = y_int[oos_idx]

        # Train XGBoost with mode-specific hyperparameters
        dtrain = xgb.DMatrix(X_train, label=y_train)
        dtrain.feature_names = feature_names
        dval = xgb.DMatrix(X_val, label=y_val)
        dval.feature_names = feature_names
        doos = xgb.DMatrix(X_oos, label=y_oos)
        doos.feature_names = feature_names

        xgb_params = {
            k: v for k, v in hyperparams.items()
            if k in {
                "objective", "num_class", "max_depth", "learning_rate",
                "subsample", "colsample_bytree", "min_child_weight",
                "gamma", "reg_alpha", "reg_lambda", "eval_metric",
                "random_state", "verbosity",
            }
        }

        start_t = time.monotonic()
        booster = xgb.train(
            params=xgb_params,
            dtrain=dtrain,
            num_boost_round=hyperparams.get("n_estimators", 200),
            evals=[(dtrain, "train"), (dval, "val")],
            early_stopping_rounds=hyperparams.get("early_stopping_rounds", 20),
            verbose_eval=False,
        )
        elapsed = time.monotonic() - start_t

        # Predictions
        train_pred = np.argmax(booster.predict(dtrain), axis=1).astype(int)
        val_pred = np.argmax(booster.predict(dval), axis=1).astype(int)
        oos_pred = np.argmax(booster.predict(doos), axis=1).astype(int)

        # Training metrics
        train_acc = float(np.mean(train_pred == y_train))
        val_acc = float(np.mean(val_pred == y_val))

        # Logloss from eval
        train_logloss = 0.0
        val_logloss = 0.0
        try:
            eval_result_train = booster.eval(dtrain)
            if eval_result_train:
                _, vs = eval_result_train.split(":")
                train_logloss = float(vs.strip())
        except (ValueError, AttributeError):
            pass
        try:
            eval_result_val = booster.eval(dval)
            if eval_result_val:
                _, vs = eval_result_val.split(":")
                val_logloss = float(vs.strip())
        except (ValueError, AttributeError):
            pass

        # OOS financial metrics
        oos_fin_metrics = compute_all_metrics(
            oos_pred, y_oos, annualization_factor=annualization
        )

        # Overfitting indicators
        acc_gap = train_acc - val_acc
        ll_gap = val_logloss - train_logloss

        if acc_gap > OVERFIT_ACCURACY_GAP_THRESHOLD:
            overfit_flags.append(OverfitFlag(
                indicator="train_oos_gap",
                severity="HIGH",
                description=(
                    f"Fold {fi}: accuracy gap {acc_gap:.4f} exceeds threshold "
                    f"{OVERFIT_ACCURACY_GAP_THRESHOLD}. Train acc={train_acc:.4f}, "
                    f"Val acc={val_acc:.4f}"
                ),
            ))

        if ll_gap > OVERFIT_LOGLOSS_GAP_THRESHOLD:
            overfit_flags.append(OverfitFlag(
                indicator="train_oos_gap",
                severity="MEDIUM",
                description=(
                    f"Fold {fi}: logloss gap {ll_gap:.4f} exceeds threshold "
                    f"{OVERFIT_LOGLOSS_GAP_THRESHOLD}. Train ll={train_logloss:.4f}, "
                    f"Val ll={val_logloss:.4f}"
                ),
            ))

        fm = FoldMetrics(
            fold_index=fi,
            train_count=len(train_idx),
            val_count=len(val_idx),
            oos_count=len(oos_idx),
            train_accuracy=train_acc,
            val_accuracy=val_acc,
            train_logloss=train_logloss,
            val_logloss=val_logloss,
            sharpe=oos_fin_metrics["sharpe"],
            win_rate=oos_fin_metrics["win_rate"],
            max_drawdown=oos_fin_metrics["max_drawdown"],
            profit_factor=oos_fin_metrics["profit_factor"],
            total_trades=oos_fin_metrics["total_trades"],
            long_trades=oos_fin_metrics["long_trades"],
            short_trades=oos_fin_metrics["short_trades"],
            no_trade_count=oos_fin_metrics["no_trade_count"],
            accuracy_gap=acc_gap,
            logloss_gap=ll_gap,
        )
        fold_metrics.append(fm)
        last_booster = booster
        logger.info(
            f"Fold {fi}: train_acc={train_acc:.4f}, val_acc={val_acc:.4f}, "
            f"oos_sharpe={oos_fin_metrics['sharpe']:.4f}, "
            f"oos_win_rate={oos_fin_metrics['win_rate']:.4f}, "
            f"oos_max_dd={oos_fin_metrics['max_drawdown']:.4f}, "
            f"oos_pf={oos_fin_metrics['profit_factor']:.4f}, "
            f"time={elapsed:.3f}s"
        )

    # ------------------------------------------------------------------
    # 6b. Feature importance
    # ------------------------------------------------------------------
    # Aggregate XGBoost feature importance from the last fold's booster
    feature_importance: Dict[str, Any] = {}
    if last_booster is not None and feature_names:
        try:
            score_map = last_booster.get_score(importance_type="total_gain")
            if score_map:
                sorted_features = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
                top_features = [feat for feat, _ in sorted_features[:5]]
                all_features_set = set(feature_names) if feature_names else set()
                top_set = set(top_features)
                noise_features = sorted(all_features_set - top_set)
                feature_importance = {
                    "top_features": top_features,
                    "noise_features": noise_features[:10],
                    "method": "xgboost_total_gain",
                    "importance_scores": dict(sorted_features),
                }
        except Exception:
            logger.warning("Failed to compute feature importance", exc_info=True)

    # ------------------------------------------------------------------
    # 7. Compute aggregate metrics
    # ------------------------------------------------------------------
    if not fold_metrics:
        return WalkForwardResult(
            overfit_flags=overfit_flags,
            verdict=ValidationVerdict.FAIL_OOS.value,
        )

    avg_train_acc = float(np.mean([f.train_accuracy for f in fold_metrics]))
    avg_val_acc = float(np.mean([f.val_accuracy for f in fold_metrics]))
    avg_sharpe = float(np.mean([f.sharpe for f in fold_metrics]))
    avg_win_rate = float(np.mean([f.win_rate for f in fold_metrics]))
    avg_max_dd = float(np.mean([f.max_drawdown for f in fold_metrics]))
    avg_pf_raw = float(np.mean([
        min(f.profit_factor, 100.0) if f.profit_factor == float("inf") else f.profit_factor
        for f in fold_metrics
    ]))
    avg_accuracy_gap = float(np.mean([f.accuracy_gap for f in fold_metrics]))
    avg_logloss_gap = float(np.mean([f.logloss_gap for f in fold_metrics]))
    total_oos_trades = sum(f.total_trades for f in fold_metrics)

    # Sharpe stability (std of Sharpe across folds)
    sharpe_std = float(np.std([f.sharpe for f in fold_metrics], ddof=1)) if len(fold_metrics) > 1 else 0.0

    # ------------------------------------------------------------------
    # 8. Determine verdict
    # ------------------------------------------------------------------
    has_critical_overfit = any(f.severity == "CRITICAL" for f in overfit_flags)
    has_high_overfit = any(f.severity == "HIGH" for f in overfit_flags)

    if not fold_metrics:
        verdict = ValidationVerdict.FAIL_OOS.value
    elif has_critical_overfit:
        verdict = ValidationVerdict.FAIL_OVERFIT.value
    elif avg_accuracy_gap > OVERFIT_ACCURACY_GAP_THRESHOLD * 1.5:
        verdict = ValidationVerdict.FAIL_OVERFIT.value
    elif avg_sharpe < -1.0:
        verdict = ValidationVerdict.FAIL_OOS.value
    elif has_high_overfit:
        verdict = ValidationVerdict.PASS_WITH_LIMITATIONS.value
    else:
        verdict = ValidationVerdict.PASS.value

    # ------------------------------------------------------------------
    # 9. Assemble result
    # ------------------------------------------------------------------
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    rid_raw = f"{mode_str}|{len(fold_metrics)}|{total_oos_trades}|{ts}"
    rid_hash = hashlib.sha256(rid_raw.encode()).hexdigest()[:8]
    report_id = f"WFV-{mode_str}-{ts}-{rid_hash}"

    # Compute fold pass/fail metrics
    # A fold passes if sharpe > 0 (positive risk-adjusted return)
    folds_passing = sum(1 for f in fold_metrics if f.sharpe > 0)
    pass_ratio = folds_passing / len(fold_metrics) if fold_metrics else 0.0
    majority_pass = pass_ratio > 0.5

    # Fold stability score: coefficient of variation of Sharpe ratios
    sharpe_values = [f.sharpe for f in fold_metrics]
    if sharpe_values:
        mean_s = float(np.mean(sharpe_values))
        std_s = float(np.std(sharpe_values, ddof=1))
        if abs(mean_s) > 1e-10:
            fold_stability_score = max(0.0, min(1.0, 1.0 - std_s / abs(mean_s)))
        else:
            fold_stability_score = 0.0
    else:
        fold_stability_score = 0.0

    aggregate_metrics = {
        "n_folds": len(fold_metrics),
        "total_oos_trades": total_oos_trades,
        "avg_train_accuracy": avg_train_acc,
        "avg_val_accuracy": avg_val_acc,
        "avg_accuracy_gap": avg_accuracy_gap,
        "avg_logloss_gap": avg_logloss_gap,
        "avg_sharpe": avg_sharpe,
        "sharpe_stability_std": sharpe_std,
        "avg_win_rate": avg_win_rate,
        "avg_max_drawdown": avg_max_dd,
        "avg_profit_factor": avg_pf_raw,
        "fold_stability_score": fold_stability_score,
        "folds_passing": folds_passing,
        "majority_pass": majority_pass,
        "pass_ratio": pass_ratio,
    }

    config_summary = {
        "mode": config.mode.value,
        "train_window_bars": config.train_window_bars,
        "test_window_bars": config.test_window_bars,
        "purge_bars": config.purge_bars,
        "embargo_bars": config.embargo_bars,
        "window_type": config.window_type.value,
        "min_folds": config.min_folds,
        "actual_folds": len(fold_metrics),
    }

    data_summary = {
        "total_bars": total_bars,
        "n_symbols": len(symbols),
        "n_features": len(feature_names),
        "feature_names": feature_names,
        "valid_rows": len(X),
        "label_distribution": {
            lbl: int(np.sum(y_int == _LABEL_TO_INT[lbl]))
            for lbl in _LABEL_TO_INT
        },
    }

    return WalkForwardResult(
        folds=fold_metrics,
        overfit_flags=overfit_flags,
        aggregate_metrics=aggregate_metrics,
        feature_importance=feature_importance,
        verdict=verdict,
        report_id=report_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        config_summary=config_summary,
        data_summary=data_summary,
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def walk_forward_result_to_dict(result: WalkForwardResult) -> Dict[str, Any]:
    """Convert WalkForwardResult to a JSON-serializable dict."""
    return {
        "report_id": result.report_id,
        "generated_at": result.generated_at,
        "verdict": result.verdict,
        "config_summary": result.config_summary,
        "data_summary": result.data_summary,
        "feature_importance": result.feature_importance,
        "aggregate_metrics": result.aggregate_metrics,
        "fold_metrics": [
            {
                "fold_index": fm.fold_index,
                "sample_counts": {
                    "train": fm.train_count,
                    "val": fm.val_count,
                    "oos": fm.oos_count,
                },
                "training_metrics": {
                    "train_accuracy": fm.train_accuracy,
                    "val_accuracy": fm.val_accuracy,
                    "train_logloss": fm.train_logloss,
                    "val_logloss": fm.val_logloss,
                },
                "oos_financial_metrics": {
                    "sharpe": fm.sharpe,
                    "win_rate": fm.win_rate,
                    "max_drawdown": fm.max_drawdown,
                    "profit_factor": fm.profit_factor,
                },
                "oos_trade_counts": {
                    "total_trades": fm.total_trades,
                    "long_trades": fm.long_trades,
                    "short_trades": fm.short_trades,
                    "no_trade_count": fm.no_trade_count,
                },
                "overfitting_indicators": {
                    "accuracy_gap": fm.accuracy_gap,
                    "logloss_gap": fm.logloss_gap,
                },
                "feature_importance": result.feature_importance,
            }
            for fm in result.folds
        ],
        "overfit_risk_flags": [
            {
                "indicator": f.indicator,
                "severity": f.severity,
                "description": f.description,
            }
            for f in result.overfit_flags
        ],
    }


def save_walk_forward_report(
    result: WalkForwardResult,
    output_path: str,
) -> str:
    """Save walk-forward validation report as JSON.

    Args:
        result: WalkForwardResult from run_walk_forward().
        output_path: File path to write JSON.

    Returns:
        The output_path.
    """
    report_dict = walk_forward_result_to_dict(result)
    with open(output_path, "w") as f:
        json.dump(report_dict, f, indent=2, default=str)
    logger.info(f"Walk-forward report saved to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point for walk-forward validation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run walk-forward validation with TR-05 XGBoost hyperparameters"
    )
    parser.add_argument(
        "--n-bars", type=int, default=2000,
        help="Number of bars per symbol (default: 2000)"
    )
    parser.add_argument(
        "--n-symbols", type=int, default=3,
        help="Number of symbols (default: 3)"
    )
    parser.add_argument(
        "--min-folds", type=int, default=WFV_MIN_FOLDS,
        help=f"Minimum folds (default: {WFV_MIN_FOLDS})"
    )
    parser.add_argument(
        "--train-window", type=int, default=WFV_TRAIN_WINDOW_BARS,
        help=f"Training window bars (default: {WFV_TRAIN_WINDOW_BARS})"
    )
    parser.add_argument(
        "--test-window", type=int, default=WFV_TEST_WINDOW_BARS,
        help=f"Test window bars (default: {WFV_TEST_WINDOW_BARS})"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output JSON path (default: artifacts/reports/wfv_report_<ts>.json)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (default: 42)"
    )
    parser.add_argument(
        "--mode", type=str, default="SWING",
        help="Trading mode: SWING, SCALP, or AGGRESSIVE_SCALP (default: SWING)"
    )

    args = parser.parse_args()

    print(f"=== Multi-Timeframe Walk-Forward Validation ===")
    print(f"Mode: {args.mode}")
    print(f"Bars per symbol: {args.n_bars}")
    print(f"Symbols: {args.n_symbols}")
    print(f"Min folds: {args.min_folds}")
    print(f"Train window: {args.train_window} bars")
    print(f"Test window: {args.test_window} bars")
    print(f"Random seed: {args.seed}")
    print()

    result = run_walk_forward(
        n_bars=args.n_bars,
        n_symbols=args.n_symbols,
        random_seed=args.seed,
        train_window_bars=args.train_window,
        test_window_bars=args.test_window,
        min_folds=args.min_folds,
        mode=args.mode,
    )

    print(f"\n=== Walk-Forward Results ===")
    print(f"Folds: {len(result.folds)}")
    print(f"Verdict: {result.verdict}")
    print(f"Report ID: {result.report_id}")
    print()

    if result.folds:
        agg = result.aggregate_metrics
        print(f"Aggregate Metrics:")
        print(f"  Avg Train Accuracy:  {agg['avg_train_accuracy']:.4f}")
        print(f"  Avg Val Accuracy:    {agg['avg_val_accuracy']:.4f}")
        print(f"  Avg Accuracy Gap:    {agg['avg_accuracy_gap']:.4f}")
        print(f"  Avg Logloss Gap:     {agg['avg_logloss_gap']:.4f}")
        print(f"  Avg Sharpe:          {agg['avg_sharpe']:.4f}")
        print(f"  Sharpe Stability:    {agg['sharpe_stability_std']:.4f}")
        print(f"  Avg Win Rate:        {agg['avg_win_rate']:.4f}")
        print(f"  Avg Max Drawdown:    {agg['avg_max_drawdown']:.4f}")
        print(f"  Avg Profit Factor:   {agg['avg_profit_factor']:.4f}")
        print(f"  Total OOS Trades:    {agg['total_oos_trades']}")
        print()

        print("Per-Fold Metrics:")
        header = (
            f"  {'Fold':>5s}  {'TrainAcc':>10s}  {'ValAcc':>10s}  "
            f"{'AccGap':>8s}  {'Sharpe':>8s}  {'WinRate':>8s}  "
            f"{'MaxDD':>8s}  {'PF':>8s}  {'Trades':>7s}"
        )
        print(header)
        for fm in result.folds:
            pf_str = f"{fm.profit_factor:.4f}" if fm.profit_factor != float("inf") else "inf"
            print(
                f"  {fm.fold_index:5d}  {fm.train_accuracy:10.4f}  "
                f"{fm.val_accuracy:10.4f}  "
                f"{fm.accuracy_gap:8.4f}  {fm.sharpe:8.4f}  "
                f"{fm.win_rate:8.4f}  "
                f"{fm.max_drawdown:8.4f}  {pf_str:>8s}  {fm.total_trades:7d}"
            )

    if result.overfit_flags:
        print(f"\nOverfit Risk Flags ({len(result.overfit_flags)}):")
        for flag in result.overfit_flags:
            print(f"  [{flag.severity}] {flag.indicator}: {flag.description}")

    # Save report
    if args.output:
        output_path = args.output
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        output_path = f"artifacts/reports/wfv_report_{ts}.json"

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    save_walk_forward_report(result, output_path)
    print(f"\nReport saved to: {output_path}")

    return 0 if result.verdict != ValidationVerdict.FAIL_OOS.value else 1


# ---------------------------------------------------------------------------
# Nested walk-forward validation convenience entry point
# ---------------------------------------------------------------------------


def run_nested_walk_forward(
    n_bars: int = 2000,
    n_symbols: int = 3,
    random_seed: int = 42,
    mode: str = "SWING",
    outer_folds: int = 7,
    inner_folds: int = 3,
    embargo_days: int = 30,
    optuna_n_trials: int = 30,
    optuna_timeout_seconds: int = 120,
    outer_train_window_bars: int = 500,
    outer_test_window_bars: int = 200,
) -> Any:
    """Run nested walk-forward validation with Optuna-based hyperparameter tuning.

    Convenience function that delegates to the tuning module's implementation.

    Outer loop: [TRAIN][VAL][OOS] x outer_folds
    Inner loop: [TRAIN][VAL] x inner_folds (Optuna tunes hyperparameters)
    Best params -> train on outer TRAIN -> evaluate on outer OOS

    Args:
        n_bars: Bars per symbol.
        n_symbols: Number of symbols.
        random_seed: Random seed.
        mode: Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).
        outer_folds: Number of outer folds.
        inner_folds: Number of inner folds for Optuna tuning.
        embargo_days: Embargo between train and val in calendar days.
        optuna_n_trials: Optuna hyperparameter search trials.
        optuna_timeout_seconds: Timeout for Optuna study.

    Returns:
        NestedWalkForwardResult from the tuning module.
    """
    from alphaforge.tuning.nested_wfv import (
        run_nested_walk_forward as _run_nested,
    )
    return _run_nested(
        n_bars=n_bars,
        n_symbols=n_symbols,
        random_seed=random_seed,
        mode=mode,
        outer_folds=outer_folds,
        inner_folds=inner_folds,
        embargo_days=embargo_days,
        optuna_n_trials=optuna_n_trials,
        optuna_timeout_seconds=optuna_timeout_seconds,
        outer_train_window_bars=outer_train_window_bars,
        outer_test_window_bars=outer_test_window_bars,
    )


if __name__ == "__main__":
    import sys
    sys.exit(main())
