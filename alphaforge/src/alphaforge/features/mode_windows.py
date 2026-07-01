"""Per-mode feature window configuration for AlphaForge pipeline.

Each trading mode (SWING, SCALP, AGGRESSIVE_SCALP) has its own window
parameter set tuned to the mode's primary bar interval.

SWING:            4h primary — widest windows, longest memory (LOCKED_INITIAL_BASELINE)
SCALP:            1h primary — narrower windows, faster decay (LOCKED_INITIAL_BASELINE)
AGGRESSIVE_SCALP: 15m primary — very narrow, microstructure-aware (LOCKED_INITIAL_BASELINE)

All windows are in bars at the mode's primary interval. All windows are
LOCKED_INITIAL_BASELINE — safe conservative defaults that must be
recalibrated after first empirical walk-forward evidence.

Rationale for SCALP vs SWING window differences:
  See module docstring section "Window Sizing Rationale" below and the
  individual mode docstrings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Dict


# ===========================================================================
# Window Sizing Rationale
# ===========================================================================
#
# SCALP and AGGRESSIVE_SCALP windows differ from SWING because:
#
# 1. Holding horizon. SCALP trades are closed intraday (hours), not multi-day.
#    Windows must be short enough that the signal is still relevant when the
#    trade executes. A 40-hour lookback (SWING n_returns=10 at 4h) is longer
#    than a typical SCALP trade's full lifetime.
#
# 2. Noise regime. At 1h and 15m bars, price noise dominates. Longer windows
#    average out microstructure noise, but too-long windows include stale
#    regimes. The sweet spot balances noise reduction against regime recency.
#
# 3. Signal decay. Predictive power decays faster at shorter timeframes.
#    A 4h momentum signal may persist for days; a 15m momentum signal may
#    decay within hours. Windows must match the decay rate.
#
# 4. Microstructure awareness. AGGRESSIVE_SCALP at 15m must be sensitive to
#    order-book dynamics (spread, depth, short-term momentum). Overly wide
#    windows (20+ bars at 15m = 5+ hours) include irrelevant pre-session data.
#
# 5. Feature overlap. All three modes compute identical feature groups
#    (returns, volatility, atr, momentum, volume, breakout). Only the window
#    parameters differ. This preserves comparability across modes.
#
# Empirical recalibration triggers:
#   (a) Walk-forward Sharpe ratio degrades vs baseline
#   (b) Feature importance from XGBoost shows specific window dominance
#   (c) Regime shift detected (volatility regime change >2 sigma)
#   (d) Holding-period distribution changes significantly
#
# These window values are LOCKED_INITIAL_BASELINE — safe conservative
# defaults. They are NOT optimized. Recalibrate after first walk-forward
# evidence.


# ===========================================================================
# ModeWindowConfig — frozen per-mode parameter set
# ===========================================================================

@dataclass(frozen=True)
class ModeWindowConfig:
    """Immutable feature window configuration for one trading mode.

    All window parameters are counts of bars at the mode's primary interval.
    All are positive integers except bb_num_std which is float.

    Attributes:
        mode: Trading mode name (SWING, SCALP, AGGRESSIVE_SCALP).
        primary_interval: Bar interval string (4h, 1h, 15m).
        periods_per_year: Number of primary-interval bars in a year.
        n_returns: Lookback bars for N-bar log returns.
        volatility_window: Lookback bars for rolling volatility (returns
            z-score, realized vol, high-low range, Garman-Klass, Parkinson).
        atr_window: Lookback bars for Average True Range.
        momentum_n: Lookback bars for raw momentum and ROC.
        rsi_window: Lookback bars for Wilder's RSI.
        macd_fast: Fast EMA period for MACD.
        macd_slow: Slow EMA period for MACD.
        macd_signal: Signal EMA period for MACD.
        volume_window: Lookback bars for volume ratio and volume trend.
        breakout_window: Lookback bars for range breakout (Donchian).
        bb_window: Lookback bars for Bollinger Bands.
        bb_num_std: Standard deviation multiplier for Bollinger Bands.
        funding_window: Lookback bars for funding rate features.
        description: Human-readable rationale for this mode's windows.
        threshold_status: Lock status (LOCKED_INITIAL_BASELINE for all).
    """

    mode: str
    primary_interval: str
    periods_per_year: int
    n_returns: int
    volatility_window: int
    atr_window: int
    momentum_n: int
    rsi_window: int
    macd_fast: int
    macd_slow: int
    macd_signal: int
    volume_window: int
    breakout_window: int
    bb_window: int
    bb_num_std: float
    funding_window: int = 10
    description: str = ""
    threshold_status: str = "LOCKED_INITIAL_BASELINE"

    # Registry of all configs keyed by mode name
    _registry: ClassVar[Dict[str, ModeWindowConfig]] = {}

    def __post_init__(self) -> None:
        """Validate window parameters after frozen construction."""
        int_params = [
            ("periods_per_year", self.periods_per_year),
            ("n_returns", self.n_returns),
            ("volatility_window", self.volatility_window),
            ("atr_window", self.atr_window),
            ("momentum_n", self.momentum_n),
            ("rsi_window", self.rsi_window),
            ("macd_fast", self.macd_fast),
            ("macd_slow", self.macd_slow),
            ("macd_signal", self.macd_signal),
            ("volume_window", self.volume_window),
            ("breakout_window", self.breakout_window),
            ("bb_window", self.bb_window),
        ]
        for name, value in int_params:
            if not isinstance(value, int) or value <= 0:
                raise ValueError(
                    f"{self.mode}: {name} must be a positive integer, got {value!r}"
                )
        if self.bb_num_std <= 0:
            raise ValueError(
                f"{self.mode}: bb_num_std must be positive, got {self.bb_num_std}"
            )
        # MACD: fast < slow
        if self.macd_fast >= self.macd_slow:
            raise ValueError(
                f"{self.mode}: macd_fast ({self.macd_fast}) must be < "
                f"macd_slow ({self.macd_slow})"
            )

    @classmethod
    def register(cls, config: ModeWindowConfig) -> None:
        """Register a ModeWindowConfig in the global registry."""
        cls._registry[config.mode] = config

    @classmethod
    def get(cls, mode: str) -> ModeWindowConfig:
        """Retrieve a registered config by mode name.

        Raises ValueError if mode not registered.
        """
        if mode not in cls._registry:
            raise ValueError(
                f"Unknown mode '{mode}'. Registered: "
                f"{sorted(cls._registry.keys())}"
            )
        return cls._registry[mode]

    @classmethod
    def all_modes(cls) -> tuple[str, ...]:
        """Return sorted tuple of all registered mode names."""
        return tuple(sorted(cls._registry.keys()))

    def to_dict(self) -> Dict[str, object]:
        """Return window parameters as a dict for pipeline consumption.

        Keys match the _MODE_DEFAULTS dict format used by compute_features().
        """
        return {
            "n_returns": self.n_returns,
            "volatility_window": self.volatility_window,
            "atr_window": self.atr_window,
            "momentum_n": self.momentum_n,
            "rsi_window": self.rsi_window,
            "macd_fast": self.macd_fast,
            "macd_slow": self.macd_slow,
            "macd_signal": self.macd_signal,
            "volume_window": self.volume_window,
            "breakout_window": self.breakout_window,
            "bb_window": self.bb_window,
            "bb_num_std": self.bb_num_std,
            "funding_window": self.funding_window,
            "periods_per_year": self.periods_per_year,
        }


# ===========================================================================
# SWING — 4h primary, widest windows (LOCKED_INITIAL_BASELINE)
# ===========================================================================
# Timeframe stack: primary 4h, context 1d, refinement 1h.
# periods_per_year: 365 days * 6 bars/day = 2190.
#
# Windows are the established baseline used in the initial pipeline
# implementation. These values are carried forward unchanged.

SWING_WINDOWS = ModeWindowConfig(
    mode="SWING",
    primary_interval="4h",
    periods_per_year=2190,
    n_returns=10,
    volatility_window=20,
    atr_window=14,
    momentum_n=10,
    rsi_window=14,
    macd_fast=12,
    macd_slow=26,
    macd_signal=9,
    volume_window=20,
    breakout_window=20,
    bb_window=20,
    bb_num_std=2.0,
    funding_window=10,
    description=(
        "SWING 4h windows — widest lookbacks for multi-day holding. "
        "n_returns=10 (40h), vol_window=20 (80h ~3.3d), "
        "MACD(12,26,9) at 4h (~2d/4.3d/1.5d). "
        "Conservative baseline, carries existing pipeline defaults."
    ),
)

# ===========================================================================
# SCALP — 1h primary, narrower windows (LOCKED_INITIAL_BASELINE)
# ===========================================================================
# Timeframe stack: primary 1h, context 4h, refinement 15m.
# periods_per_year: 365 days * 24 bars/day = 8760.
#
# Windows are compressed relative to SWING to match the intraday holding
# horizon. n_returns=12 (12h vs 40h SWING), volatility_window=24 (24h=1d
# vs 3.3d SWING). MACD(8,17,9) at 1h (~8h/17h/9h) — faster than
# classic (12,26,9) which at 1h would span 12h/26h.

SCALP_WINDOWS = ModeWindowConfig(
    mode="SCALP",
    primary_interval="1h",
    periods_per_year=8760,
    n_returns=12,
    volatility_window=24,
    atr_window=14,
    momentum_n=12,
    rsi_window=14,
    macd_fast=8,
    macd_slow=17,
    macd_signal=9,
    volume_window=24,
    breakout_window=24,
    bb_window=20,
    bb_num_std=2.0,
    funding_window=12,
    description=(
        "SCALP 1h windows — compressed for intraday holding. "
        "n_returns=12 (12h), vol_window=24 (1d), MACD(8,17,9) at 1h. "
        "Narrower than SWING: faster reaction, shorter memory, "
        "matched to intraday signal decay."
    ),
)

# ===========================================================================
# AGGRESSIVE_SCALP — 15m primary, very narrow windows (LOCKED_INITIAL_BASELINE)
# ===========================================================================
# Timeframe stack: primary 15m, context 1h, refinement 5m.
# periods_per_year: 365 days * 96 bars/day = 35040.
#
# Very narrow windows for microstructure sensitivity. n_returns=16 (4h),
# volatility_window=24 (6h), atr_window=10 (2.5h — faster than standard 14).
# RSI(10) for faster oscillator response. MACD(6,13,5) at 15m (~1.5h/3.25h/1.25h)
# — fastest of the three modes. bb_window=12 (3h) for tighter Bollinger Bands.

AGGRESSIVE_SCALP_WINDOWS = ModeWindowConfig(
    mode="AGGRESSIVE_SCALP",
    primary_interval="15m",
    periods_per_year=35040,
    n_returns=16,
    volatility_window=24,
    atr_window=10,
    momentum_n=16,
    rsi_window=10,
    macd_fast=6,
    macd_slow=13,
    macd_signal=5,
    volume_window=24,
    breakout_window=12,
    bb_window=12,
    bb_num_std=2.0,
    funding_window=16,
    description=(
        "AGGRESSIVE_SCALP 15m windows — very narrow, microstructure-aware. "
        "n_returns=16 (4h), vol_window=24 (6h), ATR(10), RSI(10), "
        "MACD(6,13,5) at 15m (~1.5h/3.25h/1.25h). "
        "Tightest windows: fastest reaction, shortest memory, "
        "sensitive to order-book dynamics."
    ),
)

# Register all configs
ModeWindowConfig.register(SWING_WINDOWS)
ModeWindowConfig.register(SCALP_WINDOWS)
ModeWindowConfig.register(AGGRESSIVE_SCALP_WINDOWS)


# ===========================================================================
# Convenience accessor
# ===========================================================================

def get_mode_windows(mode: str) -> ModeWindowConfig:
    """Return the ModeWindowConfig for a given trading mode.

    Shortcut for ``ModeWindowConfig.get(mode)``.

    Args:
        mode: One of 'SWING', 'SCALP', 'AGGRESSIVE_SCALP'.

    Returns:
        The immutable ModeWindowConfig for the mode.

    Raises:
        ValueError: If the mode is not registered.
    """
    return ModeWindowConfig.get(mode)


def get_all_mode_windows() -> Dict[str, ModeWindowConfig]:
    """Return a shallow copy of all registered mode window configs."""
    return dict(ModeWindowConfig._registry)
