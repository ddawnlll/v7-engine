"""AlphaForge Feature Pipeline — deterministic causal feature computation.

Exports:
    FeatureMatrix  — structured container for feature arrays
    compute_features — main pipeline entry point
    FeatureCache   — Parquet+Zstd disk cache for feature matrices
    cached_compute_features — caching wrapper around compute_features
    FeatureGroup    — enumeration of feature groups (LEAD_LAG DEFERRED)
    FEATURE_GROUP_MAP — mapping from FeatureGroup to compute function names
    PIPELINE_VERSION — semantic version of the pipeline implementation
    CACHE_DIR_DEFAULT — default cache directory path
    OrderBook group — microstructure-aware features (AGGRESSIVE_SCALP primary)
    LeadLag group — cross-sectional multi-symbol features
    Funding group — funding rate and OI proxy features
    ModeWindowConfig — per-mode window parameter configuration
"""

from alphaforge.features.pipeline import (
    CACHE_DIR_DEFAULT,
    FEATURE_GROUP_MAP,
    FeatureCache,
    FeatureGroup,
    FeatureMatrix,
    PIPELINE_VERSION,
    cached_compute_features,
    compute_features,
    compute_time_features_group,
)

# OrderBook microstructure features (AGGRESSIVE_SCALP primary, all modes supported)
from alphaforge.features.orderbook import (
    AGGRESSIVE_AMIHUD_WINDOW,
    AGGRESSIVE_DEPTH_RATIO_WINDOW,
    AGGRESSIVE_IMBALANCE_WINDOW,
    AGGRESSIVE_INTENSITY_WINDOW,
    AGGRESSIVE_LIQUIDITY_VACUUM_WINDOW,
    AGGRESSIVE_MICROPRICE_WINDOW,
    AGGRESSIVE_NOISE_WINDOW,
    AGGRESSIVE_PERIODS_PER_YEAR,
    AGGRESSIVE_PRICE_IMPACT_WINDOW,
    AGGRESSIVE_ROLL_SPREAD_WINDOW,
    AGGRESSIVE_SERIAL_CORR_WINDOW,
    AGGRESSIVE_SPREAD_WINDOW,
    AGGRESSIVE_VPIN_WINDOW,
    DEFAULT_AMIHUD_WINDOW,
    DEFAULT_DEPTH_RATIO_WINDOW,
    DEFAULT_LIQUIDITY_VACUUM_WINDOW,
    DEFAULT_MICROPRICE_WINDOW,
    DEFAULT_NOISE_WINDOW,
    DEFAULT_ORDERBOOK_WINDOW,
    DEFAULT_PRICE_IMPACT_WINDOW,
    DEFAULT_ROLL_SPREAD_WINDOW,
    DEFAULT_SERIAL_CORR_WINDOW,
    DEFAULT_VPIN_WINDOW,
    compute_amihud_illiquidity_numpy,
    compute_depth_ratio,
    compute_liquidity_vacuum,
    compute_microprice,
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
    SCALP_LL_CORRELATION_WINDOW,
    SCALP_LL_MAX_LAG,
    SCALP_LL_PERIODS_PER_YEAR,
    SCALP_LL_VOLATILITY_WINDOW,
    compute_cluster_rotation,
    compute_correlation_pairwise,
    compute_lead_lag_group,
    compute_lead_lag_score,
    compute_relative_strength,
    compute_tf_alignment,
)

# Funding rate and OI proxy features
from alphaforge.features.funding import (
    AGGRESSIVE_SCALP_FUNDING_WINDOW,
    AGGRESSIVE_SCALP_OI_PROXY_WINDOW,
    DEFAULT_FUNDING_WINDOW,
    DEFAULT_OI_PROXY_WINDOW,
    SCALP_FUNDING_WINDOW,
    SCALP_OI_PROXY_WINDOW,
    SWING_FUNDING_WINDOW,
    SWING_OI_PROXY_WINDOW,
    compute_funding_group,
    compute_funding_oi_divergence,
    compute_funding_rate,
    compute_funding_rate_ma,
    compute_funding_rate_volatility,
    compute_funding_rate_zscore,
    compute_open_interest_proxy,
)

# Open Interest features (#280)
from alphaforge.features.open_interest import (
    AGGRESSIVE_SCALP_OI_WINDOW,
    DEFAULT_OI_WINDOW,
    SCALP_OI_WINDOW,
    SWING_OI_WINDOW,
    compute_open_interest_change,
    compute_open_interest_change_pct,
    compute_open_interest_group,
    compute_open_interest_volume_ratio,
    compute_open_interest_zscore,
)

