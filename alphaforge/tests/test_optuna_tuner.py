"""Tests for AlphaForge Optuna Tuning Engine (TR-05).

Covers:
- OptunaTuner initialization and mode validation
- TPE sampler configuration
- ASHA (SuccessiveHalving) pruning configuration
- SQLite study persistence
- Study lifecycle: create, load, list, delete
- Mode-specific search space suggestions
- Optimization with synthetic data
- Results: best_params, best_value, study_summary
- save_results JSON output
- search_spaces function
- Edge cases: no trials, pruned trials
- list_studies and delete_study functions
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import numpy as np
import optuna
import pytest
import xgboost as xgb

from tuning.optuna_tuner import (
    DEFAULT_N_TRIALS,
    DEFAULT_TIMEOUT_SECONDS,
    STUDIES_DIR,
    ASHA_MIN_RESOURCE,
    ASHA_REDUCTION_FACTOR,
    ASHA_MIN_EARLY_STOPPING_RATE,
    TPE_N_STARTUP_TRIALS,
    TPE_SEED,
    OptunaTuner,
    StudySummary,
    TuningResult,
    search_spaces,
    list_studies,
    delete_study,
    _storage_url,
    _resolve_studies_dir,
)
from tuning.optuna_tuner import VALID_MODES


# ============================================================================
# Helpers
# ============================================================================


def _make_demo_objective(tuner: OptunaTuner, n_samples: int = 200) -> Any:
    """Create a demo objective function for a given tuner.

    Uses synthetic 3-class data with XGBoost training.
    """
    def objective(trial: optuna.Trial) -> float:
        params = tuner.suggest_params(trial)
        xgb_params = {
            **params,
            "objective": "multi:softprob",
            "num_class": 3,
            "eval_metric": "mlogloss",
            "random_state": 42,
            "verbosity": 0,
        }

        rng = np.random.RandomState(42)
        X = rng.randn(n_samples, 10)
        y = rng.randint(0, 3, n_samples)

        n_val = max(1, n_samples // 5)
        dtrain = xgb.DMatrix(X[:-n_val], label=y[:-n_val])
        dval = xgb.DMatrix(X[-n_val:], label=y[-n_val:])

        booster = xgb.train(
            params=xgb_params,
            dtrain=dtrain,
            num_boost_round=params.get("n_estimators", 50),
            evals=[(dval, "val")],
            early_stopping_rounds=10,
            verbose_eval=False,
        )

        preds = booster.predict(dval)
        acc = float(np.mean(np.argmax(preds, axis=1) == y[-n_val:]))
        return acc

    return objective


# ============================================================================
# Initialization tests
# ============================================================================


class TestOptunaTunerInit:
    """OptunaTuner initialization tests."""

    def test_default_init(self):
        """OptunaTuner initializes with default SWING mode and TPE sampler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(study_name="test_default")
                assert tuner.mode == "SWING"
                assert tuner.study_name == "test_default"
                assert isinstance(tuner._sampler, optuna.samplers.TPESampler)
                assert isinstance(tuner._pruner, optuna.pruners.SuccessiveHalvingPruner)
                assert tuner._direction == "maximize"
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_explicit_mode(self):
        """OptunaTuner accepts explicit SWING, SCALP, AGGRESSIVE_SCALP modes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                for mode in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
                    tuner = OptunaTuner(study_name=f"test_{mode.lower()}", mode=mode)
                    assert tuner.mode == mode
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_invalid_mode(self):
        """OptunaTuner raises ValueError for invalid mode."""
        with pytest.raises(ValueError, match="Unsupported mode"):
            OptunaTuner(study_name="test_invalid", mode="INVALID")

    def test_custom_storage(self):
        """OptunaTuner accepts custom storage URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "custom.db"
            storage = f"sqlite:///{db_path}"
            tuner = OptunaTuner(
                study_name="test_storage",
                storage=storage,
            )
            assert "sqlite" in str(tuner._storage)

    def test_minimize_direction(self):
        """OptunaTuner accepts minimize direction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_minimize",
                    direction="minimize",
                )
                assert tuner._direction == "minimize"
                assert tuner.study.direction == optuna.study.StudyDirection.MINIMIZE
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_custom_sampler(self):
        """OptunaTuner accepts custom sampler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                sampler = optuna.samplers.RandomSampler(seed=42)
                tuner = OptunaTuner(
                    study_name="test_sampler",
                    sampler=sampler,
                )
                assert isinstance(tuner._sampler, optuna.samplers.RandomSampler)
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_custom_pruner(self):
        """OptunaTuner accepts custom pruner."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                pruner = optuna.pruners.MedianPruner()
                tuner = OptunaTuner(
                    study_name="test_pruner",
                    pruner=pruner,
                )
                assert isinstance(tuner._pruner, optuna.pruners.MedianPruner)
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)


# ============================================================================
# TPE sampler configuration tests
# ============================================================================


class TestTPESamplerConfig:
    """TPE sampler configuration tests."""

    def test_default_tpe_config(self):
        """Default TPE sampler uses standard n_startup_trials and seed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(study_name="test_tpe_config")
                assert tuner._sampler._n_startup_trials == TPE_N_STARTUP_TRIALS
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_custom_tpe_config(self):
        """TPE sampler accepts custom n_startup_trials and seed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_custom_tpe",
                    n_startup_trials=5,
                    seed=123,
                )
                assert tuner._sampler._n_startup_trials == 5
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)


# ============================================================================
# ASHA pruner configuration tests
# ============================================================================


class TestASHAPrunerConfig:
    """ASHA (SuccessiveHalving) pruner configuration tests."""

    def test_default_asha_config(self):
        """Default ASHA pruner uses standard min_resource, reduction_factor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(study_name="test_asha_config")
                pruner = tuner._pruner
                assert isinstance(pruner, optuna.pruners.SuccessiveHalvingPruner)
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_custom_pruner_object(self):
        """SuccessiveHalvingPruner can be constructed with custom params."""
        pruner = optuna.pruners.SuccessiveHalvingPruner(
            min_resource=ASHA_MIN_RESOURCE,
            reduction_factor=ASHA_REDUCTION_FACTOR,
            min_early_stopping_rate=ASHA_MIN_EARLY_STOPPING_RATE,
        )
        assert pruner._min_resource == ASHA_MIN_RESOURCE
        assert pruner._reduction_factor == ASHA_REDUCTION_FACTOR


