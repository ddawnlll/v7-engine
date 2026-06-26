"""
SCALP mode threshold definitions — LOCKED_INITIAL_BASELINE.

SCALP is the PRIMARY business mode (1h primary, 4h context, 15m refinement).
These thresholds define conservative baselines for scalping trade acceptance.

Design rationale:
  - min_expected_r: 0.15 — lower than SWING (0.35); scalping targets smaller
    per-trade edge from higher frequency. Must be net of all costs.
  - max_drawdown_r: -2.0 — tighter drawdown limit per session; scalping runs
    many small trades, drawdown can accumulate fast without a hard cap.
  - min_win_rate: 0.45 — lower than SWING (0.50 implied); scalping compensates
    lower win rate with higher frequency and favorable R:R profiles.
  - cost_stress_multiplier: 2.5 — scalping is cost-sensitive; stress multiplier
    ensures survivability under realistic fee/slippage/funding regimes.
  - latency_max_ms: 200 — fast execution required; higher latency erodes the
    small edge that scalping depends on.
  - funding_sensitivity: HIGH — funding cost eats scalp edge faster than swing.

Recalibration trigger: first empirical walk-forward validation (OOS).
Do NOT change these values without a LOCKED_INITIAL_BASELINE recalibration
following the G0-G10 promotion gate framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FundingSensitivity(str, Enum):
    """Funding rate cost sensitivity classification."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


@dataclass(frozen=True)
class ScalpThresholds:
    """SCALP mode trade acceptance thresholds.

    All fields are frozen and immutable. Thresholds are LOCKED_INITIAL_BASELINE
    — conservative baselines recalibrated after first empirical walk-forward
    validation.

    Attributes:
        min_expected_r: Minimum expected R-multiple after costs (net).
            Must be >0, typically lower than swing thresholds.
        max_drawdown_r: Maximum allowed drawdown in R per session.
            Negative value; session drawdown exceeding this triggers HOLD.
        min_win_rate: Minimum win rate (0.0-1.0) for trade acceptance.
            Below this rate, trades are rejected regardless of edge.
        cost_stress_multiplier: Multiplier applied to base costs for
            stress testing. 2.5 means costs are 2.5x nominal in stress.
        latency_max_ms: Maximum acceptable latency in milliseconds.
            Exchanges evaluated must have latency <= this value.
        funding_sensitivity: Sensitivity classification for funding rate
            impact. HIGH means funding is a significant cost factor.
        max_position_size_pct: Maximum position size as percentage of
            notional. Lower for scalping due to cost sensitivity.
        stop_multiplier: ATR multiplier for stop-loss placement.
            Tighter stops for scalping than swing.
        target_multiplier: ATR multiplier for take-profit placement.
    """

    min_expected_r: float
    max_drawdown_r: float
    min_win_rate: float
    cost_stress_multiplier: float
    latency_max_ms: int
    funding_sensitivity: FundingSensitivity
    max_position_size_pct: float = 5.0
    stop_multiplier: float = 1.5
    target_multiplier: float = 1.5

    def __post_init__(self):
        """Validate that thresholds are within sane bounds.

        Validation only — no attribute mutation. Frozen dataclass allows
        __post_init__ for read-only validation.
        """
        if self.min_expected_r <= 0:
            raise ValueError(
                f"min_expected_r must be > 0, got {self.min_expected_r}"
            )
        if self.max_drawdown_r >= 0:
            raise ValueError(
                f"max_drawdown_r must be negative (drawdown), got {self.max_drawdown_r}"
            )
        if not 0.0 <= self.min_win_rate <= 1.0:
            raise ValueError(
                f"min_win_rate must be in [0.0, 1.0], got {self.min_win_rate}"
            )
        if self.cost_stress_multiplier < 1.0:
            raise ValueError(
                f"cost_stress_multiplier must be >= 1.0, got {self.cost_stress_multiplier}"
            )
        if self.latency_max_ms <= 0:
            raise ValueError(
                f"latency_max_ms must be > 0, got {self.latency_max_ms}"
            )
        if self.max_position_size_pct <= 0:
            raise ValueError(
                f"max_position_size_pct must be > 0, got {self.max_position_size_pct}"
            )
        if self.stop_multiplier <= 0:
            raise ValueError(
                f"stop_multiplier must be > 0, got {self.stop_multiplier}"
            )
        if self.target_multiplier <= 0:
            raise ValueError(
                f"target_multiplier must be > 0, got {self.target_multiplier}"
            )

    @property
    def reward_risk_ratio(self) -> float:
        """Implied reward:risk ratio from stop/target multipliers."""
        return self.target_multiplier / self.stop_multiplier

    @property
    def is_cost_sensitive(self) -> bool:
        """Whether this mode is cost-sensitive (cost_stress_multiplier >= 2.0)."""
        return self.cost_stress_multiplier >= 2.0

    @property
    def is_latency_sensitive(self) -> bool:
        """Whether this mode requires low latency (latency_max_ms <= 200)."""
        return self.latency_max_ms <= 200

    @property
    def stress_cost_multiplier(self) -> float:
        """Alias for cost_stress_multiplier — stress-adjusted cost multiplier."""
        return self.cost_stress_multiplier

    def to_dict(self) -> dict:
        """Return thresholds as a plain dict (for policy integration)."""
        return {
            "min_expected_r": self.min_expected_r,
            "max_drawdown_r": self.max_drawdown_r,
            "min_win_rate": self.min_win_rate,
            "cost_stress_multiplier": self.cost_stress_multiplier,
            "latency_max_ms": self.latency_max_ms,
            "funding_sensitivity": self.funding_sensitivity.value,
            "max_position_size_pct": self.max_position_size_pct,
            "stop_multiplier": self.stop_multiplier,
            "target_multiplier": self.target_multiplier,
        }


