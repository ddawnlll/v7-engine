"""Hybrid regression→classification trainer.

Stage 1: Train XGBoost regression (reg:squarederror) on net_r
Stage 2: Add regression predictions as features, train XGBoost classifier (multi:softprob)

This gives the classifier access to the regression model's directional signal,
allowing it to learn when to trust (high confidence) vs ignore (NO_TRADE) the signal.
"""

from __future__ import annotations

import numpy as np
from alphaforge.training.xgb_trainer import XGBoostTrainer


class HybridTrainer:
    """Two-stage hybrid trainer: regression → classification."""

    def __init__(self, mode: str = "SCALP"):
        self.mode = mode
        self.reg_trainer = None
        self.clf_trainer = None
        self._reg_model = None
        self._clf_model = None

    def train(self, X: np.ndarray, y_class: np.ndarray, y_reg: np.ndarray):
        """Train hybrid model on given data.

        Args:
            X: Feature matrix (N, F).
            y_class: Classification labels (0=LONG, 1=SHORT, 2=NO_TRADE).
            y_reg: Regression targets (net_r values for each sample).
        """
        X = np.asarray(X, dtype=np.float64)
        y_class = np.asarray(y_class, dtype=np.int64)
        y_reg = np.asarray(y_reg, dtype=np.float64)

        # Stage 1: Train regression model
        self.reg_trainer = XGBoostTrainer(mode=self.mode, objective="reg:squarederror")
        reg_result = self.reg_trainer.train(X, y_reg)
        self._reg_model = reg_result.model

        # Predict on training data (including in-sample; calibrator uses held-out)
        reg_preds = np.asarray(self._reg_model.inplace_predict(X), dtype=np.float64).reshape(-1, 1)

        # Stage 2: Augment features with regression prediction
        X_aug = np.column_stack([X, reg_preds])

        # Train classifier on augmented features
        self.clf_trainer = XGBoostTrainer(mode=self.mode, objective="multi:softprob")
        clf_result = self.clf_trainer.train(X_aug, y_class)
        self._clf_model = clf_result.model

        return reg_result, clf_result

    def predict(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Predict using hybrid model.

        Returns:
            (reg_pred, clf_probs) where:
            - reg_pred: (N,) array of predicted returns
            - clf_probs: (N, 3) array of class probabilities
        """
        X = np.asarray(X, dtype=np.float64)
        reg_pred = np.asarray(self._reg_model.inplace_predict(X), dtype=np.float64)
        X_aug = np.column_stack([X, reg_pred.reshape(-1, 1)])
        clf_probs = np.asarray(self._clf_model.predict_proba(X_aug), dtype=np.float64)
        return reg_pred, clf_probs
