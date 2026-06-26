"""
FeatureSpec — per-mode feature window parameters for V7 pipeline.

Each mode (SWING, SCALP, AGGRESSIVE_SCALP) has its own FeatureSpec that
parameterizes the 6 feature groups at the correct timeframe resolution.
Features are computed from canonical state only; no future bars allowed.

Timeframe stacks (locked per v7/docs/v7_mode_centric_architecture.md):
  SWING:            primary 4h,  context 1d,  refinement 1h
  SCALP:            primary 1h,  context 4h,  refinement 15m
  AGGRESSIVE_SCALP: primary 15m, context 1h,  refinement 5m
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


# ---------------------------------------------------------------------------
# Immutable feature group window collection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureGroupWindows:
    """Window bar counts and intervals for a single feature group.

    All windows are expressed in bars at the mode's primary interval.
    """

    name: str
    primary_interval: str
    lookback_bars: tuple[int, ...]
    context_intervals: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""


# ---------------------------------------------------------------------------
# Mode-specific FeatureSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureSpec:
    """Immutable feature specification for one trading mode.

    Each mode has its own FeatureSpec populated at module level. The spec
    defines window parameters for 6 feature groups:
      returns, volatility, atr, momentum, volume, breakout.

    Rules:
      - All windows are in bars at the mode's primary interval.
      - No future bars. Features are computed from trailing windows only.
      - Missing context produces explicit missingness flags (not silent imputation).
    """

    mode: str
    primary_interval: str
    context_intervals: tuple[str, ...]
    refinement_interval: str

    # 6 feature groups
    returns: FeatureGroupWindows
    volatility: FeatureGroupWindows
    atr: FeatureGroupWindows
    momentum: FeatureGroupWindows
    volume: FeatureGroupWindows
    breakout: FeatureGroupWindows

    # Metadata
    schema_version: str = "1.0.0"
    description: str = ""

    # Per-mode business/research priority (read-only)
    business_priority: str = ""
    threshold_status: str = ""

    _known_modes: ClassVar[dict[str, FeatureSpec]] = {}
    _has_registered: ClassVar[bool] = False

    def __post_init__(self) -> None:
        """Validate internal consistency after frozen construction."""
        if not self.mode:
            raise ValueError("mode must be non-empty")
        if not self.primary_interval:
            raise ValueError("primary_interval must be non-empty")
        # All feature groups must use the same primary interval (no crosstalk)
        for group in (
            self.returns,
            self.volatility,
            self.atr,
            self.momentum,
            self.volume,
            self.breakout,
        ):
            if group.primary_interval != self.primary_interval:
                raise ValueError(
                    f"Feature group '{group.name}' primary_interval "
                    f"'{group.primary_interval}' != FeatureSpec primary_interval "
                    f"'{self.primary_interval}'"
                )
            if not group.lookback_bars:
                raise ValueError(f"Feature group '{group.name}' has empty lookback_bars")
            # Sanity: no negative or zero window
            for w in group.lookback_bars:
                if w <= 0:
                    raise ValueError(
                        f"Feature group '{group.name}' has non-positive "
                        f"lookback bar {w}"
                    )

    @classmethod
    def register(cls, spec: FeatureSpec) -> None:
        """Register a FeatureSpec into the global registry."""
        cls._known_modes[spec.mode] = spec

    @classmethod
    def get(cls, mode: str) -> FeatureSpec:
        """Retrieve a registered FeatureSpec by mode name.

        Raises ValueError if the mode has not been registered.
        """
        if mode not in cls._known_modes:
            raise ValueError(
                f"Unknown mode '{mode}'. Registered modes: "
                f"{sorted(cls._known_modes.keys())}"
            )
        return cls._known_modes[mode]

    @classmethod
    def all_modes(cls) -> tuple[str, ...]:
        """Return sorted tuple of all registered mode names."""
        return tuple(sorted(cls._known_modes.keys()))

    @classmethod
    def get_all(cls) -> dict[str, FeatureSpec]:
        """Return shallow copy of registered specs (read-only surface)."""
        return dict(cls._known_modes)


# ===================================================================
# Per-mode FeatureSpec instances (populated at import time)
# ===================================================================

# --- SWING (SECONDARY_BASELINE, LOCKED_INITIAL_BASELINE) ---------------
# Primary 4h, context 1d, refinement 1h
# Windows in 4h bars:
#   - 1 bar  = 4h
#   - 6 bars  = 1 day
#   - 18 bars = 3 days
#   - 30 bars = 5 days (1 week)
#   - 42 bars = 7 days (typical holding horizon)
#   - 84 bars = 14 days (2 weeks, long horizon)

SWING_RETURN_WINDOWS = (1, 3, 6, 12, 18, 30)
SWING_VOLATILITY_WINDOWS = (20,)
SWING_ATR_WINDOWS = (14,)
SWING_MOMENTUM_WINDOWS = (6, 12, 18, 30)
SWING_VOLUME_WINDOWS = (12, 30)
SWING_BREAKOUT_WINDOWS = (20,)

SWING_SPEC = FeatureSpec(
    mode="SWING",
    primary_interval="4h",
    context_intervals=("1d", "1h"),
    refinement_interval="1h",
    returns=FeatureGroupWindows(
        name="returns",
        primary_interval="4h",
        lookback_bars=SWING_RETURN_WINDOWS,
        description="Log returns and normalized returns over SWING lookback bars",
    ),
    volatility=FeatureGroupWindows(
        name="volatility",
        primary_interval="4h",
        lookback_bars=SWING_VOLATILITY_WINDOWS,
        description="Rolling volatility and volatility percentile over 20 bars (~3.3 days)",
    ),
    atr=FeatureGroupWindows(
        name="atr",
        primary_interval="4h",
        lookback_bars=SWING_ATR_WINDOWS,
        description="ATR(14) at 4h — standard swing timeframe",
    ),
    momentum=FeatureGroupWindows(
        name="momentum",
        primary_interval="4h",
        lookback_bars=SWING_MOMENTUM_WINDOWS,
        description="Momentum indicators (ROC, RSI, MACD-like) over SWING windows",
    ),
    volume=FeatureGroupWindows(
        name="volume",
        primary_interval="4h",
        lookback_bars=SWING_VOLUME_WINDOWS,
        description="Volume ratio, volume trend, relative volume over SWING windows",
    ),
    breakout=FeatureGroupWindows(
        name="breakout",
        primary_interval="4h",
        lookback_bars=SWING_BREAKOUT_WINDOWS,
        description="Breakout detection — Donchian channel, Bollinger squeeze over 20 bars",
    ),
    business_priority="SECONDARY_BASELINE",
    threshold_status="LOCKED_INITIAL_BASELINE",
    description="SWING feature spec — 4h primary, 1d context, 1h refinement",
)
FeatureSpec.register(SWING_SPEC)

# --- SCALP (PRIMARY business/research, HOLD) --------------------------
# Primary 1h, context 4h, refinement 15m
# Windows in 1h bars:
#   - 1 bar  = 1h
#   - 4 bars  = 4h
#   - 12 bars = 12h (half day)
#   - 24 bars = 24h (1 day)
#   - 48 bars = 2 days
#   - 72 bars = 3 days

SCALP_RETURN_WINDOWS = (1, 4, 12, 24, 48)
SCALP_VOLATILITY_WINDOWS = (24,)
SCALP_ATR_WINDOWS = (14,)
SCALP_MOMENTUM_WINDOWS = (4, 12, 24)
SCALP_VOLUME_WINDOWS = (12, 24)
SCALP_BREAKOUT_WINDOWS = (24,)

SCALP_SPEC = FeatureSpec(
    mode="SCALP",
    primary_interval="1h",
    context_intervals=("4h", "15m"),
    refinement_interval="15m",
    returns=FeatureGroupWindows(
        name="returns",
        primary_interval="1h",
        lookback_bars=SCALP_RETURN_WINDOWS,
        description="Log returns and normalized returns over SCALP lookback bars",
    ),
    volatility=FeatureGroupWindows(
        name="volatility",
        primary_interval="1h",
        lookback_bars=SCALP_VOLATILITY_WINDOWS,
        description="Rolling volatility over 24 bars (1 day)",
    ),
    atr=FeatureGroupWindows(
        name="atr",
        primary_interval="1h",
        lookback_bars=SCALP_ATR_WINDOWS,
        description="ATR(14) at 1h — standard scalp timeframe",
    ),
    momentum=FeatureGroupWindows(
        name="momentum",
        primary_interval="1h",
        lookback_bars=SCALP_MOMENTUM_WINDOWS,
        description="Momentum indicators (ROC, RSI, MACD-like) over SCALP windows",
    ),
    volume=FeatureGroupWindows(
        name="volume",
        primary_interval="1h",
        lookback_bars=SCALP_VOLUME_WINDOWS,
        description="Volume ratio, volume trend, relative volume over SCALP windows",
    ),
    breakout=FeatureGroupWindows(
        name="breakout",
        primary_interval="1h",
        lookback_bars=SCALP_BREAKOUT_WINDOWS,
        description="Breakout detection — Donchian channel, squeeze over 24 bars (1 day)",
    ),
    business_priority="PRIMARY",
    threshold_status="HOLD",
    description="SCALP feature spec — 1h primary, 4h context, 15m refinement",
)
FeatureSpec.register(SCALP_SPEC)

# --- AGGRESSIVE_SCALP (PRIMARY business/research, HOLD) ----------------
# Primary 15m, context 1h, refinement 5m
# Windows in 15m bars:
#   - 1 bar  = 15m
#   - 4 bars  = 1h
#   - 12 bars = 3h
#   - 24 bars = 6h
#   - 48 bars = 12h (half day)
#   - 96 bars = 24h (1 day)

AGGRESSIVE_RETURN_WINDOWS = (1, 4, 12, 24, 48)
AGGRESSIVE_VOLATILITY_WINDOWS = (24,)
AGGRESSIVE_ATR_WINDOWS = (10,)
AGGRESSIVE_MOMENTUM_WINDOWS = (4, 12, 24)
AGGRESSIVE_VOLUME_WINDOWS = (12, 24)
AGGRESSIVE_BREAKOUT_WINDOWS = (12,)

AGGRESSIVE_SPEC = FeatureSpec(
    mode="AGGRESSIVE_SCALP",
    primary_interval="15m",
    context_intervals=("1h", "5m"),
    refinement_interval="5m",
    returns=FeatureGroupWindows(
        name="returns",
        primary_interval="15m",
        lookback_bars=AGGRESSIVE_RETURN_WINDOWS,
        description="Log returns and normalized returns over AGGRESSIVE_SCALP lookback bars",
    ),
    volatility=FeatureGroupWindows(
        name="volatility",
        primary_interval="15m",
        lookback_bars=AGGRESSIVE_VOLATILITY_WINDOWS,
        description="Rolling volatility over 24 bars (6 hours)",
    ),
    atr=FeatureGroupWindows(
        name="atr",
        primary_interval="15m",
        lookback_bars=AGGRESSIVE_ATR_WINDOWS,
        description="ATR(10) at 15m — tighter for aggressive scalp",
    ),
    momentum=FeatureGroupWindows(
        name="momentum",
        primary_interval="15m",
        lookback_bars=AGGRESSIVE_MOMENTUM_WINDOWS,
        description="Momentum indicators over AGGRESSIVE_SCALP windows",
    ),
    volume=FeatureGroupWindows(
        name="volume",
        primary_interval="15m",
        lookback_bars=AGGRESSIVE_VOLUME_WINDOWS,
        description="Volume ratio, volume trend, relative volume over AGGRESSIVE windows",
    ),
    breakout=FeatureGroupWindows(
        name="breakout",
        primary_interval="15m",
        lookback_bars=AGGRESSIVE_BREAKOUT_WINDOWS,
        description="Breakout detection — Donchian channel, squeeze over 12 bars (3h)",
    ),
    business_priority="PRIMARY",
    threshold_status="HOLD",
    description=(
        "AGGRESSIVE_SCALP feature spec — 15m primary, 1h context, 5m refinement"
    ),
)
FeatureSpec.register(AGGRESSIVE_SPEC)


# ===================================================================
# Convenience accessor
# ===================================================================

# Type alias for readability
FeatureSpecPerMode = dict[str, FeatureSpec]


def get_feature_spec(mode: str) -> FeatureSpec:
    """Return the FeatureSpec for a given trading mode.

    Shortcut for ``FeatureSpec.get(mode)``.

    Args:
        mode: One of 'SWING', 'SCALP', 'AGGRESSIVE_SCALP'.

    Returns:
        The immutable FeatureSpec for the mode.

    Raises:
        ValueError: If the mode is not registered.
    """
    return FeatureSpec.get(mode)
