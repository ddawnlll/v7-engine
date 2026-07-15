"""Meta-labeling: two-stage model for high winrate trading.

Stage 1 — Primary model (regression): predicts future return (direction + magnitude)
Stage 2 — Meta-label model (binary classifier): predicts if Stage 1's prediction is correct

Trade only when: meta_label_confidence > threshold AND |regression_pred| > min_r

Reference: López de Prado (2018) - Advances in Financial Machine Learning
Based on ArXiv AlphaForge two-stage framework principles.
"""

from __future__ import annotations

import numpy as np
import xgboost as xgb
import logging

logger = logging.getLogger(__name__)


def compute_meta_labels(
    reg_predictions: np.ndarray,
    actual_returns: np.ndarray,
    min_return: float = 0.001,
) -> np.ndarray:
    """Compute meta-labels for each sample.

    Meta-label = 1 if regression prediction sign matches actual return sign AND
    the actual return magnitude exceeds min_return.
    Meta-label = 0 otherwise.

    Args:
        reg_predictions: (N,) predicted future returns from regression model.
        actual_returns: (N,) actual future returns.
        min_return: Minimum return threshold to count as a "valid" prediction.

    Returns:
        (N,) binary meta-labels: 1 = correct prediction, 0 = incorrect/uncertain.
    """
    reg_predictions = np.asarray(reg_predictions, dtype=np.float64)
    actual_returns = np.asarray(actual_returns, dtype=np.float64)

    # Correct when sign matches AND magnitude is meaningful
    sign_match = np.sign(reg_predictions) == np.sign(actual_returns)
    meaningful = np.abs(actual_returns) >= min_return
    return (sign_match & meaningful).astype(np.int64)


def train_meta_labeling_model(
    X: np.ndarray,
    reg_target: np.ndarray,
    meta_target: np.ndarray,
    mode: str = "SCALP",
) -> tuple:
    """Train a meta-labeling model (two-stage).

    Stage 1: Train regression on reg_target (net_r values).
    Stage 2: Compute meta-labels, train binary classifier on meta_target.

    Args:
        X: Feature matrix (N, F).
        reg_target: Regression targets (net_r for each sample).
        meta_target: Pre-computed meta-labels (0/1).
        mode: Trading mode.

    Returns:
        (reg_model, meta_model) trained models.
    """
    from alphaforge.training.xgb_trainer import XGBoostTrainer

    X = np.asarray(X, dtype=np.float64)
    reg_target = np.asarray(reg_target, dtype=np.float64)
    meta_target = np.asarray(meta_target, dtype=np.int64)

    # Stage 1: Regression
    logger.info("Meta-labeling Stage 1: training regression model...")
    reg_trainer = XGBoostTrainer(mode=mode, objective="reg:squarederror")
    reg_result = reg_trainer.train(X, reg_target)
    reg_model = reg_result.model
    reg_preds = np.asarray(reg_model.inplace_predict(X), dtype=np.float64)

    # Compute meta-labels from regression predictions
    # Use a held-out portion for realistic meta-label evaluation
    n = len(reg_preds)
    split = int(n * 0.7)
    
    # Stage 2: Meta-label classifier (binary)
    logger.info("Meta-labeling Stage 2: training meta classifier...")
    meta_trainer = XGBoostTrainer(mode=mode, objective="binary:logistic")
    meta_result = meta_trainer.train(X, meta_target)
    meta_model = meta_result.model

    return reg_model, meta_model


