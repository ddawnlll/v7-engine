"""Tests for AlphaForge Regime Filter.

Covers:
  (a) Basic filtering rules: CUSUM, HMM vol state, volatility regime
  (b) Mode-specific thresholds
  (c) Filter breakdown diagnostics
  (d) PBO guard validation hooks
  (e) Edge cases: NaN, empty, length mismatch
  (f) Determinism
"""

import sys
from pathlib import Path

import numpy as np
import pytest

_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from alphaforge.features.regime_filter import (
    SWING_VOL_REGIME_BLOCK,
    SCALP_VOL_REGIME_BLOCK,
    AGGRESSIVE_SCALP_VOL_REGIME_BLOCK,
    compute_regime_filter,
    compute_filter_breakdown,
    validate_regime_filter_conditions,
)


# ===========================================================================
# Helper: make regime features
# ===========================================================================


def _make_regime_features(
    n: int = 100,
    cusum_pct: float = 0.1,
    hmm_high_pct: float = 0.2,
    high_vol_pct: float = 0.15,
    seed: int = 42,
) -> dict:
    """Generate synthetic regime features with controlled blocking rates."""
    rng = np.random.RandomState(seed)
    cusum = np.zeros(n, dtype=np.float64)
    hmm = np.zeros(n, dtype=np.float64)
    vol = np.ones(n, dtype=np.float64)  # default MEDIUM

    # Set some bars to trigger signals
    cusum[rng.rand(n) < cusum_pct] = 1.0
    hmm[rng.rand(n) < hmm_high_pct] = 1.0
    vol[rng.rand(n) < high_vol_pct] = 2.0  # HIGH

    return {"cusum_signal": cusum, "hmm_vol_state": hmm, "volatility_regime": vol}


class TestBasicFiltering:
    """Core filtering rules."""

    def test_all_allowed_by_default(self):
        """When all features are clean, all bars are allowed."""
        n = 50
        cusum = np.zeros(n, dtype=np.float64)
        hmm = np.zeros(n, dtype=np.float64)
        vol = np.ones(n, dtype=np.float64)  # MEDIUM
        result = compute_regime_filter(cusum, hmm, vol, mode="SWING")
        assert np.all(result)
        assert len(result) == n

    def test_cusum_blocks(self):
        """Bars with cusum_signal==1 should be blocked."""
        n = 20
        cusum = np.zeros(n, dtype=np.float64)
        cusum[5] = 1.0
        cusum[10] = 1.0
        hmm = np.zeros(n, dtype=np.float64)
        vol = np.ones(n, dtype=np.float64)
        result = compute_regime_filter(cusum, hmm, vol, mode="SWING")
        assert result[5] == False
        assert result[10] == False
        assert result[0] == True

    def test_hmm_high_vol_blocks(self):
        """Bars with hmm_vol_state==1 should be blocked."""
        n = 20
        cusum = np.zeros(n, dtype=np.float64)
        hmm = np.zeros(n, dtype=np.float64)
        hmm[7] = 1.0
        hmm[15] = 1.0
        vol = np.ones(n, dtype=np.float64)
        result = compute_regime_filter(cusum, hmm, vol, mode="SWING")
        assert result[7] == False
        assert result[15] == False
        assert result[0] == True

    def test_high_vol_regime_blocks_swing(self):
        """HIGH volatility regime (2.0) should be blocked in SWING."""
        n = 20
        cusum = np.zeros(n, dtype=np.float64)
        hmm = np.zeros(n, dtype=np.float64)
        vol = np.ones(n, dtype=np.float64)
        vol[3] = 2.0
        result = compute_regime_filter(cusum, hmm, vol, mode="SWING")
        assert result[3] == False
        assert result[0] == True

    def test_medium_vol_allowed_in_swing(self):
        """MEDIUM volatility regime (1.0) should be allowed in SWING."""
        n = 10
        cusum = np.zeros(n, dtype=np.float64)
        hmm = np.zeros(n, dtype=np.float64)
        vol = np.ones(n, dtype=np.float64)  # MEDIUM
        result = compute_regime_filter(cusum, hmm, vol, mode="SWING")
        assert np.all(result)

    def test_medium_vol_blocked_in_aggressive_scalp(self):
        """MEDIUM+ volatility regime (1.0+) should be blocked in AGGRESSIVE_SCALP."""
        n = 10
        cusum = np.zeros(n, dtype=np.float64)
        hmm = np.zeros(n, dtype=np.float64)
        vol = np.ones(n, dtype=np.float64)  # MEDIUM
        result = compute_regime_filter(cusum, hmm, vol, mode="AGGRESSIVE_SCALP")
        assert not np.any(result)  # all blocked since vol_regime_block=1.0

    def test_hmm_probability_filter(self):
        """hmm_vol_probability > threshold should block."""
        n = 20
        cusum = np.zeros(n, dtype=np.float64)
        hmm = np.zeros(n, dtype=np.float64)
        vol = np.ones(n, dtype=np.float64)
        hmm_prob = np.full(n, 0.5, dtype=np.float64)
        hmm_prob[4] = 0.9
        hmm_prob[12] = 0.85
        result = compute_regime_filter(cusum, hmm, vol, hmm_vol_probability=hmm_prob, mode="SWING")
        assert result[4] == False
        assert result[12] == False
        assert result[0] == True  # 0.5 < 0.8 threshold

    def test_nan_handling(self):
        """NaN values should not cause errors and should be treated as allowed."""
        n = 20
        cusum = np.full(n, np.nan, dtype=np.float64)
        hmm = np.full(n, np.nan, dtype=np.float64)
        vol = np.full(n, np.nan, dtype=np.float64)
        result = compute_regime_filter(cusum, hmm, vol, mode="SWING")
        assert np.all(result)