# ── Canonical SCALP thresholds (LOCKED_INITIAL_BASELINE) ──────────────
# Recalibrate after first empirical walk-forward validation (OOS).
# Use G0-G10 gate framework for recalibration promotion.

SCALP_THRESHOLDS = ScalpThresholds(
    min_expected_r=0.15,
    max_drawdown_r=-2.0,
    min_win_rate=0.45,
    cost_stress_multiplier=2.5,
    latency_max_ms=200,
    funding_sensitivity=FundingSensitivity.HIGH,
    max_position_size_pct=5.0,
    stop_multiplier=1.5,
    target_multiplier=1.5,
)


def validate_scalp(
    *,
    expected_r_net: float,
    drawdown_r: float,
    win_rate: float,
    latency_ms: int,
) -> tuple[bool, list[str]]:
    """Validate a SCALP trade candidate against threshold baselines.

    Args:
        expected_r_net: Expected R-multiple after costs.
        drawdown_r: Current session drawdown in R (negative value).
        win_rate: Current estimated win rate (0.0-1.0).
        latency_ms: Measured end-to-end latency in milliseconds.

    Returns:
        Tuple of (passed: bool, failures: list[str]).
        If passed is True, failures is empty.
    """
    thresholds = SCALP_THRESHOLDS
    failures: list[str] = []

    if expected_r_net < thresholds.min_expected_r:
        failures.append(
            f"expected_r_net={expected_r_net:.4f} < "
            f"min_expected_r={thresholds.min_expected_r}"
        )
    if drawdown_r < thresholds.max_drawdown_r:
        failures.append(
            f"session_drawdown_r={drawdown_r:.4f} exceeds "
            f"max_drawdown_r={thresholds.max_drawdown_r}"
        )
    if win_rate < thresholds.min_win_rate:
        failures.append(
            f"win_rate={win_rate:.3f} < "
            f"min_win_rate={thresholds.min_win_rate}"
        )
    if latency_ms > thresholds.latency_max_ms:
        failures.append(
            f"latency={latency_ms}ms > "
            f"latency_max_ms={thresholds.latency_max_ms}ms"
        )

    return (len(failures) == 0, failures)
