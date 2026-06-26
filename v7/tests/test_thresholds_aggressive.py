"""Tests for v7.thresholds.aggressive_scalp — AGGRESSIVE_SCALP promotion gates.

ISSUE #36: P0 — AGGRESSIVE_SCALP threshold empirical evidence and LOCK.
"""

import pytest

from v7.thresholds.aggressive_scalp import (
    AGGRESSIVE_SCALP_THRESHOLDS,
    AggressiveScalpThresholds,
    is_actionable,
)
from v7.router import LOCKED_INITIAL_BASELINE


class TestAggressiveScalpThresholds:
    """Threshold dataclass correctness and default value verification."""

    def test_thresholds_is_frozen(self):
        """AggressiveScalpThresholds dataclass must be frozen (immutable)."""
        t = AggressiveScalpThresholds()
        with pytest.raises(Exception):
            t.min_expected_r = 999.0  # type: ignore

    def test_default_status_is_locked_initial_baseline(self):
        """Issue #36: thresholds are LOCKED_INITIAL_BASELINE."""
        assert AGGRESSIVE_SCALP_THRESHOLDS.status == LOCKED_INITIAL_BASELINE

    def test_default_hold_reason_is_empty(self):
        """Since status is not HOLD, hold_reason must be empty."""
        assert AGGRESSIVE_SCALP_THRESHOLDS.hold_reason == ""

    def test_min_expected_r_is_0_10(self):
        """Smallest edge tolerated — volume compensates."""
        assert AGGRESSIVE_SCALP_THRESHOLDS.min_expected_r == 0.10

    def test_max_drawdown_r_is_minus_3(self):
        """Per-session drawdown limit."""
        assert AGGRESSIVE_SCALP_THRESHOLDS.max_drawdown_r == -3.0

    def test_min_win_rate_is_0_42(self):
        """Volume-over-accuracy strategy requires at least 42% win rate."""
        assert AGGRESSIVE_SCALP_THRESHOLDS.min_win_rate == 0.42

    def test_cost_stress_multiplier_is_3(self):
        """Most cost-sensitive mode — triples costs for safety margin."""
        assert AGGRESSIVE_SCALP_THRESHOLDS.cost_stress_multiplier == 3.0

    def test_latency_max_ms_is_100(self):
        """Fastest execution pipeline required."""
        assert AGGRESSIVE_SCALP_THRESHOLDS.latency_max_ms == 100

    def test_funding_sensitivity_is_critical(self):
        """Funding rates directly gate trade eligibility."""
        assert AGGRESSIVE_SCALP_THRESHOLDS.funding_sensitivity == "CRITICAL"

    def test_min_volume_ratio_is_1_5(self):
        """Volume must be at least 1.5x average — liquidity gate."""
        assert AGGRESSIVE_SCALP_THRESHOLDS.min_volume_ratio == 1.5

    def test_module_level_constant_is_correct_type(self):
        """AGGRESSIVE_SCALP_THRESHOLDS must be an AggressiveScalpThresholds."""
        assert isinstance(
            AGGRESSIVE_SCALP_THRESHOLDS, AggressiveScalpThresholds
        )


