"""Tests for v7.labels — mode-specific LabelSpec contracts.

Design authority: v7/docs/pipeline/labels.md
"""

import pytest

from v7.labels import (
    LabelSpec,
    LABEL_SPECS,
    SUPPORTED_MODES,
    get_label_spec,
)


# ---------------------------------------------------------------------------
# LabelSpec per-mode — static contract verification
# ---------------------------------------------------------------------------

class TestLabelSpecPerMode:
    """Verify LabelSpec values for every supported mode."""

    def test_swing_spec(self):
        spec = LABEL_SPECS["SWING"]
        assert spec.mode == "SWING"
        assert spec.primary_interval == "4h"
        assert spec.label_window_bars == 24
        assert spec.min_edge_r == 0.25
        assert spec.min_net_r_for_success == 0.75
        assert spec.max_mae_r_for_success == -0.60
        assert spec.min_mfe_r_for_good_exit == 1.0
        assert spec.allow_no_trade_on_ambiguity is False
        assert spec.no_trade_default is False

    def test_scalp_spec(self):
        spec = LABEL_SPECS["SCALP"]
        assert spec.mode == "SCALP"
        assert spec.primary_interval == "1h"
        assert spec.label_window_bars == 48
        assert spec.min_edge_r == 0.15
        assert spec.min_net_r_for_success == 0.20
        assert spec.max_mae_r_for_success == -0.25
        assert spec.allow_no_trade_on_ambiguity is True

    def test_aggressive_scalp_spec(self):
        spec = LABEL_SPECS["AGGRESSIVE_SCALP"]
        assert spec.mode == "AGGRESSIVE_SCALP"
        assert spec.primary_interval == "15m"
        assert spec.label_window_bars == 96
        assert spec.min_edge_r == 0.10
        assert spec.min_net_r_for_success == 0.10
        assert spec.max_mae_r_for_success == -0.10
        assert spec.allow_no_trade_on_ambiguity is True
        assert spec.no_trade_default is True


# ---------------------------------------------------------------------------
# Edge threshold validation
# ---------------------------------------------------------------------------

class TestEdgeThresholdValidation:
    """The min_edge_r field gates trade entry — it must be positive."""

    def test_all_specs_have_positive_edge(self):
        for mode in SUPPORTED_MODES:
            spec = LABEL_SPECS[mode]
            assert spec.validate_edge_threshold(), (
                f"{mode} has non-positive min_edge_r={spec.min_edge_r}"
            )

    def test_zero_edge_is_invalid(self):
        spec = LabelSpec(
            mode="TEST_ZERO",
            primary_interval="1h",
            label_window_bars=24,
            min_edge_r=0.0,
            min_net_r_for_success=0.30,
            max_mae_r_for_success=-0.30,
            min_mfe_r_for_good_exit=0.50,
            max_time_to_mfe_bars=12,
            allow_no_trade_on_ambiguity=True,
            no_trade_default=False,
        )
        assert spec.validate_edge_threshold() is False

    def test_negative_edge_is_invalid(self):
        spec = LabelSpec(
            mode="TEST_NEG",
            primary_interval="1h",
            label_window_bars=24,
            min_edge_r=-0.05,
            min_net_r_for_success=0.30,
            max_mae_r_for_success=-0.30,
            min_mfe_r_for_good_exit=0.50,
            max_time_to_mfe_bars=12,
            allow_no_trade_on_ambiguity=True,
            no_trade_default=False,
        )
        assert spec.validate_edge_threshold() is False

    def test_small_positive_edge_is_valid(self):
        spec = LabelSpec(
            mode="TEST_SMALL",
            primary_interval="1h",
            label_window_bars=24,
            min_edge_r=0.001,
            min_net_r_for_success=0.30,
            max_mae_r_for_success=-0.30,
            min_mfe_r_for_good_exit=0.50,
            max_time_to_mfe_bars=12,
            allow_no_trade_on_ambiguity=True,
            no_trade_default=False,
        )
        assert spec.validate_edge_threshold() is True


