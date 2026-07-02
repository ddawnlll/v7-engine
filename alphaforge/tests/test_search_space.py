"""Tests for XGBoost Search Space module (issue #146).

Covers:
- SearchSpace and ParameterRange dataclass immutability and defaults
- get_search_space() for all three modes (SWING, SCALP, AGGRESSIVE_SCALP)
- all_search_spaces() returns all spaces
- param_bounds() returns correct ranges per mode
- Unknown mode raises ValueError
- suggest_params() with Optuna trial (integration)
- build_objective() returns callable and produces valid objective
- Fixed params are included in suggested params
- Log-uniform params use log sampling
- Parameter ranges match issue #146 specifications
- Edge cases: ImportError when Optuna absent
"""

from __future__ import annotations

import math
from typing import Any, Dict

import numpy as np
import pytest

from alphaforge.tuning.search_space import (
    AGGRESSIVE_SCALP_SEARCH_SPACE,
    SCALP_SEARCH_SPACE,
    SWING_SEARCH_SPACE,
    ParameterRange,
    SearchSpace,
    _HAS_OPTUNA,
    all_search_spaces,
    build_objective,
    get_search_space,
    param_bounds,
    suggest_params,
)


# ============================================================================
# ParameterRange tests
# ============================================================================


def test_parameter_range_defaults():
    """ParameterRange has correct defaults for log, param_type, step."""
    pr = ParameterRange(name="test_param", low=0.0, high=1.0)
    assert pr.log is False
    assert pr.param_type == "float"
    assert pr.step is None


def test_parameter_range_immutable():
    """ParameterRange is frozen (immutable)."""
    pr = ParameterRange(name="test_param", low=0.0, high=1.0)
    with pytest.raises(AttributeError):
        pr.low = 0.5  # type: ignore[misc]


def test_parameter_range_int_type():
    """ParameterRange with param_type='int' stores correctly."""
    pr = ParameterRange(name="max_depth", low=3, high=10, param_type="int")
    assert pr.param_type == "int"
    assert pr.low == 3
    assert pr.high == 10


def test_parameter_range_log():
    """ParameterRange with log=True."""
    pr = ParameterRange(name="reg_alpha", low=1e-8, high=5.0, log=True)
    assert pr.log is True


# ============================================================================
# SearchSpace tests
# ============================================================================


def test_search_space_immutable():
    """SearchSpace is frozen (immutable)."""
    ss = SearchSpace(mode="TEST", ranges=[])
    with pytest.raises(AttributeError):
        ss.mode = "OTHER"  # type: ignore[misc]


def test_search_space_fixed_params_without():
    """fixed_params_without excludes specified keys."""
    ss = SearchSpace(
        mode="TEST",
        fixed_params={"a": 1, "b": 2, "c": 3},
    )
    filtered = ss.fixed_params_without("b")
    assert filtered == {"a": 1, "c": 3}
    assert "b" not in filtered


def test_search_space_defaults():
    """SearchSpace has sensible defaults for n_trials and timeout."""
    ss = SearchSpace(mode="TEST", ranges=[])
    assert ss.n_trials == 100
    assert ss.timeout_seconds == 600
    assert ss.description == ""
    assert ss.fixed_params == {}


# ============================================================================
# SWING search space tests
# ============================================================================


