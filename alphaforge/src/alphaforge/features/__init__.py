"""AlphaForge Feature Pipeline — deterministic causal feature computation.

Exports:
    FeatureMatrix  — structured container for feature arrays
    compute_features — main pipeline entry point
    FeatureGroup    — enumeration of feature groups (LEAD_LAG implemented, wiring DEFERRED)
    FEATURE_GROUP_MAP — mapping from FeatureGroup to compute function names
    PIPELINE_VERSION — semantic version of the pipeline implementation
    compute_lead_lag_group — Lead-Lag cross-sectional group compute (HOLD-LEAD-LAG)
"""

from alphaforge.features.pipeline import (
    PIPELINE_VERSION,
    FEATURE_GROUP_MAP,
    FeatureGroup,
    FeatureMatrix,
    compute_features,
)

# Lead-Lag cross-sectional features (implemented, wiring DEFERRED — P0.9B)
from alphaforge.features.lead_lag import (
    LL_CORRELATION_WINDOW,
    LL_MAX_LAG,
    LL_MIN_VALID,
    LL_PERIODS_PER_YEAR,
    LL_VOLATILITY_WINDOW,
    compute_correlation_pairwise,
    compute_lead_lag_group,
    compute_lead_lag_score,
    compute_tf_alignment,
)

__version__ = "0.2.0"
__authority__ = "alphaforge"
__domain__ = "feature_pipeline"

__all__ = [
    "FeatureMatrix",
    "compute_features",
    "FeatureGroup",
    "FEATURE_GROUP_MAP",
    "PIPELINE_VERSION",
    # Lead-Lag cross-sectional features (HOLD-LEAD-LAG)
    "compute_lead_lag_group",
    "compute_tf_alignment",
    "compute_correlation_pairwise",
    "compute_lead_lag_score",
    "LL_CORRELATION_WINDOW",
    "LL_MAX_LAG",
    "LL_MIN_VALID",
    "LL_PERIODS_PER_YEAR",
    "LL_VOLATILITY_WINDOW",
]