# Premium Index features (#280)
from alphaforge.features.premium_index import (
    AGGRESSIVE_SCALP_BASIS_WINDOW,
    DEFAULT_BASIS_REGIME_THRESHOLD_BPS,
    DEFAULT_BASIS_WINDOW,
    SCALP_BASIS_WINDOW,
    SWING_BASIS_WINDOW,
    compute_basis,
    compute_basis_ma,
    compute_basis_regime,
    compute_basis_vol,
    compute_basis_zscore,
    compute_premium_index_group,
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

# Residual momentum / clustering features (Milestone C)
from alphaforge.features.residual_momentum import (
    compute_beta,
    compute_residual_momentum,
    cluster_symbols,
    compute_cross_sectional_momentum,
    compute_residual_momentum_group,
)

__version__ = "0.3.0"
__authority__ = "alphaforge"
__domain__ = "feature_pipeline"

__all__ = [
    "FeatureMatrix",
    "FeatureCache",
    "cached_compute_features",
    "compute_features",
    "FeatureGroup",
    "FEATURE_GROUP_MAP",
    "PIPELINE_VERSION",
    "CACHE_DIR_DEFAULT",
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
    "compute_microprice",
    "compute_liquidity_vacuum",
    "compute_depth_ratio",
    "DEFAULT_ORDERBOOK_WINDOW",
    "DEFAULT_AMIHUD_WINDOW",
    "DEFAULT_ROLL_SPREAD_WINDOW",
    "DEFAULT_NOISE_WINDOW",
    "DEFAULT_SERIAL_CORR_WINDOW",
    "DEFAULT_VPIN_WINDOW",
    "DEFAULT_PRICE_IMPACT_WINDOW",
    "DEFAULT_MICROPRICE_WINDOW",
    "DEFAULT_LIQUIDITY_VACUUM_WINDOW",
    "DEFAULT_DEPTH_RATIO_WINDOW",
    "AGGRESSIVE_SPREAD_WINDOW",
    "AGGRESSIVE_IMBALANCE_WINDOW",
    "AGGRESSIVE_INTENSITY_WINDOW",
    "AGGRESSIVE_AMIHUD_WINDOW",
    "AGGRESSIVE_ROLL_SPREAD_WINDOW",
    "AGGRESSIVE_NOISE_WINDOW",
    "AGGRESSIVE_SERIAL_CORR_WINDOW",
    "AGGRESSIVE_VPIN_WINDOW",
    "AGGRESSIVE_PRICE_IMPACT_WINDOW",
    "AGGRESSIVE_MICROPRICE_WINDOW",
    "AGGRESSIVE_LIQUIDITY_VACUUM_WINDOW",
    "AGGRESSIVE_DEPTH_RATIO_WINDOW",
    "AGGRESSIVE_PERIODS_PER_YEAR",
    # LeadLag group (cross-sectional, HOLD-LEAD-LAG)
    "LL_CORRELATION_WINDOW",
    "LL_MAX_LAG",
    "LL_MIN_VALID",
    "LL_PERIODS_PER_YEAR",
    "LL_VOLATILITY_WINDOW",
    "SCALP_LL_CORRELATION_WINDOW",
    "SCALP_LL_MAX_LAG",
    "SCALP_LL_VOLATILITY_WINDOW",
    "SCALP_LL_PERIODS_PER_YEAR",
    "compute_correlation_pairwise",
    "compute_lead_lag_group",
    "compute_lead_lag_score",
    "compute_tf_alignment",
    "compute_relative_strength",
    "compute_cluster_rotation",
    # Funding group (funding rate and OI proxy)
    "compute_funding_group",
    "compute_funding_rate",
    "compute_funding_rate_ma",
    "compute_funding_rate_volatility",
    "compute_funding_rate_zscore",
    "compute_open_interest_proxy",
    "compute_funding_oi_divergence",
    "DEFAULT_FUNDING_WINDOW",
    "DEFAULT_OI_PROXY_WINDOW",
    "SWING_FUNDING_WINDOW",
    "SCALP_FUNDING_WINDOW",
    "AGGRESSIVE_SCALP_FUNDING_WINDOW",
    "SWING_OI_PROXY_WINDOW",
    "SCALP_OI_PROXY_WINDOW",
    "AGGRESSIVE_SCALP_OI_PROXY_WINDOW",
    # Mode window config (per-mode feature window parameters)
    "ModeWindowConfig",
    "SWING_WINDOWS",
    "SCALP_WINDOWS",
    "AGGRESSIVE_SCALP_WINDOWS",
    "get_mode_windows",
    "get_all_mode_windows",
    # Open Interest features (Real OI data, #280)
    "compute_open_interest_group",
    "compute_open_interest_change",
    "compute_open_interest_change_pct",
    "compute_open_interest_volume_ratio",
    "compute_open_interest_zscore",
    "DEFAULT_OI_WINDOW",
    "SWING_OI_WINDOW",
    "SCALP_OI_WINDOW",
    "AGGRESSIVE_SCALP_OI_WINDOW",
    # Premium Index features (Real premium index data, #280)
    "compute_premium_index_group",
    "compute_basis",
    "compute_basis_ma",
    "compute_basis_vol",
    "compute_basis_zscore",
    "compute_basis_regime",
    "DEFAULT_BASIS_WINDOW",
    "DEFAULT_BASIS_REGIME_THRESHOLD_BPS",
    "SWING_BASIS_WINDOW",
    "SCALP_BASIS_WINDOW",
    "AGGRESSIVE_SCALP_BASIS_WINDOW",
    # Time Features (S3 — calendar/time-based features)
    "compute_time_features_group",
]