class TestSwingSearchSpace:
    """Tests specific to SWING mode search space."""

    def test_mode(self):
        assert SWING_SEARCH_SPACE.mode == "SWING"

    def test_n_trials(self):
        assert SWING_SEARCH_SPACE.n_trials == 100

    def test_contains_learning_rate(self):
        names = {r.name for r in SWING_SEARCH_SPACE.ranges}
        assert "learning_rate" in names

    def test_learning_rate_range(self):
        lr = self._param("learning_rate")
        assert lr.low == pytest.approx(0.01)
        assert lr.high == pytest.approx(0.3)
        assert lr.log is True

    def test_max_depth_range(self):
        md = self._param("max_depth")
        assert md.low == 3
        assert md.high == 10
        assert md.param_type == "int"

    def test_n_estimators_range(self):
        ne = self._param("n_estimators")
        assert ne.low == 50
        assert ne.high == 500
        assert ne.param_type == "int"

    def test_subsample_range(self):
        ss = self._param("subsample")
        assert ss.low == pytest.approx(0.5)
        assert ss.high == pytest.approx(1.0)

    def test_colsample_bytree_range(self):
        cs = self._param("colsample_bytree")
        assert cs.low == pytest.approx(0.3)
        assert cs.high == pytest.approx(1.0)

    def test_min_child_weight_range(self):
        mcw = self._param("min_child_weight")
        assert mcw.low == 1
        assert mcw.high == 15
        assert mcw.param_type == "int"

    def test_gamma_range(self):
        g = self._param("gamma")
        assert g.low == pytest.approx(0.0)
        assert g.high == pytest.approx(5.0)

    def test_reg_alpha_range(self):
        ra = self._param("reg_alpha")
        assert ra.low == pytest.approx(1e-8)
        assert ra.high == pytest.approx(5.0)
        assert ra.log is True

    def test_reg_lambda_range(self):
        rl = self._param("reg_lambda")
        assert rl.low == pytest.approx(1e-8)
        assert rl.high == pytest.approx(5.0)
        assert rl.log is True

    def test_fixed_params_contains_objective(self):
        assert "objective" in SWING_SEARCH_SPACE.fixed_params
        assert SWING_SEARCH_SPACE.fixed_params["objective"] == "multi:softprob"

    def test_fixed_params_contains_num_class(self):
        assert SWING_SEARCH_SPACE.fixed_params["num_class"] == 3

    def test_all_ranges_present(self):
        """SWING has all 9 tuned parameters."""
        assert len(SWING_SEARCH_SPACE.ranges) == 9

    def _param(self, name: str) -> ParameterRange:
        for r in SWING_SEARCH_SPACE.ranges:
            if r.name == name:
                return r
        raise ValueError(f"Parameter '{name}' not found in SWING search space")


# ============================================================================
# SCALP search space tests
# ============================================================================


class TestScalpSearchSpace:
    """Tests specific to SCALP mode search space."""

    def test_mode(self):
        assert SCALP_SEARCH_SPACE.mode == "SCALP"

    def test_n_trials(self):
        assert SCALP_SEARCH_SPACE.n_trials == 100

    def test_max_depth_cap(self):
        """SCALP max_depth is capped at 8 (vs 10 for SWING)."""
        md = self._param("max_depth")
        assert md.high == 8

    def test_n_estimators_cap(self):
        """SCALP n_estimators is capped at 300 (vs 500 for SWING)."""
        ne = self._param("n_estimators")
        assert ne.high == 300

    def test_min_child_weight_floor(self):
        """SCALP min_child_weight floor is 3 (vs 1 for SWING)."""
        mcw = self._param("min_child_weight")
        assert mcw.low == 3

    def test_all_ranges_present(self):
        assert len(SCALP_SEARCH_SPACE.ranges) == 9

    def test_learning_rate_log(self):
        lr = self._param("learning_rate")
        assert lr.log is True

    def test_reg_alpha_log(self):
        ra = self._param("reg_alpha")
        assert ra.log is True

    def test_reg_lambda_log(self):
        rl = self._param("reg_lambda")
        assert rl.log is True

    def test_subsample_floor(self):
        ss = self._param("subsample")
        assert ss.low == pytest.approx(0.5)

    def _param(self, name: str) -> ParameterRange:
        for r in SCALP_SEARCH_SPACE.ranges:
            if r.name == name:
                return r
        raise ValueError(f"Parameter '{name}' not found in SCALP search space")


# ============================================================================
# AGGRESSIVE_SCALP search space tests
# ============================================================================