# ============================================================================
# Search space tests
# ============================================================================


class TestSearchSpaces:
    """Search space function tests."""

    def test_search_spaces_swing(self):
        """SWING search space has all expected parameters."""
        space = search_spaces("SWING")
        assert "max_depth" in space
        assert "learning_rate" in space
        assert "n_estimators" in space
        assert "subsample" in space
        assert space["max_depth"]["low"] == 3
        assert space["max_depth"]["high"] == 8

    def test_search_spaces_scalp(self):
        """SCALP search space has all expected parameters."""
        space = search_spaces("SCALP")
        assert "max_depth" in space
        assert space["max_depth"]["low"] == 2
        assert space["max_depth"]["high"] == 6

    def test_search_spaces_aggressive_scalp(self):
        """AGGRESSIVE_SCALP search space has all expected parameters."""
        space = search_spaces("AGGRESSIVE_SCALP")
        assert "max_depth" in space
        assert space["max_depth"]["low"] == 2
        assert space["max_depth"]["high"] == 5

    def test_search_spaces_invalid_mode(self):
        """search_spaces raises ValueError for unknown mode."""
        with pytest.raises(ValueError, match="Unknown mode"):
            search_spaces("INVALID")

    def test_suggest_params_swing(self):
        """suggest_params produces valid params for SWING mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(study_name="test_suggest_swing", mode="SWING")

                # Create a trial to test suggest_params
                study = optuna.create_study(direction="maximize")
                trial = study.ask()

                params = tuner.suggest_params(trial)
                assert "max_depth" in params
                assert "learning_rate" in params
                assert "n_estimators" in params
                assert 3 <= params["max_depth"] <= 8
                assert 0.01 <= params["learning_rate"] <= 0.15
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_suggest_params_scalp(self):
        """suggest_params produces valid params for SCALP mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(study_name="test_suggest_scalp", mode="SCALP")
                study = optuna.create_study(direction="maximize")
                trial = study.ask()

                params = tuner.suggest_params(trial)
                assert "max_depth" in params
                assert 2 <= params["max_depth"] <= 6
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_suggest_params_aggressive_scalp(self):
        """suggest_params produces valid params for AGGRESSIVE_SCALP mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_suggest_aggressive",
                    mode="AGGRESSIVE_SCALP",
                )
                study = optuna.create_study(direction="maximize")
                trial = study.ask()

                params = tuner.suggest_params(trial)
                assert "max_depth" in params
                assert 2 <= params["max_depth"] <= 5
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)


# ============================================================================
# Optimization tests
# ============================================================================


class TestOptimization:
    """Optimization execution tests."""

    def test_optimize_with_synthetic_data(self):
        """Optimize runs successfully with synthetic data and returns TuningResult."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_opt_synthetic",
                    mode="SWING",
                )
                objective = _make_demo_objective(tuner, n_samples=150)

                result = tuner.optimize(
                    objective,
                    n_trials=5,
                    timeout=120,
                )

                assert isinstance(result, TuningResult)
                assert result.study_name == "test_opt_synthetic"
                assert result.n_trials == 5
                assert result.best_value is not None
                assert result.best_value >= 0.0
                assert len(result.best_params) > 0
                assert result.duration_seconds > 0.0
                # Should have trial details
                assert len(result.trial_details) == 5
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_best_params_after_optimization(self):
        """Best params are populated after optimization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_best_params",
                    mode="SWING",
                )
                objective = _make_demo_objective(tuner, n_samples=100)

                tuner.optimize(objective, n_trials=5, timeout=120)

                assert tuner.best_value is not None
                assert tuner.best_value >= 0.0
                best_params = tuner.best_params
                assert "max_depth" in best_params
                assert "learning_rate" in best_params
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_best_trial_after_optimization(self):
        """Best trial is populated after optimization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_best_trial",
                    mode="SWING",
                )
                objective = _make_demo_objective(tuner, n_samples=100)

                tuner.optimize(objective, n_trials=5, timeout=120)

                best_trial = tuner.best_trial
                assert best_trial is not None
                assert best_trial.value is not None
                assert best_trial.number >= 0
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_optimize_with_scalp_mode(self):
        """Optimize runs with SCALP mode search space."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_scalp_opt",
                    mode="SCALP",
                )
                objective = _make_demo_objective(tuner, n_samples=100)

                result = tuner.optimize(objective, n_trials=3, timeout=60)

                assert result.n_trials == 3
                assert result.best_value is not None
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)


# ============================================================================
# Study lifecycle tests
# ============================================================================


class TestStudyLifecycle:
    """Study lifecycle management tests."""

    def test_create_and_resume_study(self):
        """Study can be created, used, then resumed with load_if_exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_resume.db"
            storage = f"sqlite:///{db_path}"

            # Create and run some trials
            tuner1 = OptunaTuner(
                study_name="test_resume",
                storage=storage,
            )
            objective = _make_demo_objective(tuner1, n_samples=100)
            tuner1.optimize(objective, n_trials=3, timeout=60)

            n_trials_1 = len(tuner1.study.trials)

            # Resume the same study
            tuner2 = OptunaTuner(
                study_name="test_resume",
                storage=storage,
                load_if_exists=True,
            )
            n_trials_2 = len(tuner2.study.trials)

            # Second instance should have same number of trials
            assert n_trials_2 == n_trials_1

    def test_sqlite_persistence(self):
        """SQLite study persists trials across instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_persist.db"
            storage = f"sqlite:///{db_path}"

            # Create and optimize
            tuner1 = OptunaTuner(
                study_name="test_persist",
                storage=storage,
            )
            objective = _make_demo_objective(tuner1, n_samples=100)
            tuner1.optimize(objective, n_trials=3, timeout=60)
            best_value_1 = tuner1.best_value

            # Re-open and check trials still exist
            tuner2 = OptunaTuner(
                study_name="test_persist",
                storage=storage,
                load_if_exists=True,
            )
            assert len(tuner2.study.trials) == 3
            assert tuner2.best_value == best_value_1

    def test_study_summary_property(self):
        """study_summary returns populated StudySummary after optimization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_summary",
                    mode="SWING",
                )

                # Before optimization
                summary = tuner.study_summary
                assert isinstance(summary, StudySummary)
                assert summary.n_trials == 0
                assert summary.best_value is None

                # After optimization
                objective = _make_demo_objective(tuner, n_samples=100)
                tuner.optimize(objective, n_trials=3, timeout=60)

                summary = tuner.study_summary
                assert summary.n_trials == 3
                assert summary.best_value is not None
                assert len(summary.best_params) > 0
                assert summary.storage_type == "sqlite"
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_empty_study_properties(self):
        """Properties return safe defaults when no trials exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(study_name="test_empty")
                assert tuner.best_params == {}
                assert tuner.best_value is None
                assert tuner.best_trial is None
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)


# ============================================================================
# save_results tests
# ============================================================================


class TestSaveResults:
    """save_results output tests."""

    def test_save_results_creates_json(self):
        """save_results creates a valid JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_save",
                    mode="SWING",
                )
                objective = _make_demo_objective(tuner, n_samples=100)
                tuner.optimize(objective, n_trials=3, timeout=60)

                output_path = Path(tmpdir) / "results.json"
                saved = tuner.save_results(str(output_path))

                assert Path(saved).exists()
                with open(saved) as f:
                    data = json.load(f)

                assert data["study_name"] == "test_save"
                assert data["mode"] == "SWING"
                assert data["best_value"] is not None
                assert len(data["best_params"]) > 0
                assert "timestamp" in data
                assert "storage" in data
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_save_results_empty_study(self):
        """save_results works with an empty study (no trials)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(study_name="test_save_empty")
                output_path = Path(tmpdir) / "empty_results.json"
                saved = tuner.save_results(str(output_path))

                assert Path(saved).exists()
                with open(saved) as f:
                    data = json.load(f)
                assert data["best_value"] is None
                assert data["best_params"] == {}
                assert data["n_trials"] == 0
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)


# ============================================================================
# list_studies and delete_study tests
# ============================================================================


class TestStudyManagement:
    """list_studies and delete_study function tests."""

    def test_list_studies_empty_dir(self):
        """list_studies returns empty list when no studies exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                studies = list_studies()
                assert isinstance(studies, list)
                assert len(studies) == 0
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_list_studies_after_optimization(self):
        """list_studies returns created study."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_list_me",
                    mode="SWING",
                )
                objective = _make_demo_objective(tuner, n_samples=100)
                tuner.optimize(objective, n_trials=3, timeout=60)

                studies = list_studies()
                names = [s["study_name"] for s in studies]
                assert "test_list_me" in names

                # Verify study details
                study_info = [s for s in studies if s["study_name"] == "test_list_me"][0]
                assert study_info["trial_count"] >= 3
                assert study_info["best_value"] is not None
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_delete_study_removes_db(self):
        """delete_study removes the study database file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_delete_me",
                    mode="SWING",
                )
                objective = _make_demo_objective(tuner, n_samples=100)
                tuner.optimize(objective, n_trials=3, timeout=60)

                # Verify study exists
                assert len(list_studies()) > 0

                # Delete the study
                result = delete_study("test_delete_me")
                assert result is True

                # Verify it's gone
                studies = list_studies()
                names = [s["study_name"] for s in studies]
                assert "test_delete_me" not in names
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_delete_nonexistent_study(self):
        """delete_study returns False for nonexistent study."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                result = delete_study("nonexistent_study")
                assert result is False
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)


# ============================================================================
# Helper function tests
# ============================================================================


class TestHelpers:
    """Helper function tests."""

    def test_resolve_studies_dir_default(self):
        """_resolve_studies_dir returns a Path with STUDIES_DIR."""
        # Clear env var
        old_val = os.environ.pop("V7_STUDIES_DIR", None)
        try:
            studies_dir = _resolve_studies_dir()
            assert isinstance(studies_dir, Path)
            assert STUDIES_DIR in str(studies_dir)
        finally:
            if old_val is not None:
                os.environ["V7_STUDIES_DIR"] = old_val

    def test_resolve_studies_dir_env_var(self):
        """_resolve_studies_dir respects V7_STUDIES_DIR env var."""
        os.environ["V7_STUDIES_DIR"] = "/tmp/v7_test_studies"
        try:
            studies_dir = _resolve_studies_dir()
            assert str(studies_dir) == "/tmp/v7_test_studies"
        finally:
            os.environ.pop("V7_STUDIES_DIR", None)

    def test_storage_url(self):
        """_storage_url builds correct SQLite URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                url = _storage_url("test_study")
                assert url.startswith("sqlite:///")
                assert "test_study" in url
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)

    def test_valid_modes(self):
        """VALID_MODES contains expected trading modes."""
        assert "SWING" in VALID_MODES
        assert "SCALP" in VALID_MODES
        assert "AGGRESSIVE_SCALP" in VALID_MODES
        assert len(VALID_MODES) == 3

    def test_constants(self):
        """Module constants have expected values."""
        assert DEFAULT_N_TRIALS == 50
        assert DEFAULT_TIMEOUT_SECONDS == 3600
        assert TPE_N_STARTUP_TRIALS == 10
        assert TPE_SEED == 42
        assert ASHA_MIN_RESOURCE == 1
        assert ASHA_REDUCTION_FACTOR == 3


# ============================================================================
# Trials dataframe test
# ============================================================================


class TestTrialsDataFrame:
    """trials_dataframe property tests."""

    def test_trials_dataframe_after_optimization(self):
        """trials_dataframe returns pandas DataFrame after optimization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["V7_STUDIES_DIR"] = tmpdir
            try:
                tuner = OptunaTuner(
                    study_name="test_df",
                    mode="SWING",
                )
                objective = _make_demo_objective(tuner, n_samples=100)
                tuner.optimize(objective, n_trials=3, timeout=60)

                df = tuner.trials_dataframe
                assert df is not None
                assert len(df) == 3
                assert "state" in df.columns or "values" in df.columns
            finally:
                os.environ.pop("V7_STUDIES_DIR", None)
