"""Ensemble Agreement — multi-model ensemble for prediction robustness.

Trains N XGBoost classifiers with different random seeds, computes
agreement scores across the ensemble, and filters predictions by
minimum agreement threshold.

This implements ensemble agreement filtering (#10 in Milestone C):
  - Train N models with different random seeds
  - agreement_score() = fraction of models agreeing on direction
  - filter_by_agreement() = only keep predictions above threshold
  - Evaluation comparing single vs ensemble-filtered performance
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xgboost as xgb

from alphaforge.training.xgb_trainer import (
    SWING_DEFAULT_HYPERPARAMS,
    XGBoostTrainer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_N_MODELS: int = 5
"""Default number of models in the ensemble."""

DEFAULT_AGREEMENT_THRESHOLD: float = 0.6
"""Default minimum agreement fraction to accept a prediction."""

ENSEMBLE_SEED_OFFSET: int = 1000
"""Offset applied to consecutive random seeds for reproducibility."""


class EnsembleAgreement:
    """Ensemble of XGBoost models with agreement-based filtering.

    Trains N models using different random seeds. On inference,
    computes agreement scores and filters low-confidence predictions.

    Usage:
        ensemble = EnsembleAgreement(n_models=5, mode="SWING")
        ensemble.fit(X, y, feature_names=feature_names)
        preds, agreement = ensemble.predict(X)
        filtered = ensemble.filter_by_agreement(preds, agreement)
    """

    def __init__(
        self,
        n_models: int = DEFAULT_N_MODELS,
        mode: str = "SWING",
        random_seed: int = 42,
        hyperparameters: Optional[Dict[str, Any]] = None,
        agreement_threshold: float = DEFAULT_AGREEMENT_THRESHOLD,
    ):
        if n_models < 2:
            raise ValueError(f"n_models must be >= 2, got {n_models}")
        if not 0 <= agreement_threshold <= 1:
            raise ValueError(f"agreement_threshold must be in [0, 1], got {agreement_threshold}")

        self._n_models = n_models
        self._mode = mode
        self._base_seed = random_seed
        self._hyperparameters = hyperparameters or SWING_DEFAULT_HYPERPARAMS.copy()
        self._agreement_threshold = agreement_threshold
        self._models: List[xgb.Booster] = []
        self._trainers: List[XGBoostTrainer] = []
        self._feature_names: Optional[List[str]] = None

    @property
    def n_models(self) -> int:
        return self._n_models

    @property
    def models(self) -> List[xgb.Booster]:
        return list(self._models)

    @property
    def agreement_threshold(self) -> float:
        return self._agreement_threshold

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> List[Any]:
        """Train N XGBoost models with different random seeds.

        Args:
            X: Feature matrix, shape (n_samples, n_features).
            y: Label vector (string or int labels).
            feature_names: Optional list of feature names.

        Returns:
            List of TrainingResult objects, one per model.
        """
        self._models = []
        self._trainers = []
        self._feature_names = feature_names
        results: List[Any] = []

        for i in range(self._n_models):
            seed = self._base_seed + i * ENSEMBLE_SEED_OFFSET
            hp = dict(self._hyperparameters)
            hp["random_state"] = seed

            trainer = XGBoostTrainer(
                mode=self._mode,
                random_seed=seed,
                hyperparameters=hp,
            )
            result = trainer.train(X, y, feature_names=feature_names)
            self._models.append(result.model)
            self._trainers.append(trainer)
            results.append(result)

            logger.info(
                "Ensemble model %d/%d: seed=%d, val_acc=%.4f",
                i + 1, self._n_models, seed,
                result.val_metrics.get("accuracy", 0.0),
            )

        return results

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(
        self,
        X: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Predict with all ensemble models and compute agreement.

        Args:
            X: Feature matrix, shape (n_samples, n_features).

        Returns:
            (predictions, agreement_scores) where:
              predictions: Majority-vote class predictions, shape (n_samples,).
              agreement_scores: Fraction of models agreeing on the predicted
                  class, shape (n_samples,). Range [1/n_models, 1].
        """
        if not self._models:
            raise RuntimeError("Ensemble has not been fit yet. Call fit() first.")

        n_samples = len(X)
        dmat = xgb.DMatrix(X)
        if self._feature_names:
            dmat.feature_names = self._feature_names

        # Collect predictions from all models: (n_models, n_samples)
        all_preds = np.zeros((self._n_models, n_samples), dtype=np.int32)

        for i, model in enumerate(self._models):
            probas = model.predict(dmat)
            if probas.ndim == 1:
                probas = probas.reshape(-1, 3)
            all_preds[i, :] = np.argmax(probas, axis=1)

        # Majority vote per sample
        predictions = np.zeros(n_samples, dtype=np.int32)
        agreement_scores = np.zeros(n_samples, dtype=np.float64)

        for j in range(n_samples):
            votes = all_preds[:, j]
            unique, counts = np.unique(votes, return_counts=True)
            majority_idx = int(unique[np.argmax(counts)])
            predictions[j] = majority_idx
            agreement_scores[j] = float(np.max(counts)) / self._n_models

        return predictions, agreement_scores

    def predict_proba(
        self,
        X: np.ndarray,
    ) -> np.ndarray:
        """Predict class probabilities averaged across the ensemble.

        Args:
            X: Feature matrix, shape (n_samples, n_features).

        Returns:
            Average class probabilities, shape (n_samples, n_classes).
            Each row sums to 1.
        """
        if not self._models:
            raise RuntimeError("Ensemble has not been fit yet. Call fit() first.")

        dmat = xgb.DMatrix(X)
        if self._feature_names:
            dmat.feature_names = self._feature_names

        n_classes = 3
        sum_probas = np.zeros((len(X), n_classes), dtype=np.float64)

        for model in self._models:
            probas = model.predict(dmat)
            if probas.ndim == 1:
                probas = probas.reshape(-1, n_classes)
            sum_probas += probas

        avg_probas = sum_probas / self._n_models
        return avg_probas

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter_by_agreement(
        self,
        predictions: np.ndarray,
        agreement_scores: np.ndarray,
        threshold: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Filter predictions by minimum agreement threshold.

        Predictions with agreement below threshold are set to NO_TRADE (2).
        NO_TRADE predictions (class 2) are always kept as-is.

        Args:
            predictions: Class predictions, shape (n_samples,).
            agreement_scores: Agreement scores in [0, 1], shape (n_samples,).
            threshold: Minimum agreement. Defaults to instance threshold (0.6).

        Returns:
            (filtered_preds, kept_mask, agreement_scores) where:
              filtered_preds: predictions with low-agreement set to NO_TRADE.
              kept_mask: bool array, True where prediction was kept.
              agreement_scores: original agreement scores (unchanged).
        """
        threshold = threshold if threshold is not None else self._agreement_threshold

        # NO_TRADE (2) is always kept
        no_trade_mask = predictions == 2
        above_threshold = agreement_scores >= threshold

        kept_mask = np.where(no_trade_mask, True, above_threshold)
        filtered_preds = np.where(kept_mask, predictions, 2)

        n_kept = int(kept_mask.sum())
        n_filtered = len(predictions) - n_kept
        logger.info(
            "Ensemble filter: kept %d / %d predictions (threshold=%.2f)",
            n_kept, len(predictions), threshold,
        )

        return filtered_preds, kept_mask, agreement_scores

    def evaluate_filter_impact(
        self,
        X: np.ndarray,
        y_true: np.ndarray,
        threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Evaluate the impact of agreement filtering vs single-model baseline.

        Computes:
          - Single model accuracy (using first ensemble member)
          - Ensemble majority-vote accuracy (unfiltered)
          - Ensemble filtered accuracy (only predictions above threshold)
          - Trade reduction fraction
          - Accuracy improvement ratio

        Args:
            X: Feature matrix, shape (n_samples, n_features).
            y_true: Ground truth labels, shape (n_samples,).
            threshold: Agreement threshold. Defaults to instance value.

        Returns:
            Dict with keys:
              single_accuracy, ensemble_accuracy, filtered_accuracy,
              trade_fraction, trade_reduction, accuracy_gain,
              mean_agreement, std_agreement, n_models,
              threshold_used.
        """
        threshold = threshold if threshold is not None else self._agreement_threshold
        predictions, agreement_scores = self.predict(X)

        # Single model accuracy (first ensemble member)
        single_preds = self._predict_single(X, 0)
        single_accuracy = float(np.mean(single_preds == y_true))

        # Ensemble majority-vote accuracy
        ensemble_accuracy = float(np.mean(predictions == y_true))

        # Filtered accuracy
        filtered_preds, kept_mask, _ = self.filter_by_agreement(
            predictions, agreement_scores, threshold,
        )
        if kept_mask.sum() > 0:
            filtered_accuracy = float(np.mean(filtered_preds[kept_mask] == y_true[kept_mask]))
        else:
            filtered_accuracy = 0.0

        trade_fraction = float(kept_mask.sum()) / len(kept_mask)
        trade_reduction = 1.0 - trade_fraction
        accuracy_gain = filtered_accuracy - single_accuracy

        return {
            "single_accuracy": single_accuracy,
            "ensemble_accuracy": ensemble_accuracy,
            "filtered_accuracy": filtered_accuracy,
            "trade_fraction": trade_fraction,
            "trade_reduction": trade_reduction,
            "accuracy_gain": accuracy_gain,
            "mean_agreement": float(np.mean(agreement_scores)),
            "std_agreement": float(np.std(agreement_scores, ddof=1)),
            "n_models": self._n_models,
            "threshold_used": threshold,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _predict_single(
        self,
        X: np.ndarray,
        model_idx: int = 0,
    ) -> np.ndarray:
        """Predict using a single ensemble member.

        Args:
            X: Feature matrix, shape (n_samples, n_features).
            model_idx: Index into the ensemble (default 0).

        Returns:
            Class predictions, shape (n_samples,).
        """
        if model_idx >= len(self._models):
            raise IndexError(f"Model index {model_idx} out of range ({len(self._models)} models)")

        dmat = xgb.DMatrix(X)
        if self._feature_names:
            dmat.feature_names = self._feature_names

        probas = self._models[model_idx].predict(dmat)
        if probas.ndim == 1:
            probas = probas.reshape(-1, 3)
        return np.argmax(probas, axis=1).astype(np.int32)
