"""Tests for v7.features.spec — FeatureSpec per-mode correctness and no-lookahead.

Feature groups: returns, volatility, atr, momentum, volume, breakout.
Modes: SWING (4h), SCALP (1h), AGGRESSIVE_SCALP (15m).

Rules verified:
  1. Each mode has exactly 6 feature groups.
  2. All lookback windows are positive integers.
  3. All lookback windows use the mode's primary interval — no cross-interval crosstalk.
  4. SWING windows >= SCALP windows >= AGGRESSIVE_SCALP windows (longer horizon,
     larger windows; tighter horizon, smaller windows).
  5. No zero-length or negative lookback bars.
  6. No future bars — all windows are trailing (lookback), not forward.
  7. get_feature_spec returns correct spec per mode.
  8. Unknown mode raises ValueError.
  9. FeatureSpec instances are frozen (immutable).
 10. FeatureSpec registration integrity.
"""

from __future__ import annotations

import dataclasses

import pytest

from v7.features.spec import (
    FeatureGroupWindows,
    FeatureSpec,
    get_feature_spec,
    SWING_SPEC,
    SCALP_SPEC,
    AGGRESSIVE_SPEC,
    SWING_RETURN_WINDOWS,
    SCALP_RETURN_WINDOWS,
    AGGRESSIVE_RETURN_WINDOWS,
    SWING_VOLATILITY_WINDOWS,
    SCALP_VOLATILITY_WINDOWS,
    AGGRESSIVE_VOLATILITY_WINDOWS,
    SWING_ATR_WINDOWS,
    SCALP_ATR_WINDOWS,
    AGGRESSIVE_ATR_WINDOWS,
    SWING_MOMENTUM_WINDOWS,
    SCALP_MOMENTUM_WINDOWS,
    AGGRESSIVE_MOMENTUM_WINDOWS,
    SWING_VOLUME_WINDOWS,
    SCALP_VOLUME_WINDOWS,
    AGGRESSIVE_VOLUME_WINDOWS,
    SWING_BREAKOUT_WINDOWS,
    SCALP_BREAKOUT_WINDOWS,
    AGGRESSIVE_BREAKOUT_WINDOWS,
)

# ── Test data ─────────────────────────────────────────────────────────

ALL_MODES = ("SWING", "SCALP", "AGGRESSIVE_SCALP")
ALL_SPECS = (SWING_SPEC, SCALP_SPEC, AGGRESSIVE_SPEC)
GROUP_NAMES = ("returns", "volatility", "atr", "momentum", "volume", "breakout")


# ── FeatureGroupWindows unit tests ────────────────────────────────────

