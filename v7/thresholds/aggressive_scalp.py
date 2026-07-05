"""
AGGRESSIVE_SCALP Promotion Thresholds.

PRIMARY business/research mode — 15m primary, 1h context, 5m refinement.

Status: LOCKED_INITIAL_BASELINE (Issue #36)
  Recalibrate after first walk-forward OOS empirical evidence.

These thresholds define the minimum policy gates the AGGRESSIVE_SCALP
mode must satisfy before a trade candidate is eligible for execution
eligibility review by the runtime.

AGGRESSIVE_SCALP is the most cost-sensitive mode because holding costs
(fee, slippage, funding) dominate at short timeframes. Volume must be
above average to ensure sufficient liquidity for rapid execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from v7.router import LOCKED_INITIAL_BASELINE


@dataclass(frozen=True)
class AggressiveScalpThresholds:
    """AGGRESSIVE_SCALP mode promotion and execution thresholds.

    All threshold values are LOCKED_INITIAL_BASELINE — they represent
    conservative, safe starting points. Recalibrate after the first
    empirical walk-forward evaluation.

    Attributes:
        min_expected_r: Minimum expected R-multiple per trade (net after costs).
            AGGRESSIVE_SCALP tolerates the smallest edge because high trade
            volume compensates for low per-trade expectancy.
        max_drawdown_r: Maximum allowed per-session drawdown in R-multiples.
            Tighter than longer-timeframe modes due to higher trade frequency.
        min_win_rate: Minimum fraction of winning trades in evaluation window.
            Lower threshold reflects the mode's volume-over-accuracy strategy.
        cost_stress_multiplier: Multiplier applied to modeled costs during
            stress testing. At 3.0, costs are tripled to ensure margin of
            safety against real-world fee/slippage/latency degradation.
        latency_max_ms: Maximum acceptable analysis-to-decision latency in
            milliseconds. AGGRESSIVE_SCALP requires fastest execution pipeline.
        funding_sensitivity: How funding costs affect decision thresholds.
            CRITICAL means funding rates directly gate trade eligibility.
        min_volume_ratio: Volume must be at least this multiple of average
            volume to pass the liquidity gate. Values > 1.0 filter out
            low-liquidity periods where execution quality degrades.
        status: Design lock status (LOCKED_INITIAL_BASELINE).
        hold_reason: Empty when status allows execution; populated when HOLD.
    """

    min_expected_r: float = 0.10
    max_drawdown_r: float = -3.0
    min_win_rate: float = 0.42
    cost_stress_multiplier: float = 3.0
    latency_max_ms: int = 100
    funding_sensitivity: str = "CRITICAL"
    min_volume_ratio: float = 1.5
    status: str = LOCKED_INITIAL_BASELINE
    hold_reason: str = ""


AGGRESSIVE_SCALP_THRESHOLDS = AggressiveScalpThresholds()


def is_actionable(
    *,
    expected_r: float,
    current_drawdown_r: float,
    win_rate: float,
    volume_ratio: float,
    funding_cost_r: float,
    entry_risk_r: float,
) -> tuple[bool, str]:
    """Evaluate whether an AGGRESSIVE_SCALP trade candidate is actionable.

    Applies all mode-specific gates in priority order. Returns a
    (passed, reason) tuple.

    Args:
        expected_r: Expected R-multiple after modeled costs (net).
        current_drawdown_r: Current session drawdown in R-multiples
            (negative for drawdown). If no drawdown, pass 0.0.
        win_rate: Rolling win rate over recent trades (0.0-1.0).
        volume_ratio: Current volume / average volume ratio.
        funding_cost_r: Projected funding cost in R-multiples for the
            expected holding period.
        entry_risk_r: Entry risk in R-multiples (stop distance cost).
            Must be > 0 to avoid division by zero.

    Returns:
        (passed: bool, reason: str) — True if all gates pass,
        with an empty reason string on success.
    """
    t = AGGRESSIVE_SCALP_THRESHOLDS

    # Gate 1: Expected R must exceed minimum edge
    if expected_r < t.min_expected_r:
        return False, (
            f"Expected R {expected_r:.4f} < "
            f"min_expected_r {t.min_expected_r}"
        )

    # Gate 2: Session drawdown must not exceed max
    if current_drawdown_r < t.max_drawdown_r:
        return False, (
            f"Session drawdown {current_drawdown_r:.4f} exceeds "
            f"max_drawdown_r {t.max_drawdown_r}"
        )

    # Gate 3: Rolling win rate must meet minimum
    if win_rate < t.min_win_rate:
        return False, (
            f"Win rate {win_rate:.4f} < "
            f"min_win_rate {t.min_win_rate}"
        )

    # Gate 4: Volume must be above average
    if volume_ratio < t.min_volume_ratio:
        return False, (
            f"Volume ratio {volume_ratio:.4f} < "
            f"min_volume_ratio {t.min_volume_ratio}"
        )

    # Gate 5: Funding sensitivity check (CRITICAL)
    if t.funding_sensitivity == "CRITICAL" and funding_cost_r > 0:
        # When funding is CRITICAL, funding cost must not consume
        # more than 50% of the expected edge, cost-adjusted
        funding_tolerance = expected_r * 0.5
        if funding_cost_r > funding_tolerance:
            return False, (
                f"Funding cost {funding_cost_r:.6f} exceeds "
                f"tolerance {funding_tolerance:.6f} "
                f"(50% of expected_r)"
            )

    # Gate 6: Entry risk sanity check (must be > 0)
    if entry_risk_r <= 0:
        return False, "Entry risk R is zero or negative"

    # Gate 7: Cost-stressed expected R (stress-tested edge).
    # The cost stress multiplies the minimum required edge to account
    # for real-world cost degradation (worse fees/slippage/latency/impact).
    # stressed_min = min_expected_r * cost_stress_multiplier
    # Passes when: expected_r >= stressed_min
    stressed_min = t.min_expected_r * t.cost_stress_multiplier
    if expected_r < stressed_min - 1e-12:
        return False, (
            f"Expected R {expected_r:.4f} < cost-stressed minimum "
            f"{stressed_min:.4f} "
            f"(min_expected_r {t.min_expected_r} * "
            f"cost_stress_multiplier {t.cost_stress_multiplier})"
        )

    return True, ""
