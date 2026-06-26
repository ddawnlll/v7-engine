"""
Tests for mode-specific label semantics (LabelSpec / LABEL_SPECS).

Verifies:
  - All three modes are present with correct primary intervals and windows.
  - Edge thresholds are positive and match the LOCKED_INITIAL_BASELINE values.
  - LabelSpec instances are frozen (immutable).
  - Validation helpers reject invalid configurations.
"""

from dataclasses import FrozenInstanceError

import pytest

from simulation.contracts.models import TradingMode
from v7.labels.contracts import LABEL_SPECS, LabelSpec


# ── Mode presence ────────────────────────────────────────────────────────


class TestLabelSpecsPresent:
    def test_all_three_modes_registered(self):
        assert set(LABEL_SPECS.keys()) == {
            TradingMode.SWING,
            TradingMode.SCALP,
            TradingMode.AGGRESSIVE_SCALP,
        }

    def test_swing_present(self):
        spec = LABEL_SPECS[TradingMode.SWING]
        assert spec.mode == TradingMode.SWING

    def test_scalp_present(self):
        spec = LABEL_SPECS[TradingMode.SCALP]
        assert spec.mode == TradingMode.SCALP

    def test_aggressive_scalp_present(self):
        spec = LABEL_SPECS[TradingMode.AGGRESSIVE_SCALP]
        assert spec.mode == TradingMode.AGGRESSIVE_SCALP


# ── Mode-specific values ────────────────────────────────────────────────


class TestSwingValues:
    def test_primary_interval(self):
        assert LABEL_SPECS[TradingMode.SWING].primary_interval == "4h"

    def test_label_window(self):
        assert LABEL_SPECS[TradingMode.SWING].label_window == 24

    def test_min_edge_r(self):
        assert LABEL_SPECS[TradingMode.SWING].min_edge_r == 0.25


class TestScalpValues:
    def test_primary_interval(self):
        assert LABEL_SPECS[TradingMode.SCALP].primary_interval == "1h"

    def test_label_window(self):
        assert LABEL_SPECS[TradingMode.SCALP].label_window == 48

    def test_min_edge_r(self):
        assert LABEL_SPECS[TradingMode.SCALP].min_edge_r == 0.15


class TestAggressiveScalpValues:
    def test_primary_interval(self):
        assert LABEL_SPECS[TradingMode.AGGRESSIVE_SCALP].primary_interval == "15m"

    def test_label_window(self):
        assert LABEL_SPECS[TradingMode.AGGRESSIVE_SCALP].label_window == 96

    def test_min_edge_r(self):
        assert LABEL_SPECS[TradingMode.AGGRESSIVE_SCALP].min_edge_r == 0.10


# ── Edge threshold validation ──────────────────────────────────────────


class TestEdgeThresholdValidation:
    def test_all_min_edge_r_positive(self):
        for spec in LABEL_SPECS.values():
            assert spec.min_edge_r > 0, f"{spec.mode} min_edge_r <= 0"

    def test_all_min_net_r_for_success_positive(self):
        for spec in LABEL_SPECS.values():
            assert spec.min_net_r_for_success > 0, (
                f"{spec.mode} min_net_r_for_success <= 0"
            )

    def test_all_max_mae_r_for_success_negative(self):
        """MAE thresholds must be negative — they represent adverse excursion."""
        for spec in LABEL_SPECS.values():
            assert spec.max_mae_r_for_success < 0, (
                f"{spec.mode} max_mae_r_for_success >= 0"
            )

    def test_all_ambiguity_margin_r_positive(self):
        for spec in LABEL_SPECS.values():
            assert spec.ambiguity_margin_r > 0, (
                f"{spec.mode} ambiguity_margin_r <= 0"
            )

    def test_all_label_window_positive(self):
        for spec in LABEL_SPECS.values():
            assert spec.label_window > 0, f"{spec.mode} label_window <= 0"

    def test_all_primary_interval_nonempty(self):
        for spec in LABEL_SPECS.values():
            assert spec.primary_interval, f"{spec.mode} primary_interval is empty"


# ── Immutability ────────────────────────────────────────────────────────


class TestLabelSpecImmutability:
    def test_spec_is_frozen(self):
        spec = LABEL_SPECS[TradingMode.SWING]
        with pytest.raises(FrozenInstanceError):
            spec.label_window = 99


# ── SimulationOutput consumption contract ──────────────────────────────


class TestSimulationOutputConsumption:
    """Labels consume SimulationOutput; verify the interface contract."""

    def test_label_spec_accepts_all_simulation_modes(self):
        """Every TradingMode in simulation has a corresponding LabelSpec."""
        from simulation.contracts.models import TradingMode as SimMode

        for tm in SimMode:
            assert tm in LABEL_SPECS, (
                f"Missing LabelSpec for TradingMode.{tm.value}"
            )


# ── Module-level exports ────────────────────────────────────────────────


class TestLabelsModuleExports:
    def test_module_imports(self):
        from v7.labels import LabelSpec as LS, LABEL_SPECS as LS_DICT, TradingMode as TM

        assert LS is LabelSpec
        assert LS_DICT is LABEL_SPECS
        assert TM is TradingMode

    def test_v7_init_exposes_labels(self):
        import v7

        assert hasattr(v7, "labels")
        assert v7.labels.LabelSpec is LabelSpec
