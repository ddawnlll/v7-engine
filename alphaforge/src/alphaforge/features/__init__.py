"""AlphaForge Feature Pipeline — deterministic causal feature computation.

Exports:
    FeatureMatrix  — structured container for feature arrays
    compute_features — main pipeline entry point
    FeatureGroup    — enumeration of feature groups (LEAD_LAG DEFERRED)
    FEATURE_GROUP_MAP — mapping from FeatureGroup to compute function names
    PIPELINE_VERSION — semantic version of the pipeline implementation
    OrderBook group — microstructure-aware features (AGGRESSIVE_SCALP primary)
"""

from alphaforge.features.pipeline import (
    PIPELINE_VERSION,
    FEATURE_GROUP_MAP,
    FeatureGroup,
    FeatureMatrix,
    compute_features,
)

# OrderBook microstructure features (AGGRESSIVE_SCALP primary, all modes supported)
from alphaforge.features.orderbook import (
    AGGRESSIVE_AMIHUD_WINDOW,
    AGGRESSIVE_IMBALANCE_WINDOW,
    AGGRESSIVE_INTENSITY_WINDOW,
    AGGRESSIVE_PERIODS_PER_YEAR,
    AGGRESSIVE_SPREAD_WINDOW,
    DEFAULT_AMIHUD_WINDOW,
    DEFAULT_ORDERBOOK_WINDOW,
    compute_amihud_illiquidity_numpy,
    compute_orderbook_group,
    compute_spread_pct,
    compute_trade_intensity,
    compute_volume_imbalance,
)

__version__ = "0.2.1"
__authority__ = "alphaforge"
__domain__ = "feature_pipeline"

__all__ = [
    "FeatureMatrix",
    "compute_features",
    "FeatureGroup",
    "FEATURE_GROUP_MAP",
    "PIPELINE_VERSION",
    # OrderBook group (microstructure proxies, AGGRESSIVE_SCALP primary)
    "compute_orderbook_group",
    "compute_spread_pct",
    "compute_volume_imbalance",
    "compute_trade_intensity",
    "compute_amihud_illiquidity_numpy",
    "DEFAULT_ORDERBOOK_WINDOW",
    "DEFAULT_AMIHUD_WINDOW",
    "AGGRESSIVE_SPREAD_WINDOW",
    "AGGRESSIVE_IMBALANCE_WINDOW",
    "AGGRESSIVE_INTENSITY_WINDOW",
    "AGGRESSIVE_AMIHUD_WINDOW",
    "AGGRESSIVE_PERIODS_PER_YEAR",
]
