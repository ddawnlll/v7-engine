"""
Tests for v7.thresholds.scalp — SCALP mode threshold definitions.

SCALP is PRIMARY business mode. Thresholds are LOCKED_INITIAL_BASELINE.
"""

import pytest

from v7.thresholds.scalp import (
    SCALP_THRESHOLDS,
    FundingSensitivity,
    ScalpThresholds,
    validate_scalp,
)


# ── ScalpThresholds initialisation and validation ──────────────────────

class TestScalpThresholdsInit:
    """Test ScalpThresholds frozen dataclass construction and validation."""

    def test_canonical_thresholds_initialise(self):
        """Canonical SCALP_THRESHOLDS singleton creates without error."""
        assert SCALP_THRESHOLDS.min_expected_r == 0.15
        assert SCALP_THRESHOLDS.max_drawdown_r == -2.0
        assert SCALP_THRESHOLDS.min_win_rate == 0.45
        assert SCALP_THRESHOLDS.cost_stress_multiplier == 2.5
        assert SCALP_THRESHOLDS.latency_max_ms == 200
        assert SCALP_THRESHOLDS.funding_sensitivity == FundingSensitivity.HIGH
        assert SCALP_THRESHOLDS.max_position_size_pct == 5.0
        assert SCALP_THRESHOLDS.stop_multiplier == 1.5
        assert SCALP_THRESHOLDS.target_multiplier == 1.5

    def test_min_expected_r_rejects_non_positive(self):
        """min_expected_r must be > 0."""
        with pytest.raises(ValueError, match="min_expected_r must be > 0"):
            ScalpThresholds(
                min_expected_r=0.0,
                max_drawdown_r=-2.0,
                min_win_rate=0.45,
                cost_stress_multiplier=2.5,
                latency_max_ms=200,
                funding_sensitivity=FundingSensitivity.HIGH,
            )

        with pytest.raises(ValueError, match="min_expected_r must be > 0"):
            ScalpThresholds(
                min_expected_r=-0.15,
                max_drawdown_r=-2.0,
                min_win_rate=0.45,
                cost_stress_multiplier=2.5,
                latency_max_ms=200,
                funding_sensitivity=FundingSensitivity.HIGH,
            )

    def test_max_drawdown_r_rejects_non_negative(self):
        """max_drawdown_r must be negative (drawdown)."""
        with pytest.raises(ValueError, match="max_drawdown_r must be negative"):
            ScalpThresholds(
                min_expected_r=0.15,
                max_drawdown_r=0.0,
                min_win_rate=0.45,
                cost_stress_multiplier=2.5,
                latency_max_ms=200,
                funding_sensitivity=FundingSensitivity.HIGH,
            )

        with pytest.raises(ValueError, match="max_drawdown_r must be negative"):
            ScalpThresholds(
                min_expected_r=0.15,
                max_drawdown_r=5.0,
                min_win_rate=0.45,
                cost_stress_multiplier=2.5,
                latency_max_ms=200,
                funding_sensitivity=FundingSensitivity.HIGH,
            )

    def test_min_win_rate_rejects_out_of_range(self):
        """min_win_rate must be in [0.0, 1.0]."""
        with pytest.raises(ValueError, match="min_win_rate must be"):
            ScalpThresholds(
                min_expected_r=0.15,
                max_drawdown_r=-2.0,
                min_win_rate=-0.1,
                cost_stress_multiplier=2.5,
                latency_max_ms=200,
                funding_sensitivity=FundingSensitivity.HIGH,
            )

        with pytest.raises(ValueError, match="min_win_rate must be"):
            ScalpThresholds(
                min_expected_r=0.15,
                max_drawdown_r=-2.0,
                min_win_rate=1.5,
                cost_stress_multiplier=2.5,
                latency_max_ms=200,
                funding_sensitivity=FundingSensitivity.HIGH,
            )

    def test_cost_stress_multiplier_rejects_below_one(self):
        """cost_stress_multiplier must be >= 1.0."""
        with pytest.raises(
            ValueError, match="cost_stress_multiplier must be >= 1.0"
        ):
            ScalpThresholds(
                min_expected_r=0.15,
                max_drawdown_r=-2.0,
                min_win_rate=0.45,
                cost_stress_multiplier=0.5,
                latency_max_ms=200,
                funding_sensitivity=FundingSensitivity.HIGH,
            )

    def test_latency_max_ms_rejects_non_positive(self):
        """latency_max_ms must be > 0."""
        with pytest.raises(ValueError, match="latency_max_ms must be > 0"):
            ScalpThresholds(
                min_expected_r=0.15,
                max_drawdown_r=-2.0,
                min_win_rate=0.45,
                cost_stress_multiplier=2.5,
                latency_max_ms=0,
                funding_sensitivity=FundingSensitivity.HIGH,
            )

        with pytest.raises(ValueError, match="latency_max_ms must be > 0"):
            ScalpThresholds(
                min_expected_r=0.15,
                max_drawdown_r=-2.0,
                min_win_rate=0.45,
                cost_stress_multiplier=2.5,
                latency_max_ms=-10,
                funding_sensitivity=FundingSensitivity.HIGH,
            )

    def test_scalp_thresholds_immutable(self):
        """ScalpThresholds is frozen — setting attributes fails."""
        with pytest.raises(Exception):
            SCALP_THRESHOLDS.min_expected_r = 0.99  # type: ignore

    def test_optional_fields_have_defaults(self):
        """Position size and stop/target multipliers have SCALP-appropriate defaults."""
        defaults = ScalpThresholds(
            min_expected_r=0.15,
            max_drawdown_r=-2.0,
            min_win_rate=0.45,
            cost_stress_multiplier=2.5,
            latency_max_ms=200,
            funding_sensitivity=FundingSensitivity.HIGH,
        )
        assert defaults.max_position_size_pct == 5.0
        assert defaults.stop_multiplier == 1.5
        assert defaults.target_multiplier == 1.5


