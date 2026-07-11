"""Tests for simulation profile registry."""

import pytest

from simulation.profile_registry.registry import (
    get_profile,
    register_profile,
    list_profiles,
    profile_exists,
    SWING_V1_HASH,
    SCALP_V1_HASH,
    AGGRESSIVE_SCALP_V1_HASH,
)
from simulation.contracts.models import SimulationProfile, TradingMode


class TestProfileRegistry:
    """Profile registry correctness tests."""

    def test_get_swing_profile(self):
        """SWING profile resolves with correct defaults."""
        profile = get_profile("SWING")
        assert profile.mode == TradingMode.SWING
        assert profile.primary_interval == "4h"
        assert profile.profile_version == "1.0.0"

    def test_get_scalp_profile(self):
        """SCALP profile resolves with correct defaults."""
        profile = get_profile("SCALP")
        assert profile.mode == TradingMode.SCALP
        assert profile.primary_interval == "1h"
        assert profile.no_trade_default is True
        assert profile.stop_multiplier == 1.75

    def test_get_aggressive_scalp_profile(self):
        """AGGRESSIVE_SCALP profile resolves with correct defaults."""
        profile = get_profile("AGGRESSIVE_SCALP")
        assert profile.mode == TradingMode.AGGRESSIVE_SCALP
        assert profile.primary_interval == "15m"
        assert profile.max_holding_bars == 5

    def test_get_profile_by_version(self):
        """Explicit version lookup works."""
        profile = get_profile("SCALP", version="1.0.0")
        assert profile.profile_version == "1.0.0"

    def test_get_profile_unknown_mode_raises(self):
        """Unknown mode raises ValueError."""
        with pytest.raises(ValueError, match="Unknown profile mode"):
            get_profile("UNKNOWN_MODE")

    def test_get_profile_unknown_version_raises(self):
        """Unknown version raises ValueError."""
        with pytest.raises(ValueError, match="Unknown profile version"):
            get_profile("SWING", version="99.99.99")

    def test_hashes_are_deterministic(self):
        """Profile hashes are deterministic (same call = same hash)."""
        p1 = get_profile("SCALP")
        p2 = get_profile("SCALP")
        from simulation.profile_registry.registry import _compute_profile_hash
        assert _compute_profile_hash(p1) == _compute_profile_hash(p2)

    def test_swing_hash_not_empty(self):
        """SWING hash is a non-empty 16-char hex string."""
        assert isinstance(SWING_V1_HASH, str)
        assert len(SWING_V1_HASH) == 16
        int(SWING_V1_HASH, 16)  # should not raise

    def test_scalp_hash_not_empty(self):
        """SCALP hash is a non-empty 16-char hex string."""
        assert isinstance(SCALP_V1_HASH, str)
        assert len(SCALP_V1_HASH) == 16

    def test_aggressive_scalp_hash_not_empty(self):
        """AGGRESSIVE_SCALP hash is a non-empty 16-char hex string."""
        assert isinstance(AGGRESSIVE_SCALP_V1_HASH, str)
        assert len(AGGRESSIVE_SCALP_V1_HASH) == 16

    def test_list_profiles(self):
        """list_profiles returns all registered modes."""
        profiles = list_profiles()
        assert "SWING" in profiles
        assert "SCALP" in profiles
        assert "AGGRESSIVE_SCALP" in profiles
        assert "1.0.0" in profiles["SWING"]

    def test_profile_exists(self):
        """profile_exists returns correct boolean."""
        assert profile_exists("SWING") is True
        assert profile_exists("SWING", version="1.0.0") is True
        assert profile_exists("SWING", version="2.0.0") is False
        assert profile_exists("UNKNOWN") is False

    def test_register_duplicate_same_params_ok(self):
        """Registering same profile twice with same params is OK."""
        profile = get_profile("SCALP")
        # Re-registering the same version with same params should work
        register_profile(profile)  # no error

    def test_register_duplicate_different_params_raises(self):
        """Registering same version with different params raises."""
        modified = SimulationProfile(
            profile_version="1.0.0",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            max_holding_bars=99,  # different!
            stop_multiplier=1.75,
            target_multiplier=1.75,
            ambiguity_margin_r=0.10,
            min_action_edge_r=0.15,
            no_trade_default=True,
        )
        with pytest.raises(ValueError, match="Profile conflict"):
            register_profile(modified)
