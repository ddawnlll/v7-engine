"""AlphaForge Training — model training and artifact packaging.

This package is the TRAINING environment. It imports xgboost and other
ML libraries. It must NOT be imported in the gate-check environment where
the ML pilot gate verifies that GBM is absent.

Modules:
    xgb_trainer: XGBoost classifier training for mode-specific alpha models.
"""

from alphaforge.training.xgb_trainer import (
    SWING_DEFAULT_HYPERPARAMS,
    XGBoostTrainer,
    train_swing_model,
)

__all__ = [
    "SWING_DEFAULT_HYPERPARAMS",
    "XGBoostTrainer",
    "train_swing_model",
]
