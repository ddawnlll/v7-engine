"""
XGBoost model trainer for AlphaForge — hybrid classification + regression.

Trains per-mode model bundles:
- action_classifier: multi-class (LONG_NOW / SHORT_NOW / NO_TRADE)
- long_expected_R_regressor: expected net R for long entries
- short_expected_R_regressor: expected net R for short entries

Supports walk-forward training across dataset folds.
"""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
import xgboost as xgb

from alphaforge.errors import AlphaForgeError


TARGET_VERSION = "v7_alphaforge_xgb_v1"
CLASS_LABELS = ["LONG_NOW", "SHORT_NOW", "NO_TRADE"]


def _label_to_idx(label: str) -> int:
    try:
        return CLASS_LABELS.index(label)
    except ValueError:
        return 2  # NO_TRADE as default


def _dicts_to_arrays(
    rows: list[dict[str, Any]],
    feature_keys: list[str],
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None, np.ndarray | None]:
    """Convert merged training rows to numpy arrays.

    Args:
        rows: List of merged feature+label rows.
        feature_keys: Ordered list of feature column names.

    Returns:
        (X, y_class, y_long, y_short) where:
        - X: feature matrix
        - y_class: classification targets or None
        - y_long: LONG regression targets or None
        - y_short: SHORT regression targets or None
    """
    n = len(rows)
    if n == 0:
        return np.empty((0, len(feature_keys))), None, None, None

    X = np.zeros((n, len(feature_keys)), dtype=np.float64)
    y_class = np.full(n, 2, dtype=np.int32)  # default NO_TRADE
    y_long = np.zeros(n, dtype=np.float64)
    y_short = np.zeros(n, dtype=np.float64)

    for i, row in enumerate(rows):
        for j, key in enumerate(feature_keys):
            X[i, j] = float(row.get("features", {}).get(key, 0.0))
        label = row.get("label", {})
        y_class[i] = _label_to_idx(str(label.get("best_action_label", "NO_TRADE")))
        y_long[i] = float(label.get("long_R_net", 0.0))
        y_short[i] = float(label.get("short_R_net", 0.0))

    return X, y_class, y_long, y_short


