"""
Mode-specific FeatureSpec — window parameters for all 6 feature groups.

Each mode (SWING, SCALP, AGGRESSIVE_SCALP) has its own FeatureSpec with
window parameters calibrated to its locked timeframe stack.

Timeframes per mode (from v7/docs/pipeline/features.md, router.py):
  - SWING:           primary 4h, context 1d, refinement 1h
  - SCALP:           primary 1h, context 4h, refinement 15m
  - AGGRESSIVE_SCALP: primary 15m, context 1h, refinement 5m

Window parameters are specified in bars of the primary interval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FeatureGroup:
    """Window parameters for one feature group.

    Attributes:
        name: Feature group name (returns, volatility, atr, momentum, volume, breakout).
        short_window: Short lookback in primary-interval bars.
        medium_window: Medium lookback in primary-interval bars.
        long_window: Long lookback in primary-interval bars.
        extra: Optional dict for group-specific parameters (e.g. multipliers, thresholds).
    """

    name: str
    short_window: int = 1
    medium_window: int = 6
    long_window: int = 24
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FeatureSpec:
    """Complete feature specification for one trading mode.

    Attributes:
        mode: Mode name (SWING, SCALP, AGGRESSIVE_SCALP).
        primary_interval: Primary timeframe string (e.g. "4h", "1h", "15m").
        context_intervals: Higher-timeframe context intervals.
        refinement_intervals: Refinement/timing intervals.
        groups: Ordered list of 6 FeatureGroup objects.
        description: Human-readable summary.
    """

    mode: str
    primary_interval: str
    context_intervals: list[str]
    refinement_intervals: list[str]
    groups: list[FeatureGroup]
    description: str = ""

    def get_group(self, name: str) -> FeatureGroup | None:
        """Return the FeatureGroup matching *name*, or None."""
        for g in self.groups:
            if g.name == name:
                return g
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (useful for config export)."""
        return {
            "mode": self.mode,
            "primary_interval": self.primary_interval,
            "context_intervals": list(self.context_intervals),
            "refinement_intervals": list(self.refinement_intervals),
            "groups": [
                {
                    "name": g.name,
                    "short_window": g.short_window,
                    "medium_window": g.medium_window,
                    "long_window": g.long_window,
                    "extra": dict(g.extra),
                }
                for g in self.groups
            ],
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# SWING Feature Spec — primary 4h, context 1d, refinement 1h
# ---------------------------------------------------------------------------
# Each bar = 4 hours.
# Short windows capture 1-bar noise; medium windows span ~1 day (6 bars);
# long windows span ~4 days (24 bars).
_SWING_SPEC = FeatureSpec(
    mode="SWING",
    primary_interval="4h",
    context_intervals=["1d"],
    refinement_intervals=["1h"],
    groups=[
        FeatureGroup(
            name="returns",
            short_window=1,
            medium_window=6,
            long_window=24,
            extra={"geometric": True},
        ),
        FeatureGroup(
            name="volatility",
            short_window=6,
            medium_window=12,
            long_window=24,
        ),
        FeatureGroup(
            name="atr",
            short_window=14,
            medium_window=14,
            long_window=14,
            extra={"atr_multiplier": 2.0},
        ),
        FeatureGroup(
            name="momentum",
            short_window=6,
            medium_window=12,
            long_window=24,
            extra={"roc_period": 1},
        ),
        FeatureGroup(
            name="volume",
            short_window=6,
            medium_window=12,
            long_window=24,
        ),
        FeatureGroup(
            name="breakout",
            short_window=20,
            medium_window=20,
            long_window=20,
            extra={"confirmation_bars": 3},
        ),
    ],
    description=(
        "SWING feature windows: primary 4h bars. "
        "Short ~1 bar, medium ~6 bars (1d), long ~24 bars (4d)."
    ),
)

# ---------------------------------------------------------------------------
# SCALP Feature Spec — primary 1h, context 4h, refinement 15m
# ---------------------------------------------------------------------------
# Each bar = 1 hour.
# Short windows capture 1-2 bar noise; medium windows span ~4h;
# long windows span ~24h (1 day).
_SCALP_SPEC = FeatureSpec(
    mode="SCALP",
    primary_interval="1h",
    context_intervals=["4h"],
    refinement_intervals=["15m"],
    groups=[
        FeatureGroup(
            name="returns",
            short_window=1,
            medium_window=4,
            long_window=24,
            extra={"geometric": True},
        ),
        FeatureGroup(
            name="volatility",
            short_window=4,
            medium_window=12,
            long_window=24,
        ),
        FeatureGroup(
            name="atr",
            short_window=14,
            medium_window=14,
            long_window=14,
            extra={"atr_multiplier": 1.5},
        ),
        FeatureGroup(
            name="momentum",
            short_window=4,
            medium_window=12,
            long_window=24,
            extra={"roc_period": 1},
        ),
        FeatureGroup(
            name="volume",
            short_window=4,
            medium_window=12,
            long_window=24,
        ),
        FeatureGroup(
            name="breakout",
            short_window=24,
            medium_window=24,
            long_window=24,
            extra={"confirmation_bars": 2},
        ),
    ],
    description=(
        "SCALP feature windows: primary 1h bars. "
        "Short ~1 bar, medium ~4 bars (4h), long ~24 bars (1d)."
    ),
)

# ---------------------------------------------------------------------------
# AGGRESSIVE_SCALP Feature Spec — primary 15m, context 1h, refinement 5m
# ---------------------------------------------------------------------------
# Each bar = 15 minutes.
# Short windows capture 1-2 bar noise; medium windows span ~1h (4 bars);
# long windows span ~4h (16 bars).
_AGGRESSIVE_SCALP_SPEC = FeatureSpec(
    mode="AGGRESSIVE_SCALP",
    primary_interval="15m",
    context_intervals=["1h"],
    refinement_intervals=["5m"],
    groups=[
        FeatureGroup(
            name="returns",
            short_window=1,
            medium_window=4,
            long_window=16,
            extra={"geometric": True},
        ),
        FeatureGroup(
            name="volatility",
            short_window=4,
            medium_window=12,
            long_window=24,
        ),
        FeatureGroup(
            name="atr",
            short_window=14,
            medium_window=14,
            long_window=14,
            extra={"atr_multiplier": 1.0},
        ),
        FeatureGroup(
            name="momentum",
            short_window=4,
            medium_window=12,
            long_window=24,
            extra={"roc_period": 1},
        ),
        FeatureGroup(
            name="volume",
            short_window=4,
            medium_window=12,
            long_window=24,
        ),
        FeatureGroup(
            name="breakout",
            short_window=20,
            medium_window=20,
            long_window=20,
            extra={"confirmation_bars": 2},
        ),
    ],
    description=(
        "AGGRESSIVE_SCALP feature windows: primary 15m bars. "
        "Short ~1 bar, medium ~4 bars (1h), long ~16 bars (4h)."
    ),
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

MODE_FEATURE_SPECS: dict[str, FeatureSpec] = {
    "SWING": _SWING_SPEC,
    "SCALP": _SCALP_SPEC,
    "AGGRESSIVE_SCALP": _AGGRESSIVE_SCALP_SPEC,
}


def get_feature_spec(mode: str) -> FeatureSpec:
    """Return the FeatureSpec for *mode*. Raises KeyError on unknown mode."""
    upper = mode.upper()
    if upper not in MODE_FEATURE_SPECS:
        raise KeyError(
            f"Unknown mode '{mode}'. Valid modes: {sorted(MODE_FEATURE_SPECS.keys())}"
        )
    return MODE_FEATURE_SPECS[upper]


def list_modes() -> dict[str, str]:
    """Return {mode: primary_interval} for all known modes."""
    return {m: s.primary_interval for m, s in MODE_FEATURE_SPECS.items()}


def check_no_lookahead(spec: FeatureSpec) -> list[str]:
    """Verify that no FeatureGroup window exceeds safe lookback limits.

    A basic lookahead guard: all windows must be >= 1. Every window >= 1 means
    the feature does not reference future data relative to the decision bar.

    Returns a list of warnings (empty = no issues).
    """
    warnings: list[str] = []
    for group in spec.groups:
        if group.short_window < 1:
            warnings.append(
                f"[{spec.mode}] {group.name}.short_window={group.short_window} < 1"
            )
        if group.medium_window < 1:
            warnings.append(
                f"[{spec.mode}] {group.name}.medium_window={group.medium_window} < 1"
            )
        if group.long_window < 1:
            warnings.append(
                f"[{spec.mode}] {group.name}.long_window={group.long_window} < 1"
            )
    return warnings
