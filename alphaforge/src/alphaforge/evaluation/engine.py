"""
AlphaForge P8+P9 — evaluation framework and monitoring.

Evaluates model performance across walk-forward folds:
- Classification metrics (accuracy, precision, recall)
- Regression metrics (RMSE, MAE, R²)
- Trading metrics (win rate, expectancy, drawdown, profit factor)

Monitoring detects drift between training and production:
- Feature distribution drift (PSI)
- Prediction vs realized outcome comparison
- Confidence calibration drift
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error, r2_score

EVALUATION_VERSION = "eval-1.0.0"
MONITORING_VERSION = "mon-1.0.0"


# ── Classification metrics ─────────────────────────────────────────

def _win_rate(realized_r: list[float]) -> float:
    if not realized_r:
        return 0.0
    return sum(1 for r in realized_r if r > 0) / len(realized_r)


def _profit_factor(realized_r: list[float]) -> float:
    gross_wins = sum(r for r in realized_r if r > 0)
    gross_losses = abs(sum(r for r in realized_r if r < 0))
    if gross_losses == 0:
        return gross_wins if gross_wins > 0 else 0.0
    return gross_wins / gross_losses


def _max_drawdown(realized_r: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    dd = 0.0
    for r in realized_r:
        equity += r
        peak = max(peak, equity)
        dd = min(dd, equity - peak)
    return abs(dd)


def _expectancy(realized_r: list[float]) -> float:
    if not realized_r:
        return 0.0
    return sum(realized_r) / len(realized_r)


# ── Regression reliability ─────────────────────────────────────────

def regression_reliability(
    y_true: list[float] | np.ndarray,
    y_pred: list[float] | np.ndarray,
    n_buckets: int = 5,
) -> dict[str, Any]:
    """Evaluate regression reliability by predicted-R buckets.

    Groups predictions into equal-width buckets, then compares
    mean predicted vs mean realized R within each bucket.
    Reliable if predicted and realized move together monotonically.

    Args:
        y_true: Ground truth R values.
        y_pred: Predicted R values.
        n_buckets: Number of reliability buckets.

    Returns:
        Dict with per-bucket comparison and sign accuracy.
    """
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    n = len(y_true)
    if n == 0:
        return {"reliable": False, "buckets": [], "sign_accuracy": 0.0, "samples": 0}

    # Bucket by predicted R
    bin_edges = np.linspace(float(y_pred.min()), float(y_pred.max()), n_buckets + 1)
    if bin_edges[0] == bin_edges[-1]:
        bin_edges = np.linspace(-1, 1, n_buckets + 1)
    indices = np.digitize(y_pred, bin_edges) - 1
    indices = np.clip(indices, 0, n_buckets - 1)

    buckets = []
    monotonic_up = True
    prev_realized = -float("inf")
    for i in range(n_buckets):
        mask = indices == i
        if not mask.any():
            continue
        mean_pred = float(y_pred[mask].mean())
        mean_real = float(y_true[mask].mean())
        if mean_real < prev_realized - 0.01:
            monotonic_up = False
        prev_realized = mean_real
        buckets.append({
            "bucket": i,
            "range": [round(float(bin_edges[i]), 4), round(float(bin_edges[i + 1]), 4)],
            "count": int(mask.sum()),
            "mean_predicted_r": round(mean_pred, 4),
            "mean_realized_r": round(mean_real, 4),
            "error": round(abs(mean_pred - mean_real), 4),
        })

    # Sign accuracy: does predicted sign match realized sign?
    pred_sign = np.sign(y_pred)
    true_sign = np.sign(y_true)
    sign_correct = int((pred_sign == true_sign).sum())
    sign_accuracy = sign_correct / n if n > 0 else 0.0

    return {
        "reliable": monotonic_up and sign_accuracy >= 0.5,
        "buckets": buckets,
        "sign_accuracy": round(sign_accuracy, 4),
        "monotonic": monotonic_up,
        "samples": n,
    }


# ── Primary evaluation ─────────────────────────────────────────────

def evaluate_classification(
    y_true: list[int] | np.ndarray,
    y_pred: list[int] | np.ndarray,
) -> dict[str, Any]:
    """Evaluate classification performance.

    Args:
        y_true: Ground truth class labels (0=LONG, 1=SHORT, 2=NO_TRADE).
        y_pred: Predicted class labels.

    Returns:
        Dict with accuracy, F1 (macro), and per-class metrics.
    """
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    n = len(y_true)

    if n == 0:
        return {"accuracy": 0.0, "f1_macro": 0.0, "samples": 0}

    acc = float(accuracy_score(y_true, y_pred))
    f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))

    per_class = {}
    for i, label in enumerate(["LONG_NOW", "SHORT_NOW", "NO_TRADE"]):
        mask = y_true == i
        total = int(mask.sum())
        correct = int((y_pred[mask] == i).sum()) if total > 0 else 0
        per_class[label] = {
            "samples": total,
            "accuracy": round(correct / total, 4) if total > 0 else 0.0,
        }

    return {
        "accuracy": round(acc, 4),
        "f1_macro": round(f1, 4),
        "samples": n,
        "per_class": per_class,
    }


def evaluate_regression(
    y_true: list[float] | np.ndarray,
    y_pred: list[float] | np.ndarray,
) -> dict[str, Any]:
    """Evaluate regression performance.

    Args:
        y_true: Ground truth R values.
        y_pred: Predicted R values.

    Returns:
        Dict with RMSE, MAE, R².
    """
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    n = len(y_true)

    if n == 0:
        return {"rmse": 0.0, "mae": 0.0, "r2": 0.0, "samples": 0}

    return {
        "rmse": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 4),
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
        "samples": n,
    }


def evaluate_trading(
    realized_r: list[float],
) -> dict[str, Any]:
    """Evaluate trading performance from realized R values.

    Args:
        realized_r: List of realized R values (simulated or paper).

    Returns:
        Dict with win rate, profit factor, max drawdown, expectancy.
    """
    if not realized_r:
        return {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_r": 0.0,
            "expectancy_r": 0.0,
            "total_trades": 0,
            "net_r": 0.0,
        }

    net = sum(realized_r)
    return {
        "win_rate": round(_win_rate(realized_r), 4),
        "profit_factor": round(_profit_factor(realized_r), 4),
        "max_drawdown_r": round(_max_drawdown(realized_r), 4),
        "expectancy_r": round(_expectancy(realized_r), 4),
        "total_trades": len(realized_r),
        "net_r": round(net, 4),
    }


def evaluate_walk_forward(
    fold_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate evaluation across walk-forward folds.

    Args:
        fold_results: List of per-fold evaluation dicts.

    Returns:
        Aggregated evaluation with fold-level detail.
    """
    if not fold_results:
        return {"status": "no_folds", "fold_count": 0}

    all_realized_r = []
    for fold in fold_results:
        all_realized_r.extend(fold.get("realized_r", []))

    trading = evaluate_trading(all_realized_r)
    trading["fold_count"] = len(fold_results)
    trading["folds"] = fold_results
    return trading


