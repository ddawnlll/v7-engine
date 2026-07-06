"""MetaLabeler — two-stage meta-labeling for AlphaForge.

Generates meta-labels from a primary model's correctness on training data,
then trains a secondary XGBoost classifier to predict primary correctness.
Supports walk-forward cross-validation for robust evaluation.

Reference: Lopez de Prado, M. (2018). Advances in Financial Machine Learning.
Chapter 9: Meta-Labeling.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xgboost as xgb

from alphaforge.meta.config import (
    DEFAULT_META_DEPTH,
    DEFAULT_META_REG_LAMBDA,
    DEFAULT_TRAIN_RATIO,
    META_CONFIDENCE_DEFAULT_THRESHOLD,
    META_LEARNING_RATE,
    META_N_ESTIMATORS,
)

logger = logging.getLogger(__name__)


class MetaLabeler:
    """Two-stage meta-labeling wrapper.

    Usage:
        labeler = MetaLabeler()
        meta_model = labeler.fit(X, primary_preds, y_true)
        meta_probs = labeler.predict_meta_proba(X_meta)
        trades, confs = labeler.filter_trades(primary_preds, meta_probs)
    """

    def __init__(
        self,
        train_ratio: float = DEFAULT_TRAIN_RATIO,
        meta_depth: int = DEFAULT_META_DEPTH,
        meta_reg_lambda: float = DEFAULT_META_REG_LAMBDA,
        random_state: int = 42,
        confidence_threshold: float = META_CONFIDENCE_DEFAULT_THRESHOLD,
    ):
        if not 0 < train_ratio < 1:
            raise ValueError(f"train_ratio must be in (0, 1), got {train_ratio}")
        self._train_ratio = train_ratio
        self._meta_depth = meta_depth
        self._meta_reg_lambda = meta_reg_lambda
        self._random_state = random_state
        self._confidence_threshold = confidence_threshold
        self._meta_model: Optional[xgb.XGBClassifier] = None
        self._meta_feature_keys: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def meta_model(self) -> Optional[xgb.XGBClassifier]:
        return self._meta_model

    @property
    def confidence_threshold(self) -> float:
        return self._confidence_threshold

    # ------------------------------------------------------------------
    # Meta-label generation
    # ------------------------------------------------------------------

    def _generate_meta_labels(
        self,
        primary_preds: np.ndarray,
        y_true: np.ndarray,
    ) -> np.ndarray:
        """Generate binary meta-labels from primary model correctness.

        Meta-label = 1 if primary prediction matches true label, else 0.

        Args:
            primary_preds: Primary model predictions, shape (n_samples,).
            y_true: Ground truth labels, shape (n_samples,).

        Returns:
            Binary array of shape (n_samples,): 1 = correct, 0 = wrong.
        """
        return np.where(primary_preds == y_true, 1, 0).astype(np.int32)

    def _build_meta_features(
        self,
        X: np.ndarray,
        primary_preds: np.ndarray,
        primary_probas: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Build feature matrix for the meta-classifier.

        Augments the original feature set with primary model outputs:
          - Primary predicted class (one-hot encoded, 3 columns)
          - Primary confidence (max probability across classes)

        Args:
            X: Original feature matrix, shape (n_samples, n_features).
            primary_preds: Primary class predictions, shape (n_samples,).
            primary_probas: Primary class probabilities, shape (n_samples, n_classes).
                If None, confidence is approximated from one-hot encoding of preds.

        Returns:
            Augmented feature matrix, shape (n_samples, n_features + 4).
        """
        n = len(primary_preds)
        n_classes = 3

        # One-hot encode primary predictions
        one_hot = np.zeros((n, n_classes), dtype=np.float64)
        one_hot[np.arange(n), primary_preds.astype(int)] = 1.0

        # Primary confidence: max probability (or 1.0 if probas unavailable)
        if primary_probas is not None:
            confidence = np.max(primary_probas, axis=1)
        else:
            confidence = np.ones(n, dtype=np.float64)

        meta_features = np.column_stack([X, one_hot, confidence])
        return meta_features

    # ------------------------------------------------------------------
    # Fit
    # ------------------------------------------------------------------

    def fit(
        self,
        X: np.ndarray,
        primary_preds: np.ndarray,
        y_true: np.ndarray,
        primary_probas: Optional[np.ndarray] = None,
    ) -> xgb.XGBClassifier:
        """Fit the meta-classifier using time-series split.

        1. Generate meta-labels from primary correctness on full data.
        2. Split: first `train_ratio` fraction for meta-label generation,
           last `1 - train_ratio` for meta-classifier training.
        3. Build meta-features on the training split.
        4. Train binary XGBoost classifier on the training split.

        Args:
            X: Original feature matrix, shape (n_samples, n_features).
            primary_preds: Primary model predictions, shape (n_samples,).
            y_true: Ground truth labels, shape (n_samples,).
            primary_probas: Primary class probabilities (n_samples, n_classes).
                Used to compute primary confidence as a meta-feature.

        Returns:
            Trained XGBClassifier (binary:logistic).

        Raises:
            ValueError: If inputs are invalid or too few samples.
        """
        n = len(X)
        if n < 20:
            raise ValueError(
                f"Need at least 20 samples for meta-labeling, got {n}"
            )

        # Generate meta-labels
        meta_labels = self._generate_meta_labels(primary_preds, y_true)

        # Build meta-features on full data
        meta_features = self._build_meta_features(X, primary_preds, primary_probas)
        self._meta_feature_keys = [f"meta_f{i}" for i in range(meta_features.shape[1])]

        # Time-series split: first train_ratio for label gen, rest for meta training
        split_idx = int(n * self._train_ratio)
        split_idx = max(split_idx, 10)  # ensure at least 10 samples for meta training
        split_idx = min(split_idx, n - 10)

        # The meta-labeler's training set is the last (1 - train_ratio) portion
        X_meta_train = meta_features[split_idx:]
        y_meta_train = meta_labels[split_idx:]

        # Primary confidence is already embedded in meta_features,
        # per spec requirement: "Includes primary confidence as meta-feature"

        # Train binary XGBoost classifier
        model = xgb.XGBClassifier(
            objective="binary:logistic",
            n_estimators=META_N_ESTIMATORS,
            max_depth=self._meta_depth,
            learning_rate=META_LEARNING_RATE,
            reg_lambda=self._meta_reg_lambda,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=5,
            gamma=0.1,
            eval_metric="logloss",
            random_state=self._random_state,
            verbosity=0,
        )
        model.fit(X_meta_train, y_meta_train, verbose=False)

        self._meta_model = model

        n_correct = int(meta_labels.sum())
        n_wrong = n - n_correct
        logger.info(
            "MetaLabeler fit: %d samples (%.1f%% correct), "
            "split at %d (train_ratio=%.2f), "
            "meta train size=%d",
            n, 100.0 * n_correct / max(n, 1),
            split_idx, self._train_ratio,
            len(X_meta_train),
        )

        return model

    # ------------------------------------------------------------------
    # Walk-forward CV
    # ------------------------------------------------------------------

    def walk_forward_fit(
        self,
        X: np.ndarray,
        primary_preds: np.ndarray,
        y_true: np.ndarray,
        n_folds: int = 6,
        primary_probas: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Fit meta-classifiers across walk-forward folds.

        Each fold: train on past (expanding window), meta-label on adjacent
        validation window. Returns per-fold models and aggregated metrics.

        Args:
            X: Feature matrix, shape (n_samples, n_features).
            primary_preds: Primary predictions, shape (n_samples,).
            y_true: Ground truth labels, shape (n_samples,).
            n_folds: Number of walk-forward folds (default 6).
            primary_probas: Primary class probabilities (n_samples, n_classes).

        Returns:
            Dict with keys:
              models: List of trained XGBClassifier per fold.
              fold_meta_accuracy: List of per-fold meta accuracy.
              avg_meta_accuracy: Mean meta accuracy across folds.
              std_meta_accuracy: Std of meta accuracy across folds.
        """
        n = len(X)
        fold_size = n // n_folds
        if fold_size < 10:
            raise ValueError(
                f"Fold size too small ({fold_size}) for {n_folds} folds on {n} samples"
            )

        meta_features = self._build_meta_features(X, primary_preds, primary_probas)
        meta_labels = self._generate_meta_labels(primary_preds, y_true)

        models: List[xgb.XGBClassifier] = []
        fold_meta_acc: List[float] = []

        for fold_idx in range(n_folds):
            train_end = (fold_idx + 1) * fold_size
            val_start = train_end
            val_end = min(val_start + fold_size, n)

            if val_end - val_start < 10 or train_end < 10:
                continue

            X_fold_train = meta_features[:train_end]
            y_fold_train = meta_labels[:train_end]
            X_fold_val = meta_features[val_start:val_end]
            y_fold_val = meta_labels[val_start:val_end]

            model = xgb.XGBClassifier(
                objective="binary:logistic",
                n_estimators=META_N_ESTIMATORS,
                max_depth=self._meta_depth,
                learning_rate=META_LEARNING_RATE,
                reg_lambda=self._meta_reg_lambda,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=5,
                gamma=0.1,
                eval_metric="logloss",
                random_state=self._random_state + fold_idx,
                verbosity=0,
            )
            model.fit(X_fold_train, y_fold_train, verbose=False)

            val_preds = model.predict(X_fold_val)
            acc = float(np.mean(val_preds == y_fold_val))
            fold_meta_acc.append(acc)
            models.append(model)

            logger.info(
                "WFV fold %d: meta train=%d val=%d accuracy=%.4f",
                fold_idx, len(X_fold_train), len(X_fold_val), acc,
            )

        if not fold_meta_acc:
            raise RuntimeError("No walk-forward folds could be constructed")

        return {
            "models": models,
            "fold_meta_accuracy": fold_meta_acc,
            "avg_meta_accuracy": float(np.mean(fold_meta_acc)),
            "std_meta_accuracy": float(np.std(fold_meta_acc, ddof=1)) if len(fold_meta_acc) > 1 else 0.0,
        }

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict_meta_proba(
        self,
        X: np.ndarray,
        primary_preds: np.ndarray,
        primary_probas: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Predict meta-class probabilities for new data.

        Args:
            X: Original feature matrix, shape (n_samples, n_features).
            primary_preds: Primary predictions, shape (n_samples,).
            primary_probas: Primary class probabilities (n_samples, n_classes).

        Returns:
            Meta-class probabilities, shape (n_samples,).
            Probability that the primary prediction is correct.

        Raises:
            RuntimeError: If model has not been fit yet.
        """
        if self._meta_model is None:
            raise RuntimeError("MetaLabeler has not been fit yet. Call fit() first.")

        meta_features = self._build_meta_features(X, primary_preds, primary_probas)
        probas = self._meta_model.predict_proba(meta_features)
        # probas[:, 1] = probability of class 1 (correct prediction)
        return probas[:, 1]

    def filter_trades(
        self,
        primary_preds: np.ndarray,
        meta_probas: np.ndarray,
        threshold: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Filter primary predictions using meta confidence.

        A trade is accepted when meta confidence > threshold.
        NO_TRADE (class 2) is always passed through as NO_TRADE.

        Args:
            primary_preds: Primary model predictions, shape (n_samples,).
            meta_probas: Meta-class probabilities (n_samples,).
            threshold: Confidence threshold. Defaults to instance value.

        Returns:
            (trades, confidence) where:
              trades: bool array, True = accept the trade.
              confidence: float array, meta probability (0 if rejected).
        """
        threshold = threshold if threshold is not None else self._confidence_threshold

        # NO_TRADE (2) are always accepted as-is (no trade)
        no_trade_mask = primary_preds == 2
        meta_above_threshold = meta_probas > threshold

        trades = np.where(no_trade_mask, True, meta_above_threshold)
        confidence = np.where(trades, meta_probas, 0.0)

        return trades, confidence

    def predict_with_filter(
        self,
        X: np.ndarray,
        primary_preds: np.ndarray,
        primary_probas: Optional[np.ndarray] = None,
        threshold: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Full inference: predict meta probs, filter trades.

        Args:
            X: Feature matrix, shape (n_samples, n_features).
            primary_preds: Primary predictions, shape (n_samples,).
            primary_probas: Primary class probabilities (n_samples, n_classes).
            threshold: Confidence threshold.

        Returns:
            (trades, confidence, final_preds) where:
              trades: bool array, True = accept trade.
              confidence: meta probability (0 if rejected).
              final_preds: primary predictions with rejected ones set to NO_TRADE (2).
        """
        meta_probas = self.predict_meta_proba(X, primary_preds, primary_probas)
        trades, confidence = self.filter_trades(primary_preds, meta_probas, threshold)

        final_preds = primary_preds.copy()
        final_preds[~trades] = 2  # NO_TRADE

        return trades, confidence, final_preds
