"""Tests for v7.features — FeatureSpec per mode, no lookahead."""

import pytest

from v7.features import (
    FeatureGroup,
    FeatureSpec,
    MODE_FEATURE_SPECS,
    get_feature_spec,
    list_modes,
)
from v7.features.spec import check_no_lookahead


class TestFeatureGroup:
    """FeatureGroup dataclass basics."""

    def test_defaults(self):
        """Default short/medium/long windows."""
        g = FeatureGroup(name="returns")
        assert g.name == "returns"
        assert g.short_window == 1
        assert g.medium_window == 6
        assert g.long_window == 24
        assert g.extra == {}

    def test_custom_values(self):
        """Custom window parameters."""
        g = FeatureGroup(
            name="atr",
            short_window=14,
            medium_window=14,
            long_window=14,
            extra={"atr_multiplier": 2.0},
        )
        assert g.short_window == 14
        assert g.extra["atr_multiplier"] == 2.0

    def test_immutable(self):
        """FeatureGroup instances are frozen."""
        g = FeatureGroup(name="test")
        with pytest.raises(Exception):
            g.short_window = 99  # type: ignore


class TestFeatureSpec:
    """FeatureSpec dataclass basics."""

    def test_swing_spec(self):
        """SWING has primary 4h, context 1d, refinement 1h."""
        spec = MODE_FEATURE_SPECS["SWING"]
        assert spec.mode == "SWING"
        assert spec.primary_interval == "4h"
        assert "1d" in spec.context_intervals
        assert "1h" in spec.refinement_intervals

    def test_scalp_spec(self):
        """SCALP has primary 1h, context 4h, refinement 15m."""
        spec = MODE_FEATURE_SPECS["SCALP"]
        assert spec.mode == "SCALP"
        assert spec.primary_interval == "1h"
        assert "4h" in spec.context_intervals
        assert "15m" in spec.refinement_intervals

    def test_aggressive_scalp_spec(self):
        """AGGRESSIVE_SCALP has primary 15m, context 1h, refinement 5m."""
        spec = MODE_FEATURE_SPECS["AGGRESSIVE_SCALP"]
        assert spec.mode == "AGGRESSIVE_SCALP"
        assert spec.primary_interval == "15m"
        assert "1h" in spec.context_intervals
        assert "5m" in spec.refinement_intervals

    def test_get_group_found(self):
        """get_group returns the matching FeatureGroup."""
        spec = MODE_FEATURE_SPECS["SWING"]
        g = spec.get_group("returns")
        assert g is not None
        assert g.name == "returns"

    def test_get_group_not_found(self):
        """get_group returns None for unknown group."""
        spec = MODE_FEATURE_SPECS["SWING"]
        assert spec.get_group("nonexistent") is None

    def test_all_modes_have_six_groups(self):
        """Every mode has exactly 6 feature groups."""
        for mode, spec in MODE_FEATURE_SPECS.items():
            assert len(spec.groups) == 6, f"{mode} has {len(spec.groups)} groups, expected 6"

    def test_group_names_are_consistent(self):
        """All modes have the same 6 group names."""
        expected = {"returns", "volatility", "atr", "momentum", "volume", "breakout"}
        for mode, spec in MODE_FEATURE_SPECS.items():
            names = {g.name for g in spec.groups}
            assert names == expected, f"{mode} has groups {names}, expected {expected}"

    def test_swing_window_sizes(self):
        """SWING windows: short ~1 bar, medium ~6 bars, long ~24 bars."""
        spec = MODE_FEATURE_SPECS["SWING"]
        ret = spec.get_group("returns")
        assert ret is not None
        assert ret.short_window == 1
        assert ret.medium_window == 6
        assert ret.long_window == 24

    def test_scalp_window_sizes(self):
        """SCALP windows: short ~1 bar, medium ~4 bars, long ~24 bars."""
        spec = MODE_FEATURE_SPECS["SCALP"]
        ret = spec.get_group("returns")
        assert ret is not None
        assert ret.short_window == 1
        assert ret.medium_window == 4
        assert ret.long_window == 24

    def test_aggressive_scalp_window_sizes(self):
        """AGGRESSIVE_SCALP windows: short ~1 bar, medium ~4 bars, long ~16 bars."""
        spec = MODE_FEATURE_SPECS["AGGRESSIVE_SCALP"]
        ret = spec.get_group("returns")
        assert ret is not None
        assert ret.short_window == 1
        assert ret.medium_window == 4
        assert ret.long_window == 16

    def test_atr_multiplier_varies_by_mode(self):
        """ATR multiplier decreases from SWING -> SCALP -> AGGRESSIVE_SCALP."""
        swing_atr = MODE_FEATURE_SPECS["SWING"].get_group("atr")
        scalp_atr = MODE_FEATURE_SPECS["SCALP"].get_group("atr")
        aggr_atr = MODE_FEATURE_SPECS["AGGRESSIVE_SCALP"].get_group("atr")
        assert swing_atr is not None and scalp_atr is not None and aggr_atr is not None
        assert swing_atr.extra["atr_multiplier"] > scalp_atr.extra["atr_multiplier"]
        assert scalp_atr.extra["atr_multiplier"] > aggr_atr.extra["atr_multiplier"]

    def test_breakout_confirmation_bars(self):
        """SWING has higher confirmation bars than scalp modes."""
        swing_bo = MODE_FEATURE_SPECS["SWING"].get_group("breakout")
        aggr_bo = MODE_FEATURE_SPECS["AGGRESSIVE_SCALP"].get_group("breakout")
        assert swing_bo is not None and aggr_bo is not None
        assert swing_bo.extra["confirmation_bars"] == 3
        assert aggr_bo.extra["confirmation_bars"] == 2

    def test_get_feature_spec_by_mode(self):
        """get_feature_spec returns the correct spec."""
        spec = get_feature_spec("swing")
        assert spec.mode == "SWING"
        spec = get_feature_spec("Scalp")
        assert spec.mode == "SCALP"
        spec = get_feature_spec("AGGRESSIVE_SCALP")
        assert spec.mode == "AGGRESSIVE_SCALP"

    def test_get_feature_spec_unknown(self):
        """get_feature_spec raises KeyError for unknown modes."""
        with pytest.raises(KeyError):
            get_feature_spec("BOGUS_MODE")

    def test_list_modes(self):
        """list_modes returns all three modes with primary intervals."""
        modes = list_modes()
        assert modes == {
            "SWING": "4h",
            "SCALP": "1h",
            "AGGRESSIVE_SCALP": "15m",
        }

    def test_to_dict_export(self):
        """to_dict produces a serializable dict."""
        spec = MODE_FEATURE_SPECS["SWING"]
        d = spec.to_dict()
        assert d["mode"] == "SWING"
        assert d["primary_interval"] == "4h"
        assert len(d["groups"]) == 6
        assert d["groups"][0]["name"] == "returns"
        assert d["groups"][0]["short_window"] == 1

    def test_immutable_spec(self):
        """FeatureSpec instances are frozen."""
        spec = MODE_FEATURE_SPECS["SWING"]
        with pytest.raises(Exception):
            spec.primary_interval = "1h"  # type: ignore