class TestModeSpecific:
    """Mode-specific threshold differences."""

    def test_swing_mode_constants(self):
        """SWING should use correct constants."""
        assert SWING_VOL_REGIME_BLOCK == 2.0
        assert SCALP_VOL_REGIME_BLOCK == 1.5
        assert AGGRESSIVE_SCALP_VOL_REGIME_BLOCK == 1.0

    def test_scalp_blocks_medium_vol(self):
        """SCALP should block MEDIUM+ volatility (regime >= 1.5)."""
        n = 20
        cusum = np.zeros(n, dtype=np.float64)
        hmm = np.zeros(n, dtype=np.float64)
        vol = np.ones(n, dtype=np.float64)
        # Add some HIGH vol bars
        vol[5] = 2.0
        vol[10] = 1.5  # MEDIUM-high boundary
        result = compute_regime_filter(cusum, hmm, vol, mode="SCALP")
        assert result[5] == False  # HIGH blocked
        assert result[10] == False  # >= 1.5 blocked
        # MEDIUM (1.0) should be allowed in SCALP
        assert result[0] == True

    def test_overrides(self):
        """Threshold overrides should work."""
        n = 10
        cusum = np.zeros(n, dtype=np.float64)
        hmm = np.zeros(n, dtype=np.float64)
        vol = np.ones(n, dtype=np.float64)
        # Override vol_regime_block to 0.0 (block everything)
        result = compute_regime_filter(cusum, hmm, vol, mode="SWING", vol_regime_block=0.0)
        assert not np.any(result)

    def test_unknown_mode_raises(self):
        """Unknown mode should raise ValueError."""
        n = 10
        cusum = np.zeros(n, dtype=np.float64)
        hmm = np.zeros(n, dtype=np.float64)
        vol = np.ones(n, dtype=np.float64)
        with pytest.raises(ValueError, match="Unknown mode"):
            compute_regime_filter(cusum, hmm, vol, mode="UNKNOWN")