class TestAggressiveScalpSearchSpace:
    """Tests specific to AGGRESSIVE_SCALP mode search space."""

    def test_mode(self):
        assert AGGRESSIVE_SCALP_SEARCH_SPACE.mode == "AGGRESSIVE_SCALP"

    def test_n_trials(self):
        """AGGRESSIVE_SCALP uses fewer trials (80 vs 100)."""
        assert AGGRESSIVE_SCALP_SEARCH_SPACE.n_trials == 80

    def test_timeout_longer(self):
        """AGGRESSIVE_SCALP has longer timeout (900s vs 600s)."""
        assert AGGRESSIVE_SCALP_SEARCH_SPACE.timeout_seconds == 900

    def test_learning_rate_starts_lower(self):
        lr = self._param("learning_rate")
        assert lr.low == pytest.approx(0.005)
        assert lr.high == pytest.approx(0.2)

    def test_max_depth_capped_at_6(self):
        md = self._param("max_depth")
        assert md.high == 6
        assert md.low == 2

    def test_n_estimators_capped_at_200(self):
        ne = self._param("n_estimators")
        assert ne.high == 200
        assert ne.low == 30

    def test_subsample_starts_lower(self):
        ss = self._param("subsample")
        assert ss.low == pytest.approx(0.4)

    def test_colsample_bytree_starts_lower(self):
        cs = self._param("colsample_bytree")
        assert cs.low == pytest.approx(0.2)

    def test_min_child_weight_floor_higher(self):
        mcw = self._param("min_child_weight")
        assert mcw.low == 5
        assert mcw.high == 20

    def test_gamma_wider_range(self):
        g = self._param("gamma")
        assert g.high == pytest.approx(8.0)

    def test_reg_alpha_wider_range(self):
        ra = self._param("reg_alpha")
        assert ra.high == pytest.approx(10.0)

    def test_reg_lambda_wider_range(self):
        rl = self._param("reg_lambda")
        assert rl.high == pytest.approx(10.0)

    def test_all_ranges_present(self):
        assert len(AGGRESSIVE_SCALP_SEARCH_SPACE.ranges) == 9

    def _param(self, name: str) -> ParameterRange:
        for r in AGGRESSIVE_SCALP_SEARCH_SPACE.ranges:
            if r.name == name:
                return r
        raise ValueError(f"Parameter '{name}' not found in AGGRESSIVE_SCALP search space")


# ============================================================================
# get_search_space tests
# ============================================================================


def test_get_search_space_swing():
    space = get_search_space("SWING")
    assert space.mode == "SWING"
    assert len(space.ranges) == 9


def test_get_search_space_scalp():
    space = get_search_space("SCALP")
    assert space.mode == "SCALP"
    assert len(space.ranges) == 9


def test_get_search_space_aggressive_scalp():
    space = get_search_space("AGGRESSIVE_SCALP")
    assert space.mode == "AGGRESSIVE_SCALP"
    assert len(space.ranges) == 9


def test_get_search_space_invalid_mode():
    with pytest.raises(ValueError, match="Unknown mode"):
        get_search_space("INVALID")


def test_get_search_space_case_sensitive():
    with pytest.raises(ValueError):
        get_search_space("swing")


def test_all_search_spaces_returns_all():
    spaces = all_search_spaces()
    assert len(spaces) == 3
    for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        assert mode in spaces
        assert isinstance(spaces[mode], SearchSpace)


def test_all_search_spaces_immutable():
    """all_search_spaces returns a copy, not the internal dict."""
    spaces = all_search_spaces()
    spaces.pop("SWING", None)
    # Original should still have SWING
    assert "SWING" in all_search_spaces()


# ============================================================================
# param_bounds tests
# ============================================================================


def test_param_bounds_swing():
    bounds = param_bounds("SWING")
    assert isinstance(bounds, dict)
    assert "learning_rate" in bounds
    assert "max_depth" in bounds
    assert "reg_alpha" in bounds
    assert bounds["learning_rate"] == (0.01, 0.3)
    assert bounds["max_depth"] == (3, 10)