# ── Computed properties ────────────────────────────────────────────────

class TestScalpThresholdsProperties:
    """Test derived/computed properties on ScalpThresholds."""

    def test_reward_risk_ratio(self):
        """Implied R:R ratio is target / stop."""
        t = ScalpThresholds(
            min_expected_r=0.15,
            max_drawdown_r=-2.0,
            min_win_rate=0.45,
            cost_stress_multiplier=2.5,
            latency_max_ms=200,
            funding_sensitivity=FundingSensitivity.HIGH,
            target_multiplier=3.0,
            stop_multiplier=2.0,
        )
        assert t.reward_risk_ratio == pytest.approx(1.5)

    def test_canonical_reward_risk_is_one(self):
        """Canonical SCALP thresholds have 1:1 target:stop ratio (1.5/1.5 = 1.0).

        This is intentional for conservative baseline — scalping with 1:1
        requires higher win rate or smaller edge.
        """
        assert SCALP_THRESHOLDS.reward_risk_ratio == pytest.approx(1.0)

    def test_is_cost_sensitive(self):
        """SCALP is cost-sensitive (multiplier >= 2.0)."""
        assert SCALP_THRESHOLDS.is_cost_sensitive is True

        not_sensitive = ScalpThresholds(
            min_expected_r=0.35,
            max_drawdown_r=-5.0,
            min_win_rate=0.55,
            cost_stress_multiplier=1.0,
            latency_max_ms=500,
            funding_sensitivity=FundingSensitivity.LOW,
        )
        assert not_sensitive.is_cost_sensitive is False

    def test_is_latency_sensitive(self):
        """SCALP is latency-sensitive (<= 200ms)."""
        assert SCALP_THRESHOLDS.is_latency_sensitive is True

        not_sensitive = ScalpThresholds(
            min_expected_r=0.35,
            max_drawdown_r=-5.0,
            min_win_rate=0.55,
            cost_stress_multiplier=1.0,
            latency_max_ms=500,
            funding_sensitivity=FundingSensitivity.LOW,
        )
        assert not_sensitive.is_latency_sensitive is False

    def test_stress_cost_multiplier_alias(self):
        """stress_cost_multiplier property mirrors cost_stress_multiplier."""
        assert SCALP_THRESHOLDS.stress_cost_multiplier == 2.5

    def test_to_dict(self):
        """to_dict() returns a plain dict with all fields."""
        d = SCALP_THRESHOLDS.to_dict()
        assert isinstance(d, dict)
        assert d["min_expected_r"] == 0.15
        assert d["max_drawdown_r"] == -2.0
        assert d["min_win_rate"] == 0.45
        assert d["cost_stress_multiplier"] == 2.5
        assert d["latency_max_ms"] == 200
        assert d["funding_sensitivity"] == "HIGH"
        assert d["max_position_size_pct"] == 5.0
        assert d["stop_multiplier"] == 1.5
        assert d["target_multiplier"] == 1.5
        # Verify all keys present
        expected_keys = {
            "min_expected_r", "max_drawdown_r", "min_win_rate",
            "cost_stress_multiplier", "latency_max_ms",
            "funding_sensitivity", "max_position_size_pct",
            "stop_multiplier", "target_multiplier",
        }
        assert set(d.keys()) == expected_keys


# ── validate_scalp function ────────────────────────────────────────────