class TestIsActionable:
    """is_actionable() gate evaluation for AGGRESSIVE_SCALP."""

    def _valid_args(self, **overrides):
        """Return arguments that pass all gates by default.

        Default expected_r=0.35 clears the cost-stressed minimum
        (min_expected_r=0.10 * cost_stress_multiplier=3.0 = 0.30).
        """
        return {
            "expected_r": 0.35,
            "current_drawdown_r": 0.0,
            "win_rate": 0.55,
            "volume_ratio": 2.0,
            "funding_cost_r": 0.001,
            "entry_risk_r": 0.05,
            **overrides,
        }

    # --- Passing cases ---

    def test_all_gates_pass_with_strong_candidate(self):
        """A strong candidate passes every gate."""
        passed, reason = is_actionable(**self._valid_args())
        assert passed is True
        assert reason == ""

    def test_passes_at_minimum_edge(self):
        """Passes at the cost-stressed minimum expected R.

        With cost_stress_multiplier=3.0, stressed_min = 0.10*3.0 = 0.30.
        Below 0.30, the cost stress gate blocks.
        """
        passed, reason = is_actionable(**self._valid_args(expected_r=0.30))
        assert passed is True, f"Expected pass at stressed_min=0.30, got: {reason}"

    def test_passes_at_minimum_win_rate(self):
        """Passes right at the minimum win rate threshold."""
        passed, reason = is_actionable(**self._valid_args(win_rate=0.42))
        assert passed is True

    def test_passes_at_minimum_volume_ratio(self):
        """Passes right at the minimum volume ratio threshold."""
        passed, reason = is_actionable(**self._valid_args(volume_ratio=1.5))
        assert passed is True

    # --- Expected R gate failures ---

    def test_fails_when_expected_r_below_threshold(self):
        """Rejects when expected R is below min_expected_r."""
        passed, reason = is_actionable(**self._valid_args(expected_r=0.05))
        assert passed is False
        assert "min_expected_r" in reason

    def test_fails_when_expected_r_is_zero(self):
        """Rejects a candidate with zero expected edge."""
        passed, reason = is_actionable(**self._valid_args(expected_r=0.0))
        assert passed is False

    def test_fails_when_expected_r_is_negative(self):
        """Rejects a candidate with negative expected R."""
        passed, reason = is_actionable(**self._valid_args(expected_r=-0.20))
        assert passed is False

    # --- Drawdown gate failures ---

    def test_fails_when_drawdown_exceeds_max(self):
        """Rejects when session drawdown exceeds max_drawdown_r."""
        passed, reason = is_actionable(
            **self._valid_args(current_drawdown_r=-3.5)
        )
        assert passed is False
        assert "drawdown" in reason.lower()

    def test_passes_when_drawdown_at_boundary(self):
        """Passes at exactly the max drawdown boundary."""
        passed, reason = is_actionable(
            **self._valid_args(current_drawdown_r=-3.0)
        )
        assert passed is True

    # --- Win rate gate failures ---

    def test_fails_when_win_rate_below_threshold(self):
        """Rejects when rolling win rate is below minimum."""
        passed, reason = is_actionable(**self._valid_args(win_rate=0.30))
        assert passed is False
        assert "Win rate" in reason

    # --- Volume ratio gate failures ---

    def test_fails_when_volume_below_average(self):
        """Rejects when volume is below the liquidity gate."""
        passed, reason = is_actionable(**self._valid_args(volume_ratio=1.2))
        assert passed is False
        assert "Volume ratio" in reason

    def test_fails_when_volume_is_zero(self):
        """Rejects when there is no volume at all."""
        passed, reason = is_actionable(**self._valid_args(volume_ratio=0.0))
        assert passed is False

    # --- Funding sensitivity gate failures ---

    def test_fails_when_funding_cost_exceeds_tolerance(self):
        """CRITICAL funding sensitivity blocks when funding > 50% of edge."""
        passed, reason = is_actionable(
            **self._valid_args(expected_r=0.12, funding_cost_r=0.07)
        )
        assert passed is False
        assert "Funding cost" in reason

    def test_passes_when_funding_cost_within_tolerance(self):
        """Funding cost at exactly 50% of edge still passes.

        expected_r=0.30 passes the cost stress gate (stressed_min=0.30)
        and funding_cost_r=0.15 is exactly 50% of edge (tolerance).
        """
        passed, reason = is_actionable(
            **self._valid_args(expected_r=0.30, funding_cost_r=0.15)
        )
        assert passed is True, f"Expected pass but got: {reason}"

    def test_passes_when_funding_cost_is_zero(self):
        """Zero funding cost trivially passes the funding gate."""
        passed, reason = is_actionable(
            **self._valid_args(funding_cost_r=0.0)
        )
        assert passed is True

    # --- Entry risk gate failures ---

    def test_fails_when_entry_risk_is_zero(self):
        """Rejects when entry risk R is zero."""
        passed, reason = is_actionable(**self._valid_args(entry_risk_r=0.0))
        assert passed is False
        assert "zero or negative" in reason.lower()

    def test_fails_when_entry_risk_is_negative(self):
        """Rejects when entry risk R is negative."""
        passed, reason = is_actionable(**self._valid_args(entry_risk_r=-0.01))
        assert passed is False

    # --- Cost stress test failures ---

    def test_fails_when_expected_r_below_cost_stressed_minimum(self):
        """Cost stress gate rejects expected_r < min_expected_r * cost_stress_multiplier.

        stressed_min = 0.10 * 3.0 = 0.30.
        expected_r=0.25 passes gate 1 (>= 0.10) but fails cost stress (< 0.30).
        """
        passed, reason = is_actionable(**self._valid_args(expected_r=0.25))
        assert passed is False
        assert "cost-stressed" in reason.lower()

    def test_cost_stressed_formula_is_correct(self):
        """Cost stress: expected_r must be >= min_expected_r * cost_stress_multiplier.

        stressed_min = 0.10 * 3.0 = 0.30.
        expected_r=0.10 passes gate 1 (>= 0.10) but fails gate 7 (< 0.30).
        """
        passed, reason = is_actionable(**self._valid_args(expected_r=0.10))
        # 0.10 passes gate 1 but fails cost stress (needs >= 0.30)
        assert passed is False
        assert "cost-stressed" in reason.lower() or "cost_stress" in reason

    # --- Combined failures ---

    def test_multiple_failures_report_first_failure_only(self):
        """When multiple gates fail, only the first failure reason is returned."""
        passed, reason = is_actionable(
            expected_r=0.05,       # Fails gate 1 (below min)
            current_drawdown_r=-5.0,  # Would also fail gate 2
            win_rate=0.30,         # Would also fail gate 3
            volume_ratio=1.0,      # Would also fail gate 4
            funding_cost_r=0.50,
            entry_risk_r=0.01,
        )
        assert passed is False
        # First failure is expected_r gate
        assert "min_expected_r" in reason

    # --- Edge cases ---

    def test_works_with_all_boundary_values(self):
        """All values at their respective gate boundaries should pass.

        expected_r=0.30 is the cost-stressed minimum (0.10 * 3.0).
        expected_r=0.10 (raw min_expected_r) alone is insufficient due to
        the cost stress multiplier.
        """
        passed, reason = is_actionable(
            expected_r=0.30,
            current_drawdown_r=-3.0,
            win_rate=0.42,
            volume_ratio=1.5,
            funding_cost_r=0.0,
            entry_risk_r=0.001,
        )
        assert passed is True, f"Expected pass but got: {reason}"

    def test_large_expected_r_still_passes(self):
        """Very large expected R should pass all gates comfortably."""
        passed, reason = is_actionable(
            expected_r=2.5,
            current_drawdown_r=0.0,
            win_rate=0.80,
            volume_ratio=5.0,
            funding_cost_r=0.001,
            entry_risk_r=0.10,
        )
        assert passed is True