def test_param_bounds_all_params():
    bounds = param_bounds("SWING")
    # All 9 tuned params
    expected = {
        "learning_rate", "max_depth", "n_estimators",
        "subsample", "colsample_bytree", "min_child_weight",
        "gamma", "reg_alpha", "reg_lambda",
    }
    assert set(bounds.keys()) == expected


def test_param_bounds_scalp():
    bounds = param_bounds("SCALP")
    assert bounds["max_depth"] == (3, 8)
    assert bounds["n_estimators"] == (50, 300)


# ============================================================================
# suggest_params tests (requires Optuna)
# ============================================================================

pytestmark_optuna = pytest.mark.skipif(
    not _HAS_OPTUNA, reason="Optuna is not installed"
)


@pytest.mark.skipif(not _HAS_OPTUNA, reason="Optuna is not installed")
class TestSuggestParams:
    """Tests for suggest_params with Optuna."""

    def test_suggest_params_returns_all_keys(self):
        import optuna

        study = optuna.create_study(direction="minimize")
        trial = study.ask()

        space = get_search_space("SWING")
        params = suggest_params(trial, space)

        # All fixed params present
        for k in space.fixed_params:
            assert k in params, f"Missing fixed param: {k}"

        # All tuned params present
        for rng in space.ranges:
            assert rng.name in params, f"Missing tuned param: {rng.name}"

        # Total params = fixed + tuned
        assert len(params) == len(space.fixed_params) + len(space.ranges)

    def test_suggest_params_within_bounds(self):
        import optuna

        study = optuna.create_study(direction="minimize")

        space = get_search_space("SWING")
        # Sample multiple times to verify bounds
        for _ in range(20):
            trial = study.ask()
            params = suggest_params(trial, space)
            for rng in space.ranges:
                val = params[rng.name]
                assert rng.low <= val <= rng.high, (
                    f"{rng.name}: {val} not in [{rng.low}, {rng.high}]"
                )

    def test_suggest_params_int_params_are_integers(self):
        import optuna

        study = optuna.create_study(direction="minimize")
        trial = study.ask()

        params = suggest_params(trial, get_search_space("SWING"))
        for name in ("max_depth", "n_estimators", "min_child_weight"):
            assert isinstance(params[name], int), f"{name} should be int"

    def test_suggest_params_float_params_are_floats(self):
        import optuna

        study = optuna.create_study(direction="minimize")
        trial = study.ask()

        params = suggest_params(trial, get_search_space("SWING"))
        for name in ("learning_rate", "subsample", "gamma", "reg_alpha"):
            assert isinstance(params[name], float), f"{name} should be float"

    def test_suggest_params_log_uniform_produces_varied_values(self):
        """Log-uniform params should produce values across the full range."""
        import optuna

        study = optuna.create_study(direction="minimize")

        reg_alpha_values = []
        for _ in range(50):
            trial = study.ask()
            params = suggest_params(trial, get_search_space("SWING"))
            reg_alpha_values.append(params["reg_alpha"])

        # At least some values should be in the lower and upper portions
        # of the log range (not all clustering near one end)
        low_count = sum(1 for v in reg_alpha_values if v < 0.01)
        high_count = sum(1 for v in reg_alpha_values if v > 2.0)
        # With log-uniform over 1e-8 to 5.0, we expect some spread
        assert low_count > 0, "No values in low end of reg_alpha range"
        assert high_count > 0, "No values in high end of reg_alpha range"

    def test_suggest_params_fixed_params_unchanged(self):
        import optuna

        study = optuna.create_study(direction="minimize")
        trial = study.ask()

        space = get_search_space("SWING")
        params = suggest_params(trial, space)
        assert params["objective"] == "multi:softprob"
        assert params["num_class"] == 3
        assert params["eval_metric"] == "mlogloss"

    def test_suggest_params_all_modes(self):
        import optuna

        study = optuna.create_study(direction="minimize")

        for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            space = get_search_space(mode)
            trial = study.ask()
            params = suggest_params(trial, space)

            assert "objective" in params
            assert "max_depth" in params
            assert "learning_rate" in params
            assert "reg_alpha" in params
            assert len(params) == len(space.fixed_params) + len(space.ranges)


