"""Tests for v7.rollback_manager — rollback and kill-switch hardening."""

import pytest

from v7.rollback_manager import (
    ArtifactBundle,
    KillSwitch,
    KillSwitchManager,
    RollbackManager,
)


class TestArtifactBundle:
    """Test ArtifactBundle dataclass."""

    def test_defaults(self):
        """ArtifactBundle should have sensible defaults."""
        bundle = ArtifactBundle(version="1.0.0", scope="swing_v1")
        assert bundle.version == "1.0.0"
        assert bundle.scope == "swing_v1"
        assert bundle.gates_results == {}
        assert bundle.compatible_with == set()

    def test_immutable(self):
        """ArtifactBundle should be frozen."""
        bundle = ArtifactBundle(version="1.0", scope="test")
        with pytest.raises(Exception):
            bundle.version = "2.0"  # type: ignore


class TestRollbackManager:
    """Test RollbackManager."""

    def _make_bundle(self, version, scope="swing_v1", gates=None, compat=None):
        return ArtifactBundle(
            version=version,
            scope=scope,
            gates_results=gates or {},
            compatible_with=set(compat or []),
        )

    def test_register_and_get_active(self):
        """Registering an artifact should make it active."""
        mgr = RollbackManager()
        bundle = self._make_bundle("1.0.0", "swing_v1")
        mgr.register_artifact(bundle)
        assert mgr.get_active_version("swing_v1") == "1.0.0"

    def test_register_rejects_empty_version(self):
        """Empty version should raise ValueError."""
        mgr = RollbackManager()
        with pytest.raises(ValueError, match="non-empty"):
            mgr.register_artifact(self._make_bundle("", "swing_v1"))

    def test_rollback_to_previous(self):
        """Rollback to a previous version should work."""
        mgr = RollbackManager()
        mgr.register_artifact(self._make_bundle("1.0.0", "swing_v1"))
        mgr.register_artifact(self._make_bundle("2.0.0", "swing_v1"))
        result = mgr.rollback("swing_v1", "1.0.0")
        assert result is not None
        assert result.version == "1.0.0"
        assert mgr.get_active_version("swing_v1") == "1.0.0"

    def test_rollback_nonexistent_returns_none(self):
        """Rollback to non-existent version should return None."""
        mgr = RollbackManager()
        mgr.register_artifact(self._make_bundle("1.0.0", "swing_v1"))
        result = mgr.rollback("swing_v1", "9.9.9")
        assert result is None

    def test_get_version_history(self):
        """Version history should return all registered versions."""
        mgr = RollbackManager()
        mgr.register_artifact(self._make_bundle("1.0.0", "swing_v1"))
        mgr.register_artifact(self._make_bundle("2.0.0", "swing_v1"))
        history = mgr.get_version_history("swing_v1")
        assert len(history) == 2
        assert history[0].version == "1.0.0"
        assert history[1].version == "2.0.0"

    def test_get_last_known_good_one_artifact(self):
        """With one artifact, last known good is that artifact."""
        mgr = RollbackManager()
        bundle = self._make_bundle("1.0.0", "swing_v1")
        mgr.register_artifact(bundle)
        lkg = mgr.get_last_known_good("swing_v1")
        assert lkg is not None
        assert lkg.version == "1.0.0"

    def test_get_last_known_good_with_history(self):
        """With multiple artifacts, last known good is the one before active."""
        mgr = RollbackManager()
        mgr.register_artifact(self._make_bundle("1.0.0", "swing_v1"))
        mgr.register_artifact(self._make_bundle("2.0.0", "swing_v1"))
        mgr.register_artifact(self._make_bundle("3.0.0", "swing_v1"))
        lkg = mgr.get_last_known_good("swing_v1")
        assert lkg is not None
        assert lkg.version == "2.0.0"  # The one before the active (3.0.0)

    def test_validate_compatibility_scope_mismatch(self):
        """Scope mismatch should fail compatibility."""
        b1 = self._make_bundle("1.0", "swing_v1")
        b2 = self._make_bundle("1.0", "scalp_v1")
        result = RollbackManager.validate_compatibility(b1, b2)
        assert result["compatible"] is False
        assert "scope_mismatch" in result["regressions"]

    def test_validate_compatibility_passes(self):
        """Compatible bundles should pass."""
        b1 = self._make_bundle("1.0", "swing_v1", compat=["2.0"])
        b2 = self._make_bundle("2.0", "swing_v1", compat=["1.0"])
        result = RollbackManager.validate_compatibility(b1, b2)
        assert result["compatible"] is True

    def test_validate_compatibility_regression(self):
        """Gate score regression should flag incompatibility."""
        b1 = self._make_bundle("1.0", "swing_v1", gates={
            "G2": {"score": 0.9},
            "G6": {"score": 0.85},
            "G7": {"score": 0.8},
        })
        b2 = self._make_bundle("2.0", "swing_v1", gates={
            "G2": {"score": 0.5},
            "G6": {"score": 0.4},
            "G7": {"score": 0.3},
        })
        result = RollbackManager.validate_compatibility(b1, b2)
        assert result["compatible"] is False
        assert any("G2" in r for r in result["regressions"])
        assert any("G6" in r for r in result["regressions"])

    def test_get_active_none_for_unknown_scope(self):
        """Unknown scope should return None."""
        mgr = RollbackManager()
        assert mgr.get_active_version("nonexistent") is None

    def test_get_last_known_good_none_for_empty(self):
        """Empty scope should return None."""
        mgr = RollbackManager()
        assert mgr.get_last_known_good("empty") is None


