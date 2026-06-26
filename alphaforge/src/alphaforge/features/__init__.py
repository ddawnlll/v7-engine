"""AlphaForge Feature Pipeline — deterministic causal feature computation.

Exports:
    FeatureMatrix    — structured container for feature arrays
    compute_features — main pipeline entry point
    FeatureGroup     — enumeration of feature groups (LEAD_LAG DEFERRED)
    FEATURE_GROUP_MAP — mapping from FeatureGroup to compute function names
    PIPELINE_VERSION — semantic version of the pipeline implementation
    ModeWindowConfig — per-mode feature window configuration (frozen)
    get_mode_windows — convenience accessor for mode window configs
"""

from alphaforge.features.pipeline import (
    PIPELINE_VERSION,
    FEATURE_GROUP_MAP,
    FeatureGroup,
    FeatureMatrix,
    compute_features,
)

from alphaforge.features.mode_windows import (
    ModeWindowConfig,
    SWING_WINDOWS,
    SCALP_WINDOWS,
    AGGRESSIVE_SCALP_WINDOWS,
    get_mode_windows,
    get_all_mode_windows,
)

__version__ = "0.1.0"
__authority__ = "alphaforge"
__domain__ = "feature_pipeline"

__all__ = [
    "FeatureMatrix",
    "compute_features",
    "FeatureGroup",
    "FEATURE_GROUP_MAP",
    "PIPELINE_VERSION",
    "ModeWindowConfig",
    "SWING_WINDOWS",
    "SCALP_WINDOWS",
    "AGGRESSIVE_SCALP_WINDOWS",
    "get_mode_windows",
    "get_all_mode_windows",
]
