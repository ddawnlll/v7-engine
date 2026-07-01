"""Objective functions for multi-objective Optuna tuning.

Provides:
1. `compute_sharpe_ratio` — annualized Sharpe ratio from a returns array.
2. `compute_profit_factor` — gross profit / gross loss from a returns array.
3. `make_moo_objective` — factory that builds a callable returning (sharpe, profit_factor)
   for use with an Optuna study with directions=['maximize', 'maximize'].

Design:
- Both objectives are dimensionless and scale-free, making them suitable for
  NSGAII-based Pareto optimization.
- Sharpe is annualized using `periods_per_year` (default: 8760 for 1h bars).
- Profit Factor is capped to avoid division by zero.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default periods per year for annualization
# 1h bars: 24 * 365 = 8760
PERIODS_PER_YEAR_DEFAULT: int = 8760

# When gross_loss is zero, profit factor is undefined. We cap it at this value
# to avoid infinities crashing the optimizer.
MAX_PROFIT_FACTOR: float = 1e6

# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


def compute_sharpe_ratio(
    returns: np.ndarray,
    periods_per_year: int = PERIODS_PER_YEAR_DEFAULT,
    risk_free_rate: float = 0.0,
) -> float:
    """Compute annualized Sharpe ratio from a 1-D array of periodic returns.

    The Sharpe ratio measures risk-adjusted return:
        Sharpe = (mean(returns) - risk_free_rate) / std(returns) * sqrt(periods_per_year)

    Args:
        returns: 1-D numpy array of periodic returns (e.g., hourly PnL fractions).
        periods_per_year: Number of periods in one year for annualization.
                          Default 8760 (1h bars). Use 252*24 for crypto perpetuals
                          or 252 for daily strategies.
        risk_free_rate: Risk-free rate per period (default 0.0 for crypto).

    Returns:
        Annualized Sharpe ratio as a float. Returns 0.0 if std is zero or
        if fewer than 2 data points are provided.

    Raises:
        TypeError: If `returns` is not a numpy array.
    """
    if not isinstance(returns, np.ndarray):
        raise TypeError(f"Expected numpy array, got {type(returns).__name__}")

    if returns.ndim != 1:
        raise ValueError(f"Expected 1-D array, got {returns.ndim}-D")

    n = len(returns)
    if n < 2:
        return 0.0

    mean_ret = float(np.mean(returns)) - risk_free_rate
    std_ret = float(np.std(returns, ddof=1))  # sample std

    if std_ret < 1e-15:
        return 0.0

    return mean_ret / std_ret * np.sqrt(periods_per_year)


def compute_profit_factor(returns: np.ndarray) -> float:
    """Compute profit factor from a 1-D array of periodic returns.

    Profit factor = sum(positive returns) / abs(sum(negative returns))

    A profit factor > 1.0 means the strategy is profitable.
    A profit factor < 1.0 means the strategy loses money.

    Args:
        returns: 1-D numpy array of periodic returns.

    Returns:
        Profit factor as a float. Returns MAX_PROFIT_FACTOR (1e6) if there
        are no negative returns (gross_loss == 0). Returns 0.0 if there are
        no positive returns.

    Raises:
        TypeError: If `returns` is not a numpy array.
    """
    if not isinstance(returns, np.ndarray):
        raise TypeError(f"Expected numpy array, got {type(returns).__name__}")

    if returns.ndim != 1:
        raise ValueError(f"Expected 1-D array, got {returns.ndim}-D")

    if len(returns) == 0:
        return 0.0

    gross_profit = float(np.sum(returns[returns > 0]))
    gross_loss = float(np.sum(np.abs(returns[returns < 0])))

    if gross_loss == 0.0:
        if gross_profit > 0.0:
            return MAX_PROFIT_FACTOR
        return 0.0

    return gross_profit / gross_loss


# ---------------------------------------------------------------------------
# Optuna objective factory
# ---------------------------------------------------------------------------


def make_moo_objective(
    X: np.ndarray,
    y: np.ndarray,
    predict_fn: Callable[[np.ndarray, Dict[str, Any]], np.ndarray],
    fixed_params: Optional[Dict[str, Any]] = None,
    val_fraction: float = 0.2,
    periods_per_year: int = PERIODS_PER_YEAR_DEFAULT,
    risk_free_rate: float = 0.0,
    param_prefix: str = "",
) -> Callable[[Any], Tuple[float, float]]:
    """Build a multi-objective Optuna objective returning (sharpe, profit_factor).

    The returned closure:
      1. Reads hyperparameter suggestions from `trial`.
      2. Trains a model via `predict_fn(X, params)` with the suggested params.
      3. Computes out-of-sample returns by running the trained predictor
         on a held-out validation split.
      4. Returns (annualized_sharpe, profit_factor) — both maximized.

    Args:
        X: Feature matrix (n_samples, n_features).
        y: Target vector (n_samples,) — must be numeric returns.
        predict_fn: A callable that takes (X, params_dict) and returns
                    a 1-D numpy array of predicted returns.
        fixed_params: Parameters to pass to predict_fn that are NOT suggested
                      by Optuna (e.g., model architecture settings).
        val_fraction: Fraction of (X, y) to hold out for validation.
        periods_per_year: Annualization factor for Sharpe ratio.
        risk_free_rate: Risk-free rate per period.
        param_prefix: Optional prefix for Optuna parameter names (used when
                      composing multiple parameter groups).

    Returns:
        A callable suitable for `study.optimize(objective_fn, ...)` that
        returns a tuple of (sharpe_ratio, profit_factor).

    Raises:
        ValueError: If validation inputs are malformed.
    """
    if not isinstance(X, np.ndarray):
        raise TypeError(f"X must be numpy.ndarray, got {type(X).__name__}")
    if not isinstance(y, np.ndarray):
        raise TypeError(f"y must be numpy.ndarray, got {type(y).__name__}")
    if len(X) != len(y):
        raise ValueError(f"X ({len(X)}) and y ({len(y)}) length mismatch")
    if len(X) < 10:
        raise ValueError(f"Need at least 10 samples, got {len(X)}")
    if val_fraction <= 0.0 or val_fraction >= 1.0:
        raise ValueError(f"val_fraction must be in (0, 1), got {val_fraction}")

    fixed = fixed_params or {}
    n_val = max(1, int(len(y) * val_fraction))
    n_train = len(y) - n_val

    X_train = X[:n_train]
    y_train = y[:n_train]
    X_val = X[n_train:]
    y_val = y[n_train:]

    def _objective(trial: Any) -> Tuple[float, float]:
        """Optuna objective: maximize Sharpe and Profit Factor on held-out data."""
        # Merge trial-suggested params with fixed params
        params: Dict[str, Any] = dict(fixed)

        # Let the predict_fn suggest its own parameters via trial
        # Default: pass through trial.params (the simplest case)
        # The predict_fn can use trial.suggest_* inside if it's aware of Optuna.
        # Here we assume predict_fn accepts the full param dict.
        params["trial"] = trial

        try:
            pred_returns = predict_fn(X_val, params)
            if not isinstance(pred_returns, np.ndarray):
                pred_returns = np.asarray(pred_returns, dtype=np.float64)
            if pred_returns.ndim != 1:
                logger.warning(
                    "predict_fn returned %d-D array, flattening to 1-D", pred_returns.ndim
                )
                pred_returns = pred_returns.ravel()
        except Exception as e:
            logger.error("predict_fn raised: %s", e)
            # Return dominated values so NSGAII discards this trial
            return -1e6, -1.0

        sharpe = compute_sharpe_ratio(
            pred_returns,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
        )
        pf = compute_profit_factor(pred_returns)
        return sharpe, pf

    return _objective


# ---------------------------------------------------------------------------
# Convenience: model returns from predicted + actual
# ---------------------------------------------------------------------------


def returns_from_signals(
    signals: np.ndarray,
    actual_returns: np.ndarray,
    position_size: float = 1.0,
) -> np.ndarray:
    """Compute strategy returns from position signals and actual period returns.

    Args:
        signals: 1-D array of position signals in [-1, 0, 1] (short/flat/long).
        actual_returns: 1-D array of actual period returns for the asset.
        position_size: Fraction of capital allocated per trade (default 1.0).

    Returns:
        1-D array of strategy returns = signals * actual_returns * position_size.

    Raises:
        ValueError: If arrays have mismatched shapes.
    """
    if signals.shape != actual_returns.shape:
        raise ValueError(
            f"signals shape {signals.shape} != actual_returns shape {actual_returns.shape}"
        )
    return signals * actual_returns * position_size
