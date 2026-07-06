"""Meta-labeling configuration constants.

These control the two-stage meta-labeling behaviour:
  - Time-series split ratio for meta-label generation
  - Secondary XGBoost classifier hyperparameters
  - Default confidence threshold for trade filtering
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Time-series split
# ---------------------------------------------------------------------------

DEFAULT_TRAIN_RATIO: float = 0.7
"""Fraction of training data (first 70%) used to generate meta-labels.
Remaining 30% is used to train the meta-classifier."""

# ---------------------------------------------------------------------------
# Meta-classifier hyperparameters (heavy regularization)
# ---------------------------------------------------------------------------

META_N_ESTIMATORS: int = 100
"""Number of boosting rounds for the meta-classifier."""

META_LEARNING_RATE: float = 0.05
"""Learning rate for the meta XGBoost classifier."""

DEFAULT_META_DEPTH: int = 5
"""Maximum tree depth for the meta-classifier (default 5, per spec)."""

DEFAULT_META_REG_LAMBDA: float = 5.0
"""L2 regularization on leaf weights for the meta-classifier (default 5.0)."""

# ---------------------------------------------------------------------------
# Confidence / threshold
# ---------------------------------------------------------------------------

META_CONFIDENCE_DEFAULT_THRESHOLD: float = 0.5
"""Default confidence threshold: meta predicts 'trade' when probability > 0.5."""