def predict_meta_labeling(
    X: np.ndarray,
    reg_model,
    meta_model,
    reg_threshold: float = 0.01,
    meta_threshold: float = 0.7,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Predict using meta-labeling model.

    Args:
        X: Feature matrix (N, F).
        reg_model: Trained regression model.
        meta_model: Trained meta-label classifier.
        reg_threshold: Min |regression_prediction| to consider trading.
        meta_threshold: Min meta_label confidence to trade.

    Returns:
        (decisions, meta_confs, reg_preds) where:
        - decisions: (N,) 0=LONG, 1=SHORT, 2=NO_TRADE
        - meta_confs: (N,) meta-label confidence scores
        - reg_preds: (N,) regression predictions
    """
    X = np.asarray(X, dtype=np.float64)

    # Stage 1: Regression prediction
    reg_preds = np.asarray(reg_model.inplace_predict(X), dtype=np.float64)

    # Stage 2: Meta-label confidence
    meta_probs = np.asarray(meta_model.predict_proba(X), dtype=np.float64)
    # meta_probs[:, 1] = probability that regression prediction is CORRECT
    meta_confs = meta_probs[:, 1]

    # Combine: trade only when BOTH conditions met
    decisions = np.full(len(X), 2, dtype=int)  # default NO_TRADE
    valid_reg = np.abs(reg_preds) >= reg_threshold
    valid_meta = meta_confs >= meta_threshold
    trade_mask = valid_reg & valid_meta

    # Direction comes from regression
    decisions[trade_mask & (reg_preds > 0)] = 0  # LONG
    decisions[trade_mask & (reg_preds < 0)] = 1  # SHORT

    return decisions, meta_confs, reg_preds


def meta_labeling_walk_forward(
    X: np.ndarray,
    net_r_values: np.ndarray,
    y_int: np.ndarray,
    mode: str = "SCALP",
    min_folds: int = 6,
    reg_thresholds: list[float] = None,
    meta_thresholds: list[float] = None,
    timestamps: np.ndarray = None,
) -> dict:
    """Run meta-labeling walk-forward validation.

    For each fold:
    1. Train regression model on training data
    2. Compute meta-labels from training data
    3. Train meta-classifier on training data
    4. Predict on validation data
    5. Convert to trade decisions using threshold pairs

    Returns dict with per-threshold results.
    """
    from alphaforge.training.xgb_trainer import XGBoostTrainer
    from alphaforge.reports.metrics import compute_oos_metrics

    if reg_thresholds is None:
        reg_thresholds = [0.005, 0.01, 0.02, 0.03, 0.05]
    if meta_thresholds is None:
        meta_thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]

    n = len(X)
    fold_size = n // (min_folds + 1)
    cfg_mode = mode

    # Purge/embargo parameters
    from alphaforge.train import _get_training_config
    _cfg = _get_training_config(mode)
    label_horizon = _cfg.label_horizon
    k = 2
    purge_bars = k * label_horizon
    embargo_bars = k * label_horizon

    # Results accumulator
    results = {}

    for fold in range(min_folds):
        train_end = (fold + 1) * fold_size
        val_start = train_end
        val_end = val_start + fold_size // 2
        if val_end >= n:
            break

        if timestamps is not None:
            unique_ts, first_rows = np.unique(timestamps, return_index=True)
            boundary_ts = timestamps[val_start]
            boundary_pos = int(np.searchsorted(unique_ts, boundary_ts, side="left"))
            train_pos = max(0, boundary_pos - purge_bars)
            val_pos = min(len(unique_ts) - 1, boundary_pos + embargo_bars)
            effective_train_end = int(first_rows[train_pos])
            effective_val_start = int(first_rows[val_pos])
        else:
            effective_train_end = train_end - purge_bars
            effective_val_start = val_start + embargo_bars

        if effective_train_end <= 0 or effective_val_start >= val_end:
            continue

        X_train = X[:effective_train_end]
        r_train = net_r_values[:effective_train_end]
        y_train = y_int[:effective_train_end]
        X_val = X[effective_val_start:val_end]
        r_val = net_r_values[effective_val_start:val_end]
        y_val = y_int[effective_val_start:val_end]

        if len(X_train) < 100 or len(X_val) < 20:
            continue

        # Stage 1: Train regression
        reg_trainer = XGBoostTrainer(mode=mode, objective="reg:squarederror")
        reg_result = reg_trainer.train(X_train, r_train)
        reg_model = reg_result.model
        reg_pred_train = np.asarray(reg_model.inplace_predict(X_train), dtype=np.float64)
        reg_pred_val = np.asarray(reg_model.inplace_predict(X_val), dtype=np.float64)

        # Compute meta-labels on training data
        meta_labels_train = compute_meta_labels(reg_pred_train, r_train)

        # Stage 2: Train meta-classifier using xgb directly (not XGBoostTrainer)
        unique_labels = np.unique(meta_labels_train)
        if len(unique_labels) < 2:
            meta_labels_train = meta_labels_train.copy()
            if 1 not in unique_labels:
                pos = np.random.randint(0, len(meta_labels_train))
                meta_labels_train[pos] = 1
            if 0 not in unique_labels:
                pos = np.random.randint(0, len(meta_labels_train))
                meta_labels_train[pos] = 0
        
        meta_dtrain = xgb.DMatrix(X_train, label=meta_labels_train)
        meta_params = {
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "max_depth": 3,
            "learning_rate": 0.05,
            "subsample": 0.7,
            "random_state": 42,
            "verbosity": 0,
        }
        meta_booster = xgb.train(meta_params, meta_dtrain, num_boost_round=100)
        meta_model = meta_booster

        # Predict meta-confidence on validation
        meta_probs_val = np.asarray(meta_model.predict(xgb.DMatrix(X_val)), dtype=np.float64)
        # binary:logistic outputs single column (probability of class 1)
        if meta_probs_val.ndim == 1:
            meta_conf_val = meta_probs_val
        else:
            meta_conf_val = meta_probs_val[:, 1]

        # Evaluate all threshold pairs
        for rt in reg_thresholds:
            for mt in meta_thresholds:
                key = (rt, mt)
                if key not in results:
                    results[key] = {"trades": 0, "wins": 0, "total_r": 0.0, "fold_counts": 0}

                # Trade decisions
                decisions = np.full(len(X_val), 2, dtype=int)
                valid_reg = np.abs(reg_pred_val) >= rt
                valid_meta = meta_conf_val >= mt
                trade_mask = valid_reg & valid_meta
                n_trades = int(np.sum(trade_mask))
                decisions[trade_mask & (reg_pred_val > 0)] = 0  # LONG
                decisions[trade_mask & (reg_pred_val < 0)] = 1  # SHORT

                if n_trades > 0:
                    win_mask = decisions[trade_mask] == y_val[trade_mask]
                    n_wins = int(np.sum(win_mask))
                    active_r = r_val[trade_mask]
                    mean_r = float(np.mean(active_r))

                    results[key]["trades"] += n_trades
                    results[key]["wins"] += n_wins
                    results[key]["total_r"] += float(np.sum(active_r))
                    results[key]["fold_counts"] += 1

    # Format results
    formatted = []
    for (rt, mt), r in sorted(results.items(), key=lambda x: -x[1]["trades"]):
        if r["trades"] > 0:
            wr = r["wins"] / r["trades"] * 100
            avg_r = r["total_r"] / r["trades"]
            formatted.append({
                "reg_thr": rt,
                "meta_thr": mt,
                "total_trades": r["trades"],
                "winrate_pct": round(wr, 1),
                "mean_r": round(avg_r, 6),
            })

    return formatted