class TestNoLookahead:
    """No window references future bars."""

    @pytest.mark.parametrize("mode", ["SWING", "SCALP", "AGGRESSIVE_SCALP"])
    def test_all_windows_positive(self, mode):
        """All windows >= 1 (no lookahead)."""
        spec = MODE_FEATURE_SPECS[mode]
        warnings = check_no_lookahead(spec)
        assert warnings == [], f"Lookahead warnings for {mode}: {warnings}"

    @pytest.mark.parametrize("mode", ["SWING", "SCALP", "AGGRESSIVE_SCALP"])
    def test_short_window_le_medium(self, mode):
        """short_window <= medium_window for all groups."""
        spec = MODE_FEATURE_SPECS[mode]
        for g in spec.groups:
            assert (
                g.short_window <= g.medium_window
            ), f"{mode}/{g.name}: short {g.short_window} > medium {g.medium_window}"

    @pytest.mark.parametrize("mode", ["SWING", "SCALP", "AGGRESSIVE_SCALP"])
    def test_medium_window_le_long(self, mode):
        """medium_window <= long_window for all groups."""
        spec = MODE_FEATURE_SPECS[mode]
        for g in spec.groups:
            assert (
                g.medium_window <= g.long_window
            ), f"{mode}/{g.name}: medium {g.medium_window} > long {g.long_window}"


class TestRouterAlignment:
    """FeatureSpec intervals align with router.py mode profiles."""

    def test_swing_intervals_match_router(self):
        """SWING intervals match router.py LOCKED_INITIAL_BASELINE profile."""
        spec = MODE_FEATURE_SPECS["SWING"]
        assert spec.primary_interval == "4h"
        assert spec.context_intervals == ["1d"]
        assert spec.refinement_intervals == ["1h"]

    def test_scalp_intervals_match_router(self):
        """SCALP intervals match router.py HOLD profile."""
        spec = MODE_FEATURE_SPECS["SCALP"]
        assert spec.primary_interval == "1h"
        assert spec.context_intervals == ["4h"]
        assert spec.refinement_intervals == ["15m"]

    def test_aggressive_scalp_intervals_match_router(self):
        """AGGRESSIVE_SCALP intervals match router.py HOLD profile."""
        spec = MODE_FEATURE_SPECS["AGGRESSIVE_SCALP"]
        assert spec.primary_interval == "15m"
        assert spec.context_intervals == ["1h"]
        assert spec.refinement_intervals == ["5m"]