def _build_model_artifact(
    model: xgb.XGBModel,
    model_type: str,
    mode: str,
    fold_id: str,
    feature_keys: list[str],
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Package a trained model into a versioned artifact dict."""
    return {
        "model_id": f"{TARGET_VERSION}_{mode.lower()}_{model_type}_{fold_id}",
        "artifact_version": TARGET_VERSION,
        "model_type": model_type,
        "mode": mode,
        "fold_id": fold_id,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_keys": feature_keys,
        "metrics": metrics or {},
    }


class ModelTrainer:
    """Trains XGBoost hybrid model bundles per mode.

    Usage:
        trainer = ModelTrainer()
        bundle = trainer.train_fold(train_rows, val_rows, feature_keys, mode="SWING")
    """

    def __init__(self, **default_params):
        self.default_params = {
            "classifier": {
                "n_estimators": 200,
                "max_depth": 6,
                "learning_rate": 0.1,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "random_state": 42,
                "eval_metric": "mlogloss",
                "early_stopping_rounds": 20,
                **default_params.get("classifier", {}),
            },
            "regressor": {
                "n_estimators": 200,
                "max_depth": 5,
                "learning_rate": 0.08,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "random_state": 42,
                "eval_metric": "rmse",
                "early_stopping_rounds": 20,
                **default_params.get("regressor", {}),
            },
        }

    def _train_classifier(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
    ) -> tuple[xgb.XGBClassifier, dict[str, Any]]:
        """Train multi-class action classifier."""
        params = dict(self.default_params["classifier"])
        eval_set = None
        if X_val is not None and y_val is not None and len(X_val) > 0:
            eval_set = [(X_val, y_val)]
        else:
            params.pop("early_stopping_rounds", None)  # not needed without eval_set

        model = xgb.XGBClassifier(
            objective="multi:softprob",
            num_class=3,
            n_estimators=params.pop("n_estimators", 200),
            max_depth=params.pop("max_depth", 6),
            learning_rate=params.pop("learning_rate", 0.1),
            subsample=params.pop("subsample", 0.8),
            colsample_bytree=params.pop("colsample_bytree", 0.8),
            random_state=params.pop("random_state", 42),
            eval_metric=params.pop("eval_metric", "mlogloss"),
            early_stopping_rounds=params.pop("early_stopping_rounds", None),
            **params,
        )
        model.fit(
            X_train, y_train,
            eval_set=eval_set,
            verbose=False,
        )

        metrics = {}
        if X_val is not None and y_val is not None and len(y_val) > 0:
            y_pred = model.predict(X_val)
            accuracy = float(np.mean(y_pred == y_val))
            metrics["val_accuracy"] = round(accuracy, 4)

        return model, metrics

    def _train_regressor(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
    ) -> tuple[xgb.XGBRegressor, dict[str, Any]]:
        """Train expected-R regressor."""
        params = dict(self.default_params["regressor"])

        has_val = X_val is not None and y_val is not None and len(y_val) > 0
        eval_set = [(X_val, y_val)] if has_val else None
        if not has_val:
            params.pop("early_stopping_rounds", None)

        model = xgb.XGBRegressor(
            objective="reg:squarederror",
            n_estimators=params.pop("n_estimators", 200),
            max_depth=params.pop("max_depth", 5),
            learning_rate=params.pop("learning_rate", 0.08),
            subsample=params.pop("subsample", 0.8),
            colsample_bytree=params.pop("colsample_bytree", 0.8),
            random_state=params.pop("random_state", 42),
            eval_metric=params.pop("eval_metric", "rmse"),
            early_stopping_rounds=params.pop("early_stopping_rounds", None),
            **params,
        )
        model.fit(
            X_train, y_train,
            eval_set=eval_set,
            verbose=False,
        )

        metrics = {}
        if has_val:
            y_pred = model.predict(X_val)
            mse = float(np.mean((y_pred - y_val) ** 2))
            rmse = round(float(np.sqrt(mse)), 4)
            metrics["val_rmse"] = rmse

        return model, metrics

    def train_fold(
        self,
        train_rows: list[dict[str, Any]],
        val_rows: list[dict[str, Any]],
        feature_keys: list[str],
        mode: str = "SWING",
        fold_id: str = "fold_0",
    ) -> dict[str, Any]:
        """Train a full model bundle for one walk-forward fold.

        Args:
            train_rows: Training set merged rows.
            val_rows: Validation set merged rows.
            feature_keys: Ordered feature column names.
            mode: Trading mode name.
            fold_id: Fold identifier.

        Returns:
            Model bundle dict with classifier, regressors, and artifacts.
        """
        if len(train_rows) < 10:
            raise AlphaForgeError(
                f"Not enough training rows: {len(train_rows)} (need >= 10)"
            )

        X_train, y_class_train, y_long_train, y_short_train = _dicts_to_arrays(
            train_rows, feature_keys
        )
        X_val, y_class_val, y_long_val, y_short_val = _dicts_to_arrays(
            val_rows, feature_keys
        )

        # Train classifier
        clf, clf_metrics = self._train_classifier(
            X_train, y_class_train,
            X_val if y_class_val is not None else None,
            y_class_val,
        )

        # Train long regressor
        long_mask = y_long_train != 0
        if long_mask.sum() > 0:
            long_reg, long_metrics = self._train_regressor(
                X_train[long_mask], y_long_train[long_mask],
                X_val[y_long_val != 0] if y_long_val is not None else None,
                y_long_val[y_long_val != 0] if y_long_val is not None else None,
            )
        else:
            long_reg, long_metrics = None, {}

        # Train short regressor
        short_mask = y_short_train != 0
        if short_mask.sum() > 0:
            short_reg, short_metrics = self._train_regressor(
                X_train[short_mask], y_short_train[short_mask],
                X_val[y_short_val != 0] if y_short_val is not None else None,
                y_short_val[y_short_val != 0] if y_short_val is not None else None,
            )
        else:
            short_reg, short_metrics = None, {}

        return {
            "classifier": {
                "model": clf,
                "artifact": _build_model_artifact(
                    clf, "action_classifier", mode, fold_id, feature_keys, clf_metrics
                ),
            },
            "long_regressor": {
                "model": long_reg,
                "artifact": _build_model_artifact(
                    long_reg, "expected_r_long_regressor", mode, fold_id, feature_keys, long_metrics
                ) if long_reg else None,
            },
            "short_regressor": {
                "model": short_reg,
                "artifact": _build_model_artifact(
                    short_reg, "expected_r_short_regressor", mode, fold_id, feature_keys, short_metrics
                ) if short_reg else None,
            },
            "metadata": {
                "mode": mode,
                "fold_id": fold_id,
                "num_train": len(train_rows),
                "num_val": len(val_rows),
                "num_features": len(feature_keys),
                "feature_keys": feature_keys,
            },
        }

    def train_from_dataset(
        self,
        dataset: dict[str, Any],
        mode: str,
    ) -> list[dict[str, Any]]:
        """Train across all folds in a dataset.

        Args:
            dataset: Output from dataset.builder.build_dataset.
            mode: Mode name.

        Returns:
            List of fold model bundles.
        """
        # Implementation requires the actual train/val row splits from the dataset.
        # The current dataset builder only stores counts, not the actual split rows.
        # This method is a placeholder for when the dataset builder provides row access.
        raise NotImplementedError(
            "train_from_dataset requires row-level fold access from the dataset builder. "
            "Implement after dataset builder exposes train_rows/val_rows."
        )