# ── Monitoring (P9) ────────────────────────────────────────────────

def feature_psi(expected: np.ndarray, actual: np.ndarray, n_bins: int = 10) -> float:
    """Population Stability Index — measures feature distribution drift.

    PSI > 0.25 indicates significant drift.
    PSI > 0.1 indicates moderate drift.
    """
    if len(expected) == 0 or len(actual) == 0:
        return 0.0
    bins = np.linspace(0, 1, n_bins + 1)
    expected_pct = np.histogram(expected, bins)[0] / len(expected)
    actual_pct = np.histogram(actual, bins)[0] / len(actual)
    # Avoid division by zero
    expected_pct = np.clip(expected_pct, 0.001, 1.0)
    actual_pct = np.clip(actual_pct, 0.001, 1.0)
    psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    return round(float(psi), 4)


def detect_drift(
    training_stats: dict[str, Any],
    production_stats: dict[str, Any],
) -> dict[str, Any]:
    """Compare training vs production statistics for drift detection.

    Args:
        training_stats: Dict with 'feature_means', 'feature_stds', 'confidence_mean'.
        production_stats: Same structure from production window.

    Returns:
        Dict with drift flags and PSI values per feature.
    """
    train_features = training_stats.get("feature_means", {})
    prod_features = production_stats.get("feature_means", {})

    drifted_features = []
    for key in train_features:
        if key not in prod_features:
            continue
        train_val = float(train_features[key])
        prod_val = float(prod_features[key])
        if abs(train_val) > 0.001:
            rel_change = abs((prod_val - train_val) / train_val)
        else:
            rel_change = abs(prod_val - train_val)
        if rel_change > 0.5:
            drifted_features.append({
                "feature": key,
                "train_mean": round(train_val, 4),
                "prod_mean": round(prod_val, 4),
                "relative_change": round(rel_change, 4),
            })

    conf_drift = None
    train_conf = training_stats.get("confidence_mean")
    prod_conf = production_stats.get("confidence_mean")
    if train_conf is not None and prod_conf is not None:
        conf_drift = round(abs(float(prod_conf) - float(train_conf)), 4)

    return {
        "drift_detected": len(drifted_features) > 0 or (conf_drift is not None and conf_drift > 0.2),
        "drifted_features": drifted_features[:10],
        "confidence_drift": conf_drift,
        "psi_values": {},
    }
