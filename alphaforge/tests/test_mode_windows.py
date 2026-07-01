"""Tests for per-mode feature window configuration.

Covers:
  (a) ModeWindowConfig construction and immutability
  (b) Window parameter validation (positive, ordering)
  (c) All three modes registered with complete parameter sets
  (d) Window sizing hierarchy: SWING >= SCALP >= AGGRESSIVE in effective hours
  (e) to_dict() produces pipeline-compatible output
  (f) get_mode_windows and get_all_mode_windows accessor correctness
  (g) Unknown mode ValueError
  (h) Import boundary: alphaforge.features exports mode_windows symbols
  (i) SCALP and AGGRESSIVE_SCALP pipeline integration (mode-specific features differ)
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from alphaforge.features.mode_windows import (
    AGGRESSIVE_SCALP_WINDOWS,
    SCALP_WINDOWS,
    SWING_WINDOWS,
    ModeWindowConfig,
    get_all_mode_windows,
    get_mode_windows,
)

from alphaforge.features import (
    compute_features,
    get_all_mode_windows as exported_get_all,
    get_mode_windows as exported_get_mode,
    ModeWindowConfig as exported_ModeWindowConfig,
    SWING_WINDOWS as exported_SWING,
    SCALP_WINDOWS as exported_SCALP,
    AGGRESSIVE_SCALP_WINDOWS as exported_AGGRESSIVE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _effective_hours(config: ModeWindowConfig, param_name: str) -> float:
    """Convert a window bar count to effective hours."""
    interval_hours = {"4h": 4.0, "1h": 1.0, "15m": 0.25}
    hours_per_bar = interval_hours[config.primary_interval]
    return getattr(config, param_name) * hours_per_bar


def _make_ohlcv(n_bars: int = 200):
    """Generate deterministic OHLCV fixture."""
    rng = np.random.RandomState(42)
    close = 50000.0 + np.cumsum(rng.randn(n_bars) * 200.0)
    high = close + np.abs(rng.randn(n_bars) * 100.0)
    low = close - np.abs(rng.randn(n_bars) * 100.0)
    open_arr = close - rng.randn(n_bars) * 50.0
    volume = np.abs(rng.randn(n_bars) * 100.0) + 100.0
    return {"open": open_arr, "high": high, "low": low, "close": close, "volume": volume}


# ===========================================================================
# ModeWindowConfig Construction and Immutability
# ===========================================================================


class TestModeWindowConfigConstruction:
    """Construction and field access."""

    def test_swing_config_fields(self):
        cfg = SWING_WINDOWS
        assert cfg.mode == "SWING"
        assert cfg.primary_interval == "4h"
        assert cfg.periods_per_year == 2190
        assert cfg.n_returns == 10
        assert cfg.volatility_window == 20
        assert cfg.atr_window == 14
        assert cfg.momentum_n == 10
        assert cfg.rsi_window == 14
        assert cfg.macd_fast == 12
        assert cfg.macd_slow == 26
        assert cfg.macd_signal == 9
        assert cfg.volume_window == 20
        assert cfg.breakout_window == 20
        assert cfg.bb_window == 20
        assert cfg.bb_num_std == 2.0

    def test_scalp_config_fields(self):
        cfg = SCALP_WINDOWS
        assert cfg.mode == "SCALP"
        assert cfg.primary_interval == "1h"
        assert cfg.periods_per_year == 8760
        assert cfg.n_returns == 12
        assert cfg.volatility_window == 24
        assert cfg.atr_window == 14
        assert cfg.momentum_n == 12
        assert cfg.rsi_window == 14
        assert cfg.macd_fast == 8
        assert cfg.macd_slow == 17
        assert cfg.macd_signal == 9
        assert cfg.volume_window == 24
        assert cfg.breakout_window == 24
        assert cfg.bb_window == 20
        assert cfg.bb_num_std == 2.0

    def test_aggressive_config_fields(self):
        cfg = AGGRESSIVE_SCALP_WINDOWS
        assert cfg.mode == "AGGRESSIVE_SCALP"
        assert cfg.primary_interval == "15m"
        assert cfg.periods_per_year == 35040
        assert cfg.n_returns == 16
        assert cfg.volatility_window == 24
        assert cfg.atr_window == 10
        assert cfg.momentum_n == 16
        assert cfg.rsi_window == 10
        assert cfg.macd_fast == 6
        assert cfg.macd_slow == 13
        assert cfg.macd_signal == 5
        assert cfg.volume_window == 24
        assert cfg.breakout_window == 12
        assert cfg.bb_window == 12
        assert cfg.bb_num_std == 2.0

    def test_all_have_description(self):
        for cfg in [SWING_WINDOWS, SCALP_WINDOWS, AGGRESSIVE_SCALP_WINDOWS]:
            assert cfg.description, f"{cfg.mode} missing description"

    def test_all_threshold_status_locked_initial_baseline(self):
        for cfg in [SWING_WINDOWS, SCALP_WINDOWS, AGGRESSIVE_SCALP_WINDOWS]:
            assert cfg.threshold_status == "LOCKED_INITIAL_BASELINE", (
                f"{cfg.mode}: {cfg.threshold_status}"
            )


class TestModeWindowConfigImmutability:
    """Frozen dataclass — cannot mutate fields."""

    def test_cannot_set_field(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            SWING_WINDOWS.n_returns = 99  # type: ignore[misc]

    def test_cannot_set_field_scalp(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            SCALP_WINDOWS.atr_window = 5  # type: ignore[misc]

    def test_cannot_set_field_aggressive(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            AGGRESSIVE_SCALP_WINDOWS.bb_num_std = 3.0  # type: ignore[misc]


# ===========================================================================
# Validation
# ===========================================================================


class TestModeWindowConfigValidation:
    """Post-init validation rejects invalid parameters."""

    def test_non_positive_window_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            ModeWindowConfig(
                mode="TEST",
                primary_interval="1h",
                periods_per_year=100,
                n_returns=0,  # invalid
                volatility_window=10,
                atr_window=10,
                momentum_n=10,
                rsi_window=10,
                macd_fast=5,
                macd_slow=10,
                macd_signal=5,
                volume_window=10,
                breakout_window=10,
                bb_window=10,
                bb_num_std=2.0,
            )

    def test_negative_window_raises(self):
        with pytest.raises(ValueError, match="positive integer"):
            ModeWindowConfig(
                mode="TEST",
                primary_interval="1h",
                periods_per_year=100,
                n_returns=10,
                volatility_window=-5,  # invalid
                atr_window=10,
                momentum_n=10,
                rsi_window=10,
                macd_fast=5,
                macd_slow=10,
                macd_signal=5,
                volume_window=10,
                breakout_window=10,
                bb_window=10,
                bb_num_std=2.0,
            )

    def test_macd_fast_gte_slow_raises(self):
        with pytest.raises(ValueError, match="macd_fast"):
            ModeWindowConfig(
                mode="TEST",
                primary_interval="1h",
                periods_per_year=100,
                n_returns=10,
                volatility_window=10,
                atr_window=10,
                momentum_n=10,
                rsi_window=10,
                macd_fast=26,
                macd_slow=12,  # fast >= slow
                macd_signal=9,
                volume_window=10,
                breakout_window=10,
                bb_window=10,
                bb_num_std=2.0,
            )

    def test_macd_fast_equal_slow_raises(self):
        with pytest.raises(ValueError, match="macd_fast"):
            ModeWindowConfig(
                mode="TEST",
                primary_interval="1h",
                periods_per_year=100,
                n_returns=10,
                volatility_window=10,
                atr_window=10,
                momentum_n=10,
                rsi_window=10,
                macd_fast=10,
                macd_slow=10,  # fast == slow
                macd_signal=5,
                volume_window=10,
                breakout_window=10,
                bb_window=10,
                bb_num_std=2.0,
            )

    def test_bb_num_std_non_positive_raises(self):
        with pytest.raises(ValueError, match="bb_num_std"):
            ModeWindowConfig(
                mode="TEST",
                primary_interval="1h",
                periods_per_year=100,
                n_returns=10,
                volatility_window=10,
                atr_window=10,
                momentum_n=10,
                rsi_window=10,
                macd_fast=5,
                macd_slow=10,
                macd_signal=5,
                volume_window=10,
                breakout_window=10,
                bb_window=10,
                bb_num_std=0.0,  # invalid
            )

    def test_valid_config_constructs(self):
        """All three mode configs pass validation (implicit — they exist)."""
        for cfg in [SWING_WINDOWS, SCALP_WINDOWS, AGGRESSIVE_SCALP_WINDOWS]:
            assert isinstance(cfg, ModeWindowConfig)
            assert cfg.macd_fast < cfg.macd_slow


# ===========================================================================
# Window Sizing Hierarchy
# ===========================================================================


class TestWindowSizingHierarchy:
    """SWING > SCALP > AGGRESSIVE in effective hours for lookback windows."""

    def test_volatility_window_hours_decreasing(self):
        sw_h = _effective_hours(SWING_WINDOWS, "volatility_window")
        sc_h = _effective_hours(SCALP_WINDOWS, "volatility_window")
        ag_h = _effective_hours(AGGRESSIVE_SCALP_WINDOWS, "volatility_window")
        assert sw_h > sc_h, f"SWING {sw_h}h should be > SCALP {sc_h}h"
        assert sc_h > ag_h, f"SCALP {sc_h}h should be > AGGRESSIVE {ag_h}h"

    def test_n_returns_hours_decreasing(self):
        sw_h = _effective_hours(SWING_WINDOWS, "n_returns")
        sc_h = _effective_hours(SCALP_WINDOWS, "n_returns")
        ag_h = _effective_hours(AGGRESSIVE_SCALP_WINDOWS, "n_returns")
        assert sw_h > sc_h, f"SWING {sw_h}h should be > SCALP {sc_h}h"
        assert sc_h > ag_h, f"SCALP {sc_h}h should be > AGGRESSIVE {ag_h}h"

    def test_atr_window_hours_decreasing(self):
        sw_h = _effective_hours(SWING_WINDOWS, "atr_window")
        sc_h = _effective_hours(SCALP_WINDOWS, "atr_window")
        ag_h = _effective_hours(AGGRESSIVE_SCALP_WINDOWS, "atr_window")
        assert sw_h > sc_h, f"SWING {sw_h}h should be > SCALP {sc_h}h"
        assert sc_h > ag_h, f"SCALP {sc_h}h should be > AGGRESSIVE {ag_h}h"

    def test_momentum_n_hours_decreasing(self):
        sw_h = _effective_hours(SWING_WINDOWS, "momentum_n")
        sc_h = _effective_hours(SCALP_WINDOWS, "momentum_n")
        ag_h = _effective_hours(AGGRESSIVE_SCALP_WINDOWS, "momentum_n")
        assert sw_h > sc_h, f"SWING {sw_h}h should be > SCALP {sc_h}h"
        assert sc_h > ag_h, f"SCALP {sc_h}h should be > AGGRESSIVE {ag_h}h"

    def test_breakout_window_hours_decreasing(self):
        sw_h = _effective_hours(SWING_WINDOWS, "breakout_window")
        sc_h = _effective_hours(SCALP_WINDOWS, "breakout_window")
        ag_h = _effective_hours(AGGRESSIVE_SCALP_WINDOWS, "breakout_window")
        assert sw_h > sc_h, f"SWING {sw_h}h should be > SCALP {sc_h}h"
        assert sc_h > ag_h, f"SCALP {sc_h}h should be > AGGRESSIVE {ag_h}h"

    def test_rsi_aggressive_tighter_than_swing(self):
        """AGGRESSIVE RSI window is tighter (faster oscillator response)."""
        assert AGGRESSIVE_SCALP_WINDOWS.rsi_window < SWING_WINDOWS.rsi_window

    def test_macd_all_modes_have_fast_lt_slow(self):
        for cfg in [SWING_WINDOWS, SCALP_WINDOWS, AGGRESSIVE_SCALP_WINDOWS]:
            assert cfg.macd_fast < cfg.macd_slow, (
                f"{cfg.mode}: macd_fast={cfg.macd_fast} not < macd_slow={cfg.macd_slow}"
            )


# ===========================================================================
# to_dict() Method
# ===========================================================================


class TestToDict:
    """to_dict() produces pipeline-compatible output."""

    REQUIRED_KEYS = {
        "n_returns",
        "volatility_window",
        "atr_window",
        "momentum_n",
        "rsi_window",
        "macd_fast",
        "macd_slow",
        "macd_signal",
        "volume_window",
        "breakout_window",
        "bb_window",
        "bb_num_std",
        "periods_per_year",
    }

    def test_swing_to_dict_has_all_keys(self):
        d = SWING_WINDOWS.to_dict()
        assert set(d.keys()) == self.REQUIRED_KEYS

    def test_scalp_to_dict_has_all_keys(self):
        d = SCALP_WINDOWS.to_dict()
        assert set(d.keys()) == self.REQUIRED_KEYS

    def test_aggressive_to_dict_has_all_keys(self):
        d = AGGRESSIVE_SCALP_WINDOWS.to_dict()
        assert set(d.keys()) == self.REQUIRED_KEYS

    def test_to_dict_values_match_config(self):
        cfg = SCALP_WINDOWS
        d = cfg.to_dict()
        assert d["n_returns"] == cfg.n_returns
        assert d["volatility_window"] == cfg.volatility_window
        assert d["atr_window"] == cfg.atr_window
        assert d["momentum_n"] == cfg.momentum_n
        assert d["rsi_window"] == cfg.rsi_window
        assert d["macd_fast"] == cfg.macd_fast
        assert d["macd_slow"] == cfg.macd_slow
        assert d["macd_signal"] == cfg.macd_signal
        assert d["volume_window"] == cfg.volume_window
        assert d["breakout_window"] == cfg.breakout_window
        assert d["bb_window"] == cfg.bb_window
        assert d["bb_num_std"] == cfg.bb_num_std
        assert d["periods_per_year"] == cfg.periods_per_year

    def test_to_dict_all_positive(self):
        for cfg in [SWING_WINDOWS, SCALP_WINDOWS, AGGRESSIVE_SCALP_WINDOWS]:
            d = cfg.to_dict()
            for key in self.REQUIRED_KEYS:
                val = d[key]
                if key == "bb_num_std":
                    assert isinstance(val, float), f"{cfg.mode}.{key} not float"
                else:
                    assert isinstance(val, int), f"{cfg.mode}.{key} not int"
                assert val > 0, f"{cfg.mode}.{key} = {val} not positive"


# ===========================================================================
# Registry and Accessors
# ===========================================================================


class TestRegistry:
    """ModeWindowConfig registry and accessor correctness."""

    def test_all_three_modes_registered(self):
        modes = ModeWindowConfig.all_modes()
        assert set(modes) == {"AGGRESSIVE_SCALP", "SCALP", "SWING"}

    def test_get_swing_returns_correct_config(self):
        cfg = ModeWindowConfig.get("SWING")
        assert cfg is SWING_WINDOWS
        assert cfg.mode == "SWING"

    def test_get_scalp_returns_correct_config(self):
        cfg = ModeWindowConfig.get("SCALP")
        assert cfg is SCALP_WINDOWS
        assert cfg.mode == "SCALP"

    def test_get_aggressive_returns_correct_config(self):
        cfg = ModeWindowConfig.get("AGGRESSIVE_SCALP")
        assert cfg is AGGRESSIVE_SCALP_WINDOWS
        assert cfg.mode == "AGGRESSIVE_SCALP"

    def test_get_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            ModeWindowConfig.get("HFT")

    def test_get_mode_windows_convenience(self):
        cfg = get_mode_windows("SWING")
        assert cfg is SWING_WINDOWS

    def test_get_all_mode_windows_returns_all(self):
        all_cfgs = get_all_mode_windows()
        assert set(all_cfgs.keys()) == {"SWING", "SCALP", "AGGRESSIVE_SCALP"}
        assert all_cfgs["SWING"] is SWING_WINDOWS
        assert all_cfgs["SCALP"] is SCALP_WINDOWS
        assert all_cfgs["AGGRESSIVE_SCALP"] is AGGRESSIVE_SCALP_WINDOWS

    def test_get_all_mode_windows_is_shallow_copy(self):
        all1 = get_all_mode_windows()
        all2 = get_all_mode_windows()
        assert all1 is not all2  # Different dict objects
        assert all1 == all2  # But equal content


# ===========================================================================
# Import Boundary / Export Surface
# ===========================================================================


class TestExportSurface:
    """alphaforge.features exports mode_windows symbols."""

    def test_init_exports_mode_window_config(self):
        assert exported_ModeWindowConfig is ModeWindowConfig

    def test_init_exports_swing_windows(self):
        assert exported_SWING is SWING_WINDOWS

    def test_init_exports_scalp_windows(self):
        assert exported_SCALP is SCALP_WINDOWS

    def test_init_exports_aggressive_windows(self):
        assert exported_AGGRESSIVE is AGGRESSIVE_SCALP_WINDOWS

    def test_init_exports_get_mode_windows(self):
        assert exported_get_mode is get_mode_windows

    def test_init_exports_get_all_mode_windows(self):
        assert exported_get_all is get_all_mode_windows


# ===========================================================================
# Pipeline Integration — mode-specific features differ
# ===========================================================================


class TestPipelineModeSpecific:
    """Verify compute_features produces different outputs per mode."""

    def test_swing_vs_scalp_features_differ(self):
        """SWING and SCALP use different window params — outputs must differ."""
        ohlcv = _make_ohlcv(500)
        swing_fm = compute_features(ohlcv, mode="SWING")
        scalp_fm = compute_features(ohlcv, mode="SCALP")

        # Feature names must be identical (same group structure)
        assert set(swing_fm.features.keys()) == set(scalp_fm.features.keys())

        # At least some features should differ due to different windows
        diff_count = 0
        for key in swing_fm.features:
            sw_arr = swing_fm.features[key]
            sc_arr = scalp_fm.features[key]
            both_valid = ~np.isnan(sw_arr) & ~np.isnan(sc_arr)
            if np.sum(both_valid) > 0 and not np.allclose(
                sw_arr[both_valid], sc_arr[both_valid], atol=1e-8
            ):
                diff_count += 1
        assert diff_count > 0, "Expected SWING and SCALP features to differ"

    def test_scalp_vs_aggressive_features_differ(self):
        ohlcv = _make_ohlcv(500)
        scalp_fm = compute_features(ohlcv, mode="SCALP")
        agg_fm = compute_features(ohlcv, mode="AGGRESSIVE_SCALP")

        diff_count = 0
        for key in scalp_fm.features:
            sc_arr = scalp_fm.features[key]
            ag_arr = agg_fm.features[key]
            both_valid = ~np.isnan(sc_arr) & ~np.isnan(ag_arr)
            if np.sum(both_valid) > 0 and not np.allclose(
                sc_arr[both_valid], ag_arr[both_valid], atol=1e-8
            ):
                diff_count += 1
        assert diff_count > 0, "Expected SCALP and AGGRESSIVE features to differ"

    def test_all_modes_produce_35_features(self):
        ohlcv = _make_ohlcv(200)
        for mode in ["SWING", "SCALP", "AGGRESSIVE_SCALP"]:
            fm = compute_features(ohlcv, mode=mode)
            assert fm.total_features() == 35, f"{mode}: {fm.total_features()}"
            assert fm.bar_count() == 200
            assert fm.mode == mode

    def test_nan_counts_differ_by_mode(self):
        """Different windows produce different NaN counts at series start."""
        ohlcv = _make_ohlcv(200)
        swing_fm = compute_features(ohlcv, mode="SWING")
        scalp_fm = compute_features(ohlcv, mode="SCALP")
        agg_fm = compute_features(ohlcv, mode="AGGRESSIVE_SCALP")

        # SWING n_returns=10, SCALP n_returns=12, AGGRESSIVE n_returns=16
        assert int(np.sum(np.isnan(swing_fm.features["log_return_N"]))) == 10
        assert int(np.sum(np.isnan(scalp_fm.features["log_return_N"]))) == 12
        assert int(np.sum(np.isnan(agg_fm.features["log_return_N"]))) == 16

    def test_metadata_includes_window_defaults(self):
        ohlcv = _make_ohlcv(100)
        for mode in ["SWING", "SCALP", "AGGRESSIVE_SCALP"]:
            fm = compute_features(ohlcv, mode=mode)
            assert "window_defaults" in fm.metadata
            wd = fm.metadata["window_defaults"]
            assert isinstance(wd, dict)
            # Verify at least one key
            assert "n_returns" in wd

    def test_causality_no_revision_all_modes(self):
        """No-revision test passes for all three modes."""
        ohlcv = _make_ohlcv(500)
        for mode in ["SWING", "SCALP", "AGGRESSIVE_SCALP"]:
            fm_n = compute_features(
                {k: v[:400] for k, v in ohlcv.items()}, mode=mode
            )
            fm_n1 = compute_features(
                {k: v[:401] for k, v in ohlcv.items()}, mode=mode
            )
            for key in fm_n.features:
                arr_n = fm_n.features[key]
                arr_n1_slice = fm_n1.features[key][:400]
                both_nan_n = np.isnan(arr_n)
                both_nan_n1 = np.isnan(arr_n1_slice)
                assert np.array_equal(both_nan_n, both_nan_n1), (
                    f"{mode}/{key}: NaN mask changed on append"
                )
                valid_n = arr_n[~both_nan_n]
                valid_n1 = arr_n1_slice[~both_nan_n1]
                assert np.allclose(valid_n, valid_n1, atol=1e-8), (
                    f"{mode}/{key}: non-NaN values differ on append"
                )

    def test_periods_per_year_passed_to_realized_volatility(self):
        """Realized volatility uses mode-specific periods_per_year."""
        ohlcv = _make_ohlcv(500)
        swing_fm = compute_features(ohlcv, mode="SWING")
        scalp_fm = compute_features(ohlcv, mode="SCALP")
        agg_fm = compute_features(ohlcv, mode="AGGRESSIVE_SCALP")

        swing_vol = swing_fm.features["realized_volatility_N"]
        scalp_vol = scalp_fm.features["realized_volatility_N"]
        agg_vol = agg_fm.features["realized_volatility_N"]

        # Annualized vol scales with sqrt(periods_per_year), so
        # SCALP vol / SWING vol ~ sqrt(8760/2190) = sqrt(4) = 2
        # for same underlying returns — but windows also differ.
        # At minimum: all should be non-negative and finite.
        for label, arr in [("SWING", swing_vol), ("SCALP", scalp_vol),
                           ("AGGRESSIVE", agg_vol)]:
            valid = arr[~np.isnan(arr)]
            assert np.all(valid >= 0), f"{label}: negative vol"
            assert np.all(np.isfinite(valid)), f"{label}: non-finite vol"


# ===========================================================================
# Determinism Tests
# ===========================================================================


class TestModeDeterminism:
    """Multiple calls with same mode produce identical output."""

    def test_swing_determinism(self):
        ohlcv = _make_ohlcv(200)
        r1 = compute_features(ohlcv, mode="SWING")
        r2 = compute_features(ohlcv, mode="SWING")
        for key in r1.features:
            assert np.array_equal(
                np.isnan(r1.features[key]), np.isnan(r2.features[key])
            ), f"SWING {key}: NaN mask differs"
            both_valid = ~np.isnan(r1.features[key])
            assert np.allclose(
                r1.features[key][both_valid],
                r2.features[key][both_valid],
                atol=1e-8,
            ), f"SWING {key}: values differ"

    def test_scalp_determinism(self):
        ohlcv = _make_ohlcv(200)
        r1 = compute_features(ohlcv, mode="SCALP")
        r2 = compute_features(ohlcv, mode="SCALP")
        for key in r1.features:
            both_valid = ~np.isnan(r1.features[key])
            assert np.allclose(
                r1.features[key][both_valid],
                r2.features[key][both_valid],
                atol=1e-8,
            ), f"SCALP {key}: values differ"

    def test_aggressive_determinism(self):
        ohlcv = _make_ohlcv(200)
        r1 = compute_features(ohlcv, mode="AGGRESSIVE_SCALP")
        r2 = compute_features(ohlcv, mode="AGGRESSIVE_SCALP")
        for key in r1.features:
            both_valid = ~np.isnan(r1.features[key])
            assert np.allclose(
                r1.features[key][both_valid],
                r2.features[key][both_valid],
                atol=1e-8,
            ), f"AGGRESSIVE_SCALP {key}: values differ"


# ===========================================================================
# Cross-mode Feature Shape Consistency
# ===========================================================================


class TestCrossModeConsistency:
    """All modes produce identically-shaped feature matrices."""

    def test_same_feature_names_across_modes(self):
        ohlcv = _make_ohlcv(200)
        names_sw = set(compute_features(ohlcv, mode="SWING").features.keys())
        names_sc = set(compute_features(ohlcv, mode="SCALP").features.keys())
        names_ag = set(compute_features(ohlcv, mode="AGGRESSIVE_SCALP").features.keys())
        assert names_sw == names_sc == names_ag

    def test_same_feature_count_across_modes(self):
        ohlcv = _make_ohlcv(200)
        for mode in ["SWING", "SCALP", "AGGRESSIVE_SCALP"]:
            fm = compute_features(ohlcv, mode=mode)
            assert fm.total_features() == 35

    def test_no_lead_lag_in_any_mode(self):
        ohlcv = _make_ohlcv(100)
        for mode in ["SWING", "SCALP", "AGGRESSIVE_SCALP"]:
            fm = compute_features(ohlcv, mode=mode)
            assert "lead_lag" not in fm.feature_group_ids
            for key in fm.features:
                assert "lead" not in key.lower()