class TestKillSwitchManager:
    """Test KillSwitchManager."""

    def test_activate(self):
        """Activating kill switch should set active=True."""
        mgr = KillSwitchManager()
        switch = mgr.activate("swing_v1", reason="drawdown limit hit")
        assert switch.active is True
        assert switch.scope == "swing_v1"
        assert switch.reason == "drawdown limit hit"

    def test_deactivate(self):
        """Deactivating kill switch should set active=False."""
        mgr = KillSwitchManager()
        mgr.activate("swing_v1")
        switch = mgr.deactivate("swing_v1")
        assert switch is not None
        assert switch.active is False

    def test_is_active(self):
        """is_active should reflect current state."""
        mgr = KillSwitchManager()
        assert mgr.is_active("swing_v1") is False
        mgr.activate("swing_v1")
        assert mgr.is_active("swing_v1") is True
        mgr.deactivate("swing_v1")
        assert mgr.is_active("swing_v1") is False

    def test_deactivate_nonexistent(self):
        """Deactivating non-existent switch should return None."""
        mgr = KillSwitchManager()
        result = mgr.deactivate("nonexistent")
        assert result is None

    def test_get_switch(self):
        """get_switch should return the switch state."""
        mgr = KillSwitchManager()
        mgr.activate("swing_v1", reason="test")
        switch = mgr.get_switch("swing_v1")
        assert switch is not None
        assert switch.reason == "test"

    def test_get_switch_nonexistent(self):
        """get_switch for unknown scope should return None."""
        mgr = KillSwitchManager()
        assert mgr.get_switch("unknown") is None

    def test_active_scopes(self):
        """active_scopes should list only active scopes."""
        mgr = KillSwitchManager()
        mgr.activate("swing_v1")
        mgr.activate("scalp_v1")
        mgr.activate("agg_v1")
        mgr.deactivate("scalp_v1")
        active = mgr.active_scopes()
        assert "swing_v1" in active
        assert "scalp_v1" not in active
        assert "agg_v1" in active
        assert len(active) == 2


class TestKillSwitch:
    """Test KillSwitch dataclass."""

    def test_defaults(self):
        """Default KillSwitch should be inactive."""
        ks = KillSwitch()
        assert ks.active is False
        assert ks.scope == ""

    def test_immutable(self):
        """KillSwitch should be frozen."""
        ks = KillSwitch(active=True, scope="test")
        with pytest.raises(Exception):
            ks.active = False  # type: ignore