class TestFeatureGroupWindows:
    """Unit tests for FeatureGroupWindows frozen dataclass."""

    def test_construction_and_fields(self):
        fgw = FeatureGroupWindows(
            name="returns",
            primary_interval="4h",
            lookback_bars=(1, 3, 5),
            description="Returns",
        )
        assert fgw.name == "returns"
        assert fgw.primary_interval == "4h"
        assert fgw.lookback_bars == (1, 3, 5)
        assert fgw.description == "Returns"

    def test_frozen(self):
        """FeatureGroupWindows must be immutable."""
        fgw = FeatureGroupWindows(
            name="returns",
            primary_interval="4h",
            lookback_bars=(1, 3),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            fgw.name = "volatility"  # type: ignore[misc]

    def test_default_context_intervals(self):
        fgw = FeatureGroupWindows(
            name="returns",
            primary_interval="4h",
            lookback_bars=(1,),
        )
        assert fgw.context_intervals == ()

    def test_default_description(self):
        fgw = FeatureGroupWindows(
            name="returns",
            primary_interval="4h",
            lookback_bars=(1,),
        )
        assert fgw.description == ""


# ── FeatureSpec structural tests ──────────────────────────────────────

class TestFeatureSpecStructure:
    """Verify FeatureSpec structural integrity across all modes."""

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_mode_is_non_empty(self, spec: FeatureSpec) -> None:
        assert spec.mode

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_primary_interval_is_non_empty(self, spec: FeatureSpec) -> None:
        assert spec.primary_interval

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_refinement_interval_is_non_empty(self, spec: FeatureSpec) -> None:
        assert spec.refinement_interval

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_schema_version(self, spec: FeatureSpec) -> None:
        assert spec.schema_version == "1.0.0"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_six_feature_groups_present(self, spec: FeatureSpec) -> None:
        for group_name in GROUP_NAMES:
            group = getattr(spec, group_name)
            assert isinstance(group, FeatureGroupWindows), (
                f"{spec.mode}.{group_name} is not a FeatureGroupWindows"
            )
            assert group.name == group_name

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_all_groups_use_primary_interval(self, spec: FeatureSpec) -> None:
        """No group may use a different interval from the spec's primary."""
        for group_name in GROUP_NAMES:
            group = getattr(spec, group_name)
            assert group.primary_interval == spec.primary_interval, (
                f"{spec.mode}.{group_name} uses interval {group.primary_interval}, "
                f"expected {spec.primary_interval}"
            )

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_all_lookback_bars_positive(self, spec: FeatureSpec) -> None:
        """No lookback window may be zero or negative."""
        for group_name in GROUP_NAMES:
            group = getattr(spec, group_name)
            for w in group.lookback_bars:
                assert w > 0, (
                    f"{spec.mode}.{group_name} has non-positive lookback bar {w}"
                )

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_all_lookback_bars_are_integers(self, spec: FeatureSpec) -> None:
        for group_name in GROUP_NAMES:
            group = getattr(spec, group_name)
            for w in group.lookback_bars:
                assert isinstance(w, int), (
                    f"{spec.mode}.{group_name} has non-int lookback {w}"
                )

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_no_duplicate_windows_in_group(self, spec: FeatureSpec) -> None:
        """Each feature group should have unique lookback windows."""
        for group_name in GROUP_NAMES:
            group = getattr(spec, group_name)
            assert len(group.lookback_bars) == len(set(group.lookback_bars)), (
                f"{spec.mode}.{group_name} has duplicate lookback bars"
            )

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_lookback_bars_are_sorted(self, spec: FeatureSpec) -> None:
        """Lookback windows should be monotonically increasing."""
        for group_name in GROUP_NAMES:
            group = getattr(spec, group_name)
            assert list(group.lookback_bars) == sorted(group.lookback_bars), (
                f"{spec.mode}.{group_name} lookback bars not sorted"
            )

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_context_intervals_are_non_empty(self, spec: FeatureSpec) -> None:
        assert len(spec.context_intervals) > 0

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_business_priority_defined(self, spec: FeatureSpec) -> None:
        assert spec.business_priority in (
            "PRIMARY",
            "SECONDARY_BASELINE",
        ), f"{spec.mode}: unexpected business_priority '{spec.business_priority}'"

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_threshold_status_defined(self, spec: FeatureSpec) -> None:
        assert spec.threshold_status in (
            "LOCKED_INITIAL_BASELINE",
            "HOLD",
        ), f"{spec.mode}: unexpected threshold_status '{spec.threshold_status}'"


# ── No-lookahead (all windows are trailing) ───────────────────────────

class TestNoLookahead:
    """Feature windows must be trailing (past bars), not forward."""

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_windows_are_trailing(self, spec: FeatureSpec) -> None:
        """All lookback windows face backward, never forward.

        Concretely: window values represent how many bars BACK to look,
        not how many bars forward. There is no field in FeatureSpec or
        FeatureGroupWindows that projects into the future.
        """
        for group_name in GROUP_NAMES:
            group = getattr(spec, group_name)
            # The 'lookback_bars' field name itself encodes the direction.
            # Verify no forward-looking field exists.
            for field in dataclasses.fields(group):
                if "forward" in field.name.lower() or "future" in field.name.lower():
                    pytest.fail(
                        f"{spec.mode}.{group_name} has forward-looking field "
                        f"'{field.name}'"
                    )

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_no_future_reference_in_spec(self, spec: FeatureSpec) -> None:
        """FeatureSpec itself must have no future-reference fields."""
        for field in dataclasses.fields(spec):
            if "forward" in field.name.lower() or "future" in field.name.lower():
                pytest.fail(
                    f"{spec.mode} FeatureSpec has forward-looking field "
                    f"'{field.name}'"
                )


# ── Mode-specific timeframe correctness ───────────────────────────────

class TestModeSpecificTimeframes:
    """Each mode's timeframes match the locked architecture."""

    def test_swing_timeframes(self):
        assert SWING_SPEC.primary_interval == "4h"
        assert set(SWING_SPEC.context_intervals) == {"1d", "1h"}
        assert SWING_SPEC.refinement_interval == "1h"

    def test_scalp_timeframes(self):
        assert SCALP_SPEC.primary_interval == "1h"
        assert set(SCALP_SPEC.context_intervals) == {"4h", "15m"}
        assert SCALP_SPEC.refinement_interval == "15m"

    def test_aggressive_scalp_timeframes(self):
        assert AGGRESSIVE_SPEC.primary_interval == "15m"
        assert set(AGGRESSIVE_SPEC.context_intervals) == {"1h", "5m"}
        assert AGGRESSIVE_SPEC.refinement_interval == "5m"


# ── Window sizing: SWING >= SCALP >= AGGRESSIVE_SCALP ────────────────

class TestWindowSizing:
    """Longer-horizon modes cover more calendar time, even if bar counts differ.

    Windows are compared in wall-clock hours (bars * hours_per_bar), not raw
    bar counts, because the modes use different primary intervals:
      - SWING:    4h bars
      - SCALP:    1h bars
      - AGGRESSIVE_SCALP: 15m bars (0.25h)

    This is a sanity check, not a hard architectural constraint — but if it
    breaks, it signals a likely misconfiguration.
    """

    @staticmethod
    def _hours_per_bar(interval: str) -> float:
        """Convert a primary interval string like '4h', '1h', '15m' to hours."""
        interval = interval.strip().lower()
        if interval.endswith("h"):
            return float(interval[:-1])
        if interval.endswith("m"):
            return float(interval[:-1]) / 60.0
        if interval.endswith("d"):
            return float(interval[:-1]) * 24.0
        raise ValueError(f"Unknown interval format: {interval!r}")

    def _longest_hours(self, spec: FeatureSpec, group_name: str) -> float:
        group = getattr(spec, group_name)
        bars = max(group.lookback_bars)
        hpb = self._hours_per_bar(spec.primary_interval)
        return bars * hpb

    @pytest.mark.parametrize("group_name", GROUP_NAMES)
    def test_swing_longest_window_hours_gte_scalp(self, group_name: str):
        sw_h = self._longest_hours(SWING_SPEC, group_name)
        sc_h = self._longest_hours(SCALP_SPEC, group_name)
        assert sw_h >= sc_h, (
            f"{group_name}: SWING longest window {sw_h:.1f}h"
            f" < SCALP {sc_h:.1f}h"
        )

    @pytest.mark.parametrize("group_name", GROUP_NAMES)
    def test_scalp_longest_window_hours_gte_aggressive(self, group_name: str):
        sc_h = self._longest_hours(SCALP_SPEC, group_name)
        ag_h = self._longest_hours(AGGRESSIVE_SPEC, group_name)
        assert sc_h >= ag_h, (
            f"{group_name}: SCALP longest window {sc_h:.1f}h"
            f" < AGGRESSIVE_SCALP {ag_h:.1f}h"
        )


# ── get_feature_spec helper ───────────────────────────────────────────

class TestGetFeatureSpec:
    """Tests for the convenience accessor get_feature_spec()."""

    @pytest.mark.parametrize("mode", ALL_MODES)
    def test_returns_correct_spec(self, mode: str):
        spec = get_feature_spec(mode)
        assert spec.mode == mode

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            get_feature_spec("DAY_TRADING")

    def test_empty_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            get_feature_spec("")


# ── Immutability ──────────────────────────────────────────────────────

class TestImmutability:
    """FeatureSpec instances must be frozen."""

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_spec_is_frozen(self, spec: FeatureSpec):
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.mode = "NEW_MODE"  # type: ignore[misc]

    @pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.mode)
    def test_groups_cannot_be_mutated(self, spec: FeatureSpec):
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.returns = FeatureGroupWindows(  # type: ignore[misc]
                name="returns", primary_interval="1h", lookback_bars=(999,)
            )