# ---------------------------------------------------------------------------
# Label window validation
# ---------------------------------------------------------------------------

class TestLabelWindowValidation:
    """The label window configures how many bars of forward data are used."""

    def test_all_specs_have_positive_window(self):
        for mode in SUPPORTED_MODES:
            spec = LABEL_SPECS[mode]
            assert spec.validate_label_window(), (
                f"{mode} has non-positive label_window_bars={spec.label_window_bars}"
            )

    def test_zero_window_is_invalid(self):
        spec = LabelSpec(
            mode="TEST_ZERO_W",
            primary_interval="1h",
            label_window_bars=0,
            min_edge_r=0.10,
            min_net_r_for_success=0.30,
            max_mae_r_for_success=-0.30,
            min_mfe_r_for_good_exit=0.50,
            max_time_to_mfe_bars=12,
            allow_no_trade_on_ambiguity=True,
            no_trade_default=False,
        )
        assert spec.validate_label_window() is False

    def test_negative_window_is_invalid(self):
        spec = LabelSpec(
            mode="TEST_NEG_W",
            primary_interval="1h",
            label_window_bars=-5,
            min_edge_r=0.10,
            min_net_r_for_success=0.30,
            max_mae_r_for_success=-0.30,
            min_mfe_r_for_good_exit=0.50,
            max_time_to_mfe_bars=12,
            allow_no_trade_on_ambiguity=True,
            no_trade_default=False,
        )
        assert spec.validate_label_window() is False


# ---------------------------------------------------------------------------
# get_label_spec lookup
# ---------------------------------------------------------------------------

class TestGetLabelSpec:
    """The get_label_spec helper provides fail-fast lookup."""

    def test_returns_spec_for_valid_modes(self):
        for mode in SUPPORTED_MODES:
            spec = get_label_spec(mode)
            assert isinstance(spec, LabelSpec)
            assert spec.mode == mode

    def test_raises_on_unknown_mode(self):
        with pytest.raises(KeyError, match="Unknown mode"):
            get_label_spec("INVENTED_MODE")

    def test_raises_on_empty_string(self):
        with pytest.raises(KeyError):
            get_label_spec("")


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

class TestLabelSpecImmutability:
    """LabelSpec is frozen — its fields cannot be reassigned."""

    def test_frozen_assignment_raises(self):
        spec = LABEL_SPECS["SWING"]
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            spec.min_edge_r = 0.99  # type: ignore[misc]

    def test_frozen_does_not_accept_new_attributes(self):
        spec = LABEL_SPECS["SWING"]
        with pytest.raises(Exception):
            spec.new_field = 42  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Mode ordering — label window grows with faster modes
# ---------------------------------------------------------------------------

class TestLabelWindowOrdering:
    """Faster modes need more bars to capture comparable statistical signal,
    so label_window_bars should be monotonic with interval speed."""

    def test_aggressive_scalp_has_largest_window(self):
        """AGGRESSIVE_SCALP (15m) has the largest window to accumulate signal."""
        windows = {s.mode: s.label_window_bars for s in LABEL_SPECS.values()}
        assert windows["AGGRESSIVE_SCALP"] > windows["SCALP"] > windows["SWING"], (
            f"Expected AGGRESSIVE_SCALP({windows['AGGRESSIVE_SCALP']}) > "
            f"SCALP({windows['SCALP']}) > SWING({windows['SWING']})"
        )

    def test_edge_threshold_decreases_with_speed(self):
        """Faster modes accept lower edge thresholds due to volume of opportunities."""
        edges = {s.mode: s.min_edge_r for s in LABEL_SPECS.values()}
        assert edges["AGGRESSIVE_SCALP"] < edges["SCALP"] < edges["SWING"], (
            f"Expected AGGRESSIVE_SCALP({edges['AGGRESSIVE_SCALP']}) < "
            f"SCALP({edges['SCALP']}) < SWING({edges['SWING']})"
        )
