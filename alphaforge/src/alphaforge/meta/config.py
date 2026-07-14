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

# ---------------------------------------------------------------------------
# Purged walk-forward cross-validation
# ---------------------------------------------------------------------------

DEFAULT_PURGE_BARS: int = 12
"""Number of bars to purge between train and validation folds.
Prevents label leakage when labels use a forward-looking window."""

DEFAULT_EMBARGO_BARS: int = 12
"""Number of embargo bars after purge.
Adds additional buffer to prevent indirect leakage."""

# ---------------------------------------------------------------------------
# Threshold sweep
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLD_GRID: list[float] = [0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
"""Default grid of confidence thresholds to sweep."""

# ---------------------------------------------------------------------------
# Trust score
# ---------------------------------------------------------------------------

DEFAULT_TRUST_MIN_THRESHOLD: float = 0.4
"""Minimum trust score to consider a trade."""

TARGET_DAILY_TRADES: tuple[float, float] = (3.0, 12.0)
"""Target range for daily active trades. Used to optimize threshold."""
