"""AlphaForge Meta-Labeling — two-stage prediction with confidence filtering.

Meta-labeling implements Lopez de Prado (2018) Chapter 9 approach:
Stage 1: Primary model predicts action (LONG_NOW/SHORT_NOW/NO_TRADE).
Stage 2: Meta-model predicts whether the primary prediction will succeed.

Only primary predictions with sufficient meta-confidence are passed through.
"""

from alphaforge.meta.config import (
    DEFAULT_EMBARGO_BARS,
    DEFAULT_PURGE_BARS,
    DEFAULT_THRESHOLD_GRID,
    DEFAULT_TRUST_MIN_THRESHOLD,
    TARGET_DAILY_TRADES,

    DEFAULT_META_DEPTH,
    DEFAULT_META_REG_LAMBDA,
    DEFAULT_TRAIN_RATIO,
    META_CONFIDENCE_DEFAULT_THRESHOLD,
    META_N_ESTIMATORS,
    META_LEARNING_RATE,
)
from alphaforge.meta.meta_labeler import MetaLabeler, compute_trust_scores
from alphaforge.meta.meta_filter import MetaFilter, meta_filter_predictions

__all__ = [
    "DEFAULT_META_DEPTH",
    "DEFAULT_META_REG_LAMBDA",
    "DEFAULT_TRAIN_RATIO",
    "META_CONFIDENCE_DEFAULT_THRESHOLD",
    "META_N_ESTIMATORS",
    "META_LEARNING_RATE",
    "MetaLabeler",
    "MetaFilter",
    "meta_filter_predictions",
    "compute_trust_scores",
    "DEFAULT_PURGE_BARS",
    "DEFAULT_EMBARGO_BARS",
    "DEFAULT_THRESHOLD_GRID",
    "DEFAULT_TRUST_MIN_THRESHOLD",
    "TARGET_DAILY_TRADES",
]