# ── Registration integrity ────────────────────────────────────────────

class TestRegistration:
    """The global FeatureSpec registry must be internally consistent."""

    def test_all_three_modes_registered(self):
        assert FeatureSpec.all_modes() == ("AGGRESSIVE_SCALP", "SCALP", "SWING")

    def test_get_all_returns_three_specs(self):
        all_specs = FeatureSpec.get_all()
        assert len(all_specs) == 3
        for mode in ALL_MODES:
            assert mode in all_specs

    def test_get_all_is_a_copy(self):
        d1 = FeatureSpec.get_all()
        d2 = FeatureSpec.get_all()
        assert d1 is not d2
        assert d1 == d2

    def test_same_spec_identity_per_mode(self):
        assert FeatureSpec.get("SWING") is SWING_SPEC
        assert FeatureSpec.get("SCALP") is SCALP_SPEC
        assert FeatureSpec.get("AGGRESSIVE_SCALP") is AGGRESSIVE_SPEC


# ── Concrete window value tests (regression) ─────────────────────────

class TestConcreteWindows:
    """Verify the exact window values match the locked per-mode design."""

    def test_swing_window_values(self):
        assert SWING_RETURN_WINDOWS == (1, 3, 6, 12, 18, 30)
        assert SWING_VOLATILITY_WINDOWS == (20,)
        assert SWING_ATR_WINDOWS == (14,)
        assert SWING_MOMENTUM_WINDOWS == (6, 12, 18, 30)
        assert SWING_VOLUME_WINDOWS == (12, 30)
        assert SWING_BREAKOUT_WINDOWS == (20,)

    def test_scalp_window_values(self):
        assert SCALP_RETURN_WINDOWS == (1, 4, 12, 24, 48)
        assert SCALP_VOLATILITY_WINDOWS == (24,)
        assert SCALP_ATR_WINDOWS == (14,)
        assert SCALP_MOMENTUM_WINDOWS == (4, 12, 24)
        assert SCALP_VOLUME_WINDOWS == (12, 24)
        assert SCALP_BREAKOUT_WINDOWS == (24,)

    def test_aggressive_window_values(self):
        assert AGGRESSIVE_RETURN_WINDOWS == (1, 4, 12, 24, 48)
        assert AGGRESSIVE_VOLATILITY_WINDOWS == (24,)
        assert AGGRESSIVE_ATR_WINDOWS == (10,)
        assert AGGRESSIVE_MOMENTUM_WINDOWS == (4, 12, 24)
        assert AGGRESSIVE_VOLUME_WINDOWS == (12, 24)
        assert AGGRESSIVE_BREAKOUT_WINDOWS == (12,)


# ── Mode priorities ───────────────────────────────────────────────────

class TestModePriorities:
    """Business priority and threshold status from roadmap."""

    def test_swing_is_secondary_baseline(self):
        assert SWING_SPEC.business_priority == "SECONDARY_BASELINE"
        assert SWING_SPEC.threshold_status == "LOCKED_INITIAL_BASELINE"

    def test_scalp_is_primary_hold(self):
        assert SCALP_SPEC.business_priority == "PRIMARY"
        assert SCALP_SPEC.threshold_status == "HOLD"

    def test_aggressive_is_primary_hold(self):
        assert AGGRESSIVE_SPEC.business_priority == "PRIMARY"
        assert AGGRESSIVE_SPEC.threshold_status == "HOLD"