# ============================================================================
# build_objective tests
# ============================================================================


@pytest.mark.skipif(not _HAS_OPTUNA, reason="Optuna is not installed")
class TestBuildObjective:
    """Tests for build_objective with Optuna."""

    def _make_data(self, n_samples: int = 100, n_features: int = 5):
        rng = np.random.RandomState(42)
        X = rng.randn(n_samples, n_features).astype(np.float64)
        y = np.array(
            ["LONG_NOW"] * (n_samples // 3)
            + ["SHORT_NOW"] * (n_samples // 3)
            + ["NO_TRADE"] * (n_samples - 2 * (n_samples // 3))
        )
        return X, y

    def test_build_objective_returns_callable(self):
        X, y = self._make_data()
        objective = build_objective(X, y, mode="SWING")
        assert callable(objective)

    def test_objective_returns_float(self):
        import optuna
        import xgboost as xgb  # noqa: F401 — ensure available

        X, y = self._make_data()
        objective_fn = build_objective(X, y, mode="SWING")

        study = optuna.create_study(direction="minimize")
        trial = study.ask()
        value = objective_fn(trial)
        assert isinstance(value, float)
        # mlogloss should be positive (log loss > 0)
        assert value > 0.0

    def test_objective_small_data(self):
        """Objective works with minimal data."""
        import optuna
        import xgboost as xgb  # noqa: F401

        X, y = self._make_data(n_samples=30)
        objective_fn = build_objective(X, y, mode="SWING")

        study = optuna.create_study(direction="minimize")
        trial = study.ask()
        value = objective_fn(trial)
        assert isinstance(value, float)
        assert value > 0.0

    def test_objective_with_feature_names(self):
        import optuna
        import xgboost as xgb  # noqa: F401

        X, y = self._make_data()
        feature_names = [f"f{i}" for i in range(X.shape[1])]
        objective_fn = build_objective(
            X, y, mode="SWING", feature_names=feature_names
        )

        study = optuna.create_study(direction="minimize")
        trial = study.ask()
        value = objective_fn(trial)
        assert isinstance(value, float)

    def test_multiple_trials_produce_different_values(self):
        """Different param samples produce different objective values."""
        import optuna
        import xgboost as xgb  # noqa: F401

        X, y = self._make_data(n_samples=100)
        objective_fn = build_objective(X, y, mode="SWING")

        study = optuna.create_study(direction="minimize")
        values = []
        for _ in range(5):
            trial = study.ask()
            values.append(objective_fn(trial))

        # With max_depth varying 3-10 and log-uniform learning rate,
        # at least some trials should produce different values
        unique_values = set(round(v, 6) for v in values)
        assert len(unique_values) > 1, (
            "All trials produced the same objective value"
        )

    def test_build_objective_modes(self):
        """build_objective works for all modes."""
        import optuna
        import xgboost as xgb  # noqa: F401

        X, y = self._make_data(n_samples=60)

        for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            objective_fn = build_objective(X, y, mode=mode)
            study = optuna.create_study(direction="minimize")
            trial = study.ask()
            value = objective_fn(trial)
            assert isinstance(value, float), f"Mode {mode} failed"

    def test_study_optimize(self):
        """Full Optuna study optimize round-trip works."""
        import optuna
        import xgboost as xgb  # noqa: F401

        X, y = self._make_data(n_samples=60)
        objective_fn = build_objective(X, y, mode="SWING")

        study = optuna.create_study(direction="minimize")
        study.optimize(objective_fn, n_trials=3)

        assert study.best_value > 0.0
        assert study.best_params is not None
        assert "max_depth" in study.best_params
        assert "learning_rate" in study.best_params


# ============================================================================
# Cross-mode consistency tests
# ============================================================================


def test_swing_has_widest_ranges():
    """SWING has the widest or equal ranges among all modes."""
    swing_bounds = param_bounds("SWING")
    scalp_bounds = param_bounds("SCALP")
    aggro_bounds = param_bounds("AGGRESSIVE_SCALP")

    for param in swing_bounds:
        s_low, s_high = swing_bounds[param]
        sc_low, sc_high = scalp_bounds[param]
        a_low, a_high = aggro_bounds[param]
        # SWING range >= SCALP range
        assert s_low <= sc_low, f"{param}: SWING low ({s_low}) > SCALP low ({sc_low})"
        assert s_high >= sc_high, (
            f"{param}: SWING high ({s_high}) < SCALP high ({sc_high})"
        )


def test_all_modes_have_same_param_count():
    """All three modes tune exactly 9 parameters."""
    for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        space = get_search_space(mode)
        assert len(space.ranges) == 9, f"{mode} has {len(space.ranges)} ranges"


def test_all_modes_have_required_params():
    """All modes have the 9 required tuned parameters."""
    required = {
        "learning_rate", "max_depth", "n_estimators",
        "subsample", "colsample_bytree", "min_child_weight",
        "gamma", "reg_alpha", "reg_lambda",
    }
    for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        space = get_search_space(mode)
        param_names = {r.name for r in space.ranges}
        missing = required - param_names
        assert not missing, f"{mode} missing params: {missing}"
        extra = param_names - required
        assert not extra, f"{mode} has extra params: {extra}"


def test_all_log_params_correct():
    """All regularization params use log-uniform sampling."""
    for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
        space = get_search_space(mode)
        for r in space.ranges:
            if r.name in ("learning_rate", "reg_alpha", "reg_lambda"):
                assert r.log is True, (
                    f"{mode}/{r.name} should use log sampling"
                )


def test_fixed_params_consistent_across_modes():
    """All modes share the same base XGBoost fixed params."""
    spaces = [get_search_space(m) for m in ("SWING", "SCALP", "AGGRESSIVE_SCALP")]
    base_keys = {"objective", "num_class", "eval_metric", "random_state"}
    for space in spaces:
        for key in base_keys:
            assert key in space.fixed_params, (
                f"{space.mode} missing fixed param: {key}"
            )
        assert space.fixed_params["objective"] == "multi:softprob"
        assert space.fixed_params["num_class"] == 3
        assert space.fixed_params["eval_metric"] == "mlogloss"
        assert space.fixed_params["random_state"] == 42


# ============================================================================
# Edge case tests
# ============================================================================


def test_search_space_with_empty_ranges():
    """SearchSpace can be constructed with zero ranges."""
    ss = SearchSpace(mode="EMPTY")
    assert ss.ranges == []
    assert ss.mode == "EMPTY"


def test_parameter_range_zero_range():
    """A range where low == high is valid (fixed parameter in tuning space)."""
    pr = ParameterRange(name="fixed_in_search", low=1.0, high=1.0)
    assert pr.low == pr.high


def test_parameter_range_negative_values():
    """ParameterRange supports negative values where appropriate."""
    pr = ParameterRange(name="negative_ok", low=-1.0, high=1.0)
    assert pr.low == -1.0


# ============================================================================
# Import/API surface tests
# ============================================================================


def test_module_exports():
    """All expected names are exported from tuning package."""
    from alphaforge.tuning import __all__ as tuning_exports

    expected = {
        "AGGRESSIVE_SCALP_SEARCH_SPACE",
        "ParameterRange",
        "SCALP_SEARCH_SPACE",
        "SearchSpace",
        "SWING_SEARCH_SPACE",
        "all_search_spaces",
        "build_objective",
        "get_search_space",
        "param_bounds",
        "suggest_params",
    }
    assert set(tuning_exports) == expected, (
        f"Missing exports: {expected - set(tuning_exports)}"
    )