class TestValidateScalp:
    """Test the validate_scalp() trade candidate validation function."""

    def test_all_passing_candidate(self):
        """A candidate that meets all thresholds passes."""
        passed, failures = validate_scalp(
            expected_r_net=0.25,
            drawdown_r=-0.5,
            win_rate=0.55,
            latency_ms=120,
        )
        assert passed is True
        assert failures == []

    def test_expected_r_net_below_minimum(self):
        """expected_r_net below min_expected_r fails."""
        passed, failures = validate_scalp(
            expected_r_net=0.05,
            drawdown_r=-0.5,
            win_rate=0.55,
            latency_ms=120,
        )
        assert passed is False
        assert len(failures) == 1
        assert "expected_r_net" in failures[0]
        assert "0.15" in failures[0]

    def test_expected_r_net_exactly_at_minimum(self):
        """expected_r_net == min_expected_r passes (boundary)."""
        passed, failures = validate_scalp(
            expected_r_net=0.15,
            drawdown_r=-0.5,
            win_rate=0.55,
            latency_ms=120,
        )
        assert passed is True

    def test_drawdown_exceeds_maximum(self):
        """Session drawdown exceeding max_drawdown_r fails."""
        passed, failures = validate_scalp(
            expected_r_net=0.25,
            drawdown_r=-3.5,  # Below -2.0 max
            win_rate=0.55,
            latency_ms=120,
        )
        assert passed is False
        assert len(failures) == 1
        assert "drawdown" in failures[0].lower()

    def test_win_rate_below_minimum(self):
        """Win rate below min_win_rate fails."""
        passed, failures = validate_scalp(
            expected_r_net=0.25,
            drawdown_r=-0.5,
            win_rate=0.35,
            latency_ms=120,
        )
        assert passed is False
        assert len(failures) == 1
        assert "win_rate" in failures[0]

    def test_latency_exceeds_maximum(self):
        """Latency above latency_max_ms fails."""
        passed, failures = validate_scalp(
            expected_r_net=0.25,
            drawdown_r=-0.5,
            win_rate=0.55,
            latency_ms=450,
        )
        assert passed is False
        assert len(failures) == 1
        assert "latency" in failures[0]

    def test_multiple_failures(self):
        """Multiple threshold violations return all failures."""
        passed, failures = validate_scalp(
            expected_r_net=0.02,
            drawdown_r=-5.0,
            win_rate=0.30,
            latency_ms=500,
        )
        assert passed is False
        assert len(failures) == 4

    def test_negative_expected_r_net(self):
        """Negative expected_r_net always fails."""
        passed, failures = validate_scalp(
            expected_r_net=-0.10,
            drawdown_r=-0.5,
            win_rate=0.55,
            latency_ms=120,
        )
        assert passed is False
        assert len(failures) == 1

    def test_zero_win_rate(self):
        """Zero win rate always fails."""
        passed, failures = validate_scalp(
            expected_r_net=0.25,
            drawdown_r=-0.5,
            win_rate=0.0,
            latency_ms=120,
        )
        assert passed is False


# ── Integration / comparison ───────────────────────────────────────────

class TestScalpVsSwing:
    """Verify SCALP thresholds are appropriately tighter than SWING."""

    def test_scalp_min_expected_r_lower_than_swing(self):
        """SCALP targets smaller per-trade edge than SWING (0.15 < 0.35)."""
        assert SCALP_THRESHOLDS.min_expected_r < 0.35  # SWING min_action_edge_r

    def test_scalp_cost_stress_higher_than_swing_implied(self):
        """SCALP cost stress (2.5) is higher than SWING's implied ~1.5x."""
        assert SCALP_THRESHOLDS.cost_stress_multiplier > 1.5

    def test_scalp_stop_tighter_than_swing(self):
        """SCALP stop_multiplier (1.5) is tighter than SWING (2.0)."""
        assert SCALP_THRESHOLDS.stop_multiplier < 2.0


# ── FundingSensitivity enum ────────────────────────────────────────────

class TestFundingSensitivity:
    """Test the FundingSensitivity enum."""

    def test_enum_values(self):
        """All four sensitivity levels exist."""
        assert FundingSensitivity.LOW.value == "LOW"
        assert FundingSensitivity.MEDIUM.value == "MEDIUM"
        assert FundingSensitivity.HIGH.value == "HIGH"
        assert FundingSensitivity.VERY_HIGH.value == "VERY_HIGH"

    def test_high_is_greater_than_low(self):
        """HIGH sensitivity is a stricter level than LOW."""
        levels = {
            FundingSensitivity.LOW: 1,
            FundingSensitivity.MEDIUM: 2,
            FundingSensitivity.HIGH: 3,
            FundingSensitivity.VERY_HIGH: 4,
        }
        assert levels[FundingSensitivity.HIGH] > levels[FundingSensitivity.LOW]
        assert levels[FundingSensitivity.HIGH] > levels[FundingSensitivity.MEDIUM]
        assert levels[FundingSensitivity.VERY_HIGH] > levels[FundingSensitivity.HIGH]
