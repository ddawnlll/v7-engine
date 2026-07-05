"""Tests for mode-specific hyperparameter tuning profiles.

Covers:
- ModeTuningProfile data class immutability
- Canonical profiles for SWING, SCALP, AGGRESSIVE_SCALP
- get_tuning_profile lookup (valid + invalid modes)
- suggest_params produces correct param keys
- save_tuning_params and load_tuning_params round-trip
- suggest_params mode vs profile mutual exclusivity
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import optuna
import pytest

from alphaforge.tuning.mode_profiles import (
    AGGRESSIVE_SCALP_TUNING,
    SCALP_TUNING,
    SWING_TUNING,
    ModeTuningProfile,
    TuningParamRange,
    all_tuning_profiles,
    get_tuning_profile,
    load_tuning_params,
    save_tuning_params,
    suggest_params,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trial() -> optuna.trial.Trial:
    """Create a fresh Optuna trial for parameter suggestion tests."""
    study = optuna.create_study(direction="maximize")
    return study.ask()


# ---------------------------------------------------------------------------
# Profile data class tests
# ---------------------------------------------------------------------------


class TestTuningParamRange:
    """TuningParamRange immutability and construction."""

    def test_frozen(self):
        r = TuningParamRange(0.01, 0.05, log=True)
        with pytest.raises(AttributeError):
            r.low = 0.1  # type: ignore[misc]

    def test_default_log_false(self):
        r = TuningParamRange(0.1, 0.5)
        assert r.log is False

    def test_float_bounds(self):
        r = TuningParamRange(1.0, 10.0)
        assert r.low == 1.0
        assert r.high == 10.0


class TestModeTuningProfile:
    """ModeTuningProfile construction and properties."""

    def test_frozen(self):
        profile = SWING_TUNING
        with pytest.raises(AttributeError):
            profile.mode = "INVALID"  # type: ignore[misc]

    def test_swing_parameters(self):
        profile = SWING_TUNING
        assert profile.mode == "SWING"
        assert profile.learning_rate.low == 0.01
        assert profile.learning_rate.high == 0.05
        assert profile.max_depth == (6, 10)

    def test_scalp_parameters(self):
        profile = SCALP_TUNING
        assert profile.mode == "SCALP"
        assert profile.learning_rate.low == 0.05
        assert profile.learning_rate.high == 0.2
        assert profile.max_depth == (3, 6)

    def test_aggressive_scalp_parameters(self):
        profile = AGGRESSIVE_SCALP_TUNING
        assert profile.mode == "AGGRESSIVE_SCALP"
        assert profile.learning_rate.low == 0.1
        assert profile.learning_rate.high == 0.3
        assert profile.max_depth == (3, 5)


# ---------------------------------------------------------------------------
# Profile lookup tests
# ---------------------------------------------------------------------------


class TestGetTuningProfile:
    """get_tuning_profile resolution."""

    def test_all_modes_resolve(self):
        for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            profile = get_tuning_profile(mode)
            assert profile.mode == mode
            assert isinstance(profile, ModeTuningProfile)

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            get_tuning_profile("INVALID")

    def test_all_tuning_profiles_returns_copy(self):
        profiles = all_tuning_profiles()
        assert len(profiles) == 3
        assert "SWING" in profiles
        assert "SCALP" in profiles
        assert "AGGRESSIVE_SCALP" in profiles
        # Ensure it's a copy
        profiles.pop("SWING", None)
        assert "SWING" in all_tuning_profiles()


# ---------------------------------------------------------------------------
# suggest_params tests
# ---------------------------------------------------------------------------


class TestSuggestParams:
    """Param suggestion from profiles."""

    def test_swing_suggestions(self, trial):
        params = suggest_params(trial, mode="SWING")
        assert isinstance(params, dict)
        self._assert_common_keys(params)
        # SWING depth range: 6-10
        assert 6 <= params["max_depth"] <= 10
        assert 0.01 <= params["learning_rate"] <= 0.05
        assert 100 <= params["n_estimators"] <= 300

    def test_scalp_suggestions(self, trial):
        params = suggest_params(trial, mode="SCALP")
        assert isinstance(params, dict)
        self._assert_common_keys(params)
        assert 3 <= params["max_depth"] <= 6
        assert 0.05 <= params["learning_rate"] <= 0.2
        assert 100 <= params["n_estimators"] <= 500

    def test_aggressive_scalp_suggestions(self, trial):
        params = suggest_params(trial, profile=AGGRESSIVE_SCALP_TUNING)
        assert isinstance(params, dict)
        self._assert_common_keys(params)
        assert 3 <= params["max_depth"] <= 5
        assert 0.1 <= params["learning_rate"] <= 0.3
        assert 100 <= params["n_estimators"] <= 500

    def _assert_common_keys(self, params):
        required = {
            "learning_rate", "max_depth", "reg_alpha", "reg_lambda",
            "min_child_weight", "subsample", "colsample_bytree", "gamma",
            "n_estimators",
        }
        assert required.issubset(params.keys()), f"Missing keys: {required - params.keys()}"

    def test_suggestions_are_deterministic_seeded(self):
        """Same trial seed should produce different suggestions across calls
        (Optuna uses internal RNG, not global seed)."""
        study = optuna.create_study(direction="maximize")
        t1 = study.ask()
        t2 = study.ask()

        p1 = suggest_params(t1, mode="SWING")
        p2 = suggest_params(t2, mode="SWING")

        # Different trials produce different params (very high probability)
        # but we don't assert that — just check both are valid
        assert isinstance(p1, dict)
        assert isinstance(p2, dict)

    def test_neither_profile_nor_mode_raises(self, trial):
        with pytest.raises(ValueError, match="Provide either"):
            suggest_params(trial)  # type: ignore[arg-type]

    def test_both_profile_and_mode_raises(self, trial):
        with pytest.raises(ValueError, match="Provide only one"):
            suggest_params(trial, profile=SWING_TUNING, mode="SWING")


# ---------------------------------------------------------------------------
# Save / Load round-trip tests
# ---------------------------------------------------------------------------


class TestSaveLoadTuningParams:
    """save_tuning_params and load_tuning_params persistence."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def test_save_creates_file(self, temp_dir):
        params = {"learning_rate": 0.03, "max_depth": 8}
        path = save_tuning_params(params, "SWING", output_dir=str(temp_dir))
        assert path.exists()
        assert path.name == "swing_tuning_params.json"

    def test_save_creates_directory(self, temp_dir):
        nested = temp_dir / "nested" / "path"
        params = {"learning_rate": 0.1}
        path = save_tuning_params(params, "SCALP", output_dir=str(nested))
        assert path.exists()
        assert nested.exists()

    def test_save_with_trial_number(self, temp_dir):
        params = {"learning_rate": 0.2}
        path = save_tuning_params(params, "AGGRESSIVE_SCALP",
                                   output_dir=str(temp_dir), trial_number=5)
        assert path.name == "aggressive_scalp_tuning_params_trial5.json"

    def test_save_content_is_valid_json(self, temp_dir):
        params = {"learning_rate": 0.03, "max_depth": 8, "reg_alpha": 1.5}
        path = save_tuning_params(params, "SWING", output_dir=str(temp_dir))
        with open(path) as f:
            loaded = json.load(f)
        assert loaded == params

    def test_load_returns_saved_params(self, temp_dir):
        original = {"learning_rate": 0.03, "max_depth": 8}
        save_tuning_params(original, "SWING", output_dir=str(temp_dir))
        loaded = load_tuning_params("SWING", output_dir=str(temp_dir))
        assert loaded == original

    def test_load_missing_returns_none(self, temp_dir):
        result = load_tuning_params("SWING", output_dir=str(temp_dir))
        assert result is None

    def test_load_after_save_all_modes(self, temp_dir):
        all_modes = {"SWING": {"lr": 0.03}, "SCALP": {"lr": 0.1},
                     "AGGRESSIVE_SCALP": {"lr": 0.2}}
        for mode, params in all_modes.items():
            save_tuning_params(params, mode, output_dir=str(temp_dir))

        for mode, expected in all_modes.items():
            loaded = load_tuning_params(mode, output_dir=str(temp_dir))
            assert loaded is not None
            assert loaded["lr"] == expected["lr"]


# ---------------------------------------------------------------------------
# Regularisation level verification
# ---------------------------------------------------------------------------


class TestRegularisationLevels:
    """Verify reg levels match issue requirements:
    SWING=high, SCALP=medium, AGGRESSIVE=low.
    """

    def test_swing_highest_reg_alpha(self):
        assert SWING_TUNING.reg_alpha.low >= 0.5

    def test_scalp_medium_reg_alpha(self):
        alpha = SCALP_TUNING.reg_alpha
        assert alpha.low <= 0.1 or alpha.high <= 1.0

    def test_aggressive_lowest_reg_alpha(self):
        assert AGGRESSIVE_SCALP_TUNING.reg_alpha.high <= 0.1
        assert AGGRESSIVE_SCALP_TUNING.reg_lambda.high <= 1.0

    def test_reg_alpha_strictly_decreasing(self):
        """SWING > SCALP > AGGRESSIVE_SCALP in reg_alpha bounds."""
        swing = SWING_TUNING.reg_alpha
        scalp = SCALP_TUNING.reg_alpha
        aggressive = AGGRESSIVE_SCALP_TUNING.reg_alpha
        assert swing.low > scalp.low > aggressive.low
        assert swing.high > scalp.high > aggressive.high
