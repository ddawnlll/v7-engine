"""AlphaForge Feature Pipeline — deterministic causal feature computation.

Exports:
    FeatureMatrix  — structured container for feature arrays
    compute_features — main pipeline entry point
    FeatureGroup    — enumeration of feature groups (LEAD_LAG DEFERRED)
    FEATURE_GROUP_MAP — mapping from FeatureGroup to compute function names
    PIPELINE_VERSION — semantic version of the pipeline implementation
    OrderBook group — microstructure-aware features (AGGRESSIVE_SCALP primary)
    LeadLag group — cross-sectional multi-symbol features
    ModeWindowConfig — per-mode window parameter configuration
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
    AGGRESSIVE_NOISE_WINDOW,
    AGGRESSIVE_PERIODS_PER_YEAR,
    AGGRESSIVE_PRICE_IMPACT_WINDOW,
    AGGRESSIVE_ROLL_SPREAD_WINDOW,
    AGGRESSIVE_SERIAL_CORR_WINDOW,
    AGGRESSIVE_SPREAD_WINDOW,
    AGGRESSIVE_VPIN_WINDOW,
    DEFAULT_AMIHUD_WINDOW,
    DEFAULT_NOISE_WINDOW,
    DEFAULT_ORDERBOOK_WINDOW,
    DEFAULT_PRICE_IMPACT_WINDOW,
    DEFAULT_ROLL_SPREAD_WINDOW,
    DEFAULT_SERIAL_CORR_WINDOW,
    DEFAULT_VPIN_WINDOW,
    compute_amihud_illiquidity_numpy,
    compute_microstructure_noise,
    compute_orderbook_group,
    compute_price_impact_slope,
    compute_roll_spread,
    compute_serial_correlation,
    compute_spread_pct,
    compute_trade_intensity,
    compute_volume_imbalance,
    compute_vpin,
)

# LeadLag cross-sectional features (HOLD-LEAD-LAG)
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

# Per-mode feature window configuration
from alphaforge.features.mode_windows import (
    AGGRESSIVE_SCALP_WINDOWS,
    SCALP_WINDOWS,
    SWING_WINDOWS,
    ModeWindowConfig,
    get_all_mode_windows,
    get_mode_windows,
)

__version__ = "0.3.0"
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
    "compute_roll_spread",
    "compute_microstructure_noise",
    "compute_serial_correlation",
    "compute_vpin",
    "compute_price_impact_slope",
    "DEFAULT_ORDERBOOK_WINDOW",
    "DEFAULT_AMIHUD_WINDOW",
    "DEFAULT_ROLL_SPREAD_WINDOW",
    "DEFAULT_NOISE_WINDOW",
    "DEFAULT_SERIAL_CORR_WINDOW",
    "DEFAULT_VPIN_WINDOW",
    "DEFAULT_PRICE_IMPACT_WINDOW",
    "AGGRESSIVE_SPREAD_WINDOW",
    "AGGRESSIVE_IMBALANCE_WINDOW",
    "AGGRESSIVE_INTENSITY_WINDOW",
    "AGGRESSIVE_AMIHUD_WINDOW",
    "AGGRESSIVE_ROLL_SPREAD_WINDOW",
    "AGGRESSIVE_NOISE_WINDOW",
    "AGGRESSIVE_SERIAL_CORR_WINDOW",
    "AGGRESSIVE_VPIN_WINDOW",
    "AGGRESSIVE_PRICE_IMPACT_WINDOW",
    "AGGRESSIVE_PERIODS_PER_YEAR",
    # LeadLag group (cross-sectional, HOLD-LEAD-LAG)
    "LL_CORRELATION_WINDOW",
    "LL_MAX_LAG",
    "LL_MIN_VALID",
    "LL_PERIODS_PER_YEAR",
    "LL_VOLATILITY_WINDOW",
    "compute_correlation_pairwise",
    "compute_lead_lag_group",
    "compute_lead_lag_score",
    "compute_tf_alignment",
    # Mode window config (per-mode feature window parameters)
    "ModeWindowConfig",
    "SWING_WINDOWS",
    "SCALP_WINDOWS",
    "AGGRESSIVE_SCALP_WINDOWS",
    "get_mode_windows",
    "get_all_mode_windows",
]