class TestLengthValidation:
    """Input length validation."""

    def test_length_mismatch_raises(self):
        """Mismatched array lengths should raise ValueError."""
        cusum = np.zeros(10, dtype=np.float64)
        hmm = np.zeros(10, dtype=np.float64)
        vol = np.ones(9, dtype=np.float64)
        with pytest.raises(ValueError, match="Length mismatch"):
            compute_regime_filter(cusum, hmm, vol, mode="SWING")

    def test_probability_length_mismatch_raises(self):
        """hmm_vol_probability length mismatch should raise ValueError."""
        cusum = np.zeros(10, dtype=np.float64)
        hmm = np.zeros(10, dtype=np.float64)
        vol = np.ones(10, dtype=np.float64)
        prob = np.zeros(5, dtype=np.float64)
        with pytest.raises(ValueError, match="hmm_vol_probability"):
            compute_regime_filter(cusum, hmm, vol, hmm_vol_probability=prob, mode="SWING")


class TestDeterminism:
    """Determinism guarantee."""

    def test_same_input_same_output(self):
        """Same input should produce identical output."""
        features = _make_regime_features(100, seed=42)
        r1 = compute_regime_filter(**features, mode="SWING")
        r2 = compute_regime_filter(**features, mode="SWING")
        assert np.array_equal(r1, r2)


class TestFilterBreakdown:
    """Filter breakdown diagnostics."""

    def test_breakdown_has_all_keys(self):
        """Breakdown should return all expected keys."""
        features = _make_regime_features(50)
        breakdown = compute_filter_breakdown(**features, mode="SWING")
        expected = {
            "blocked_by_cusum", "blocked_by_hmm_state",
            "blocked_by_vol_regime", "blocked_by_hmm_prob",
            "trade_allowed",
        }
        assert set(breakdown.keys()) == expected

    def test_breakdown_consistency(self):
        """Combined trade_allowed should match compute_regime_filter."""
        features = _make_regime_features(100)
        direct = compute_regime_filter(**features, mode="SWING")
        breakdown = compute_filter_breakdown(**features, mode="SWING")
        assert np.array_equal(direct, breakdown["trade_allowed"])


class TestPboGuard:
    """PBO guard validation hooks."""

    def test_all_allowed_passes(self):
        """When all bars are allowed, guard should pass."""
        n = 100
        trade_allowed = np.ones(n, dtype=bool)
        result = validate_regime_filter_conditions(trade_allowed, min_allowed_frac=0.1)
        assert result["within_bounds"]
        assert result["allowed_frac"] == 1.0
        assert result["pbo_warning"] == ""

    def test_most_blocked_triggers_warning(self):
        """When most bars are blocked, guard should warn."""
        n = 100
        trade_allowed = np.zeros(n, dtype=bool)
        trade_allowed[:5] = True  # only 5%
        result = validate_regime_filter_conditions(trade_allowed, min_allowed_frac=0.1)
        assert not result["within_bounds"]
        assert "PBO GUARD" in result["pbo_warning"]
        assert result["allowed_frac"] == 0.05

    def test_empty_array(self):
        """Empty array should return zeros with warning."""
        trade_allowed = np.array([], dtype=bool)
        result = validate_regime_filter_conditions(trade_allowed)
        assert result["n_total"] == 0
        assert result["pbo_warning"] != ""

    def test_exact_boundary_passes(self):
        """Exactly at min_allowed_frac should pass."""
        n = 100
        trade_allowed = np.zeros(n, dtype=bool)
        trade_allowed[:10] = True
        result = validate_regime_filter_conditions(trade_allowed, min_allowed_frac=0.1)
        assert result["within_bounds"]

    def test_fractional_allowed(self):
        """Verify fractional computation is correct."""
        n = 1000
        trade_allowed = np.zeros(n, dtype=bool)
        trade_allowed[:250] = True
        result = validate_regime_filter_conditions(trade_allowed, min_allowed_frac=0.2)
        assert abs(result["allowed_frac"] - 0.25) < 0.001
        assert result["within_bounds"]

    def test_mode_specific_thresholds_work(self):
        """End-to-end: regime filter with realistic data and guard."""
        features = _make_regime_features(200, cusum_pct=0.05, hmm_high_pct=0.1, high_vol_pct=0.1)
        allowed = compute_regime_filter(**features, mode="SWING")
        guard = validate_regime_filter_conditions(allowed, min_allowed_frac=0.5)
        # With ~25% blocks, 75% should be allowed
        assert guard["allowed_frac"] > 0.5
        assert guard["within_bounds"]
