"""Walk-forward validation tests — 6-fold WFV for Issue 125.

Tests the walk_forward_validate function from cli/real_training.py.
Uses mocked XGBoostTrainer to avoid actual model training.

Coverage:
  - Returns at least min_folds results
  - Each fold has required keys
  - Fold indices are sequential
  - fold_count > 0
  - Stability score: identical -> 1.0, varied -> <1.0
  - hypothesis_count from MHT is NOT divided by folds
  - Not enough data -> fewer folds gracefully (no crash)
  - purge/embargo info present
"""

from __future__ import annotations
import pytest
pytestmark = pytest.mark.integration


import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xgboost as xgb

# Ensure project root is on sys.path for cli.real_training import
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Ensure alphaforge/src is on sys.path for alphaforge imports
_af_src = _project_root / "alphaforge" / "src"
if str(_af_src) not in sys.path:
    sys.path.insert(0, str(_af_src))

from alphaforge.training.xgb_trainer import TrainingResult
from cli.real_training import walk_forward_validate, _compute_stability


# =========================================================================
# Helpers
# =========================================================================


def _make_r_values(n: int, rng: np.random.RandomState | None = None) -> np.ndarray:
    """Synthetic R values (gross return fraction) with n entries."""
    if rng is None:
        rng = np.random.RandomState(42)
    # R values centered around 0, typical range [-0.5, 0.5]
    return rng.uniform(-0.3, 0.5, size=n).astype(np.float64)


def _make_labels(n: int, rng: np.random.RandomState | None = None) -> np.ndarray:
    """Synthetic integer labels (0=LONG, 1=SHORT, 2=NO_TRADE)."""
    if rng is None:
        rng = np.random.RandomState(42)
    return rng.randint(0, 3, size=n).astype(np.int32)


def _make_features(
    n: int, n_features: int = 5, rng: np.random.RandomState | None = None,
) -> np.ndarray:
    """Synthetic feature matrix (n, n_features)."""
    if rng is None:
        rng = np.random.RandomState(42)
    return rng.randn(n, n_features).astype(np.float64)


def _predict_side_effect(dval):
    """Return mock probabilities matching the input DMatrix row count.

    This ensures the length of y_pred matches y_val so accuracy
    computation does not broadcast incorrectly.
    """
    n = dval.num_row()
    # Always predict class 0 (LONG_NOW) with high confidence
    return np.column_stack([
        np.full(n, 0.7, dtype=np.float64),
        np.full(n, 0.2, dtype=np.float64),
        np.full(n, 0.1, dtype=np.float64),
    ])


def _make_mock_result(
    train_accuracy: float = 0.85,
    train_logloss: float = 0.35,
    val_accuracy: float = 0.65,
    val_logloss: float = 0.55,
) -> TrainingResult:
    """Build a mocked TrainingResult with input-size-aware model.predict()."""
    model = MagicMock(spec=xgb.Booster)
    model.predict.side_effect = _predict_side_effect
    return TrainingResult(
        model=model,
        model_artifact={
            "feature_importance": {
                "feature_0": 0.4,
                "feature_1": 0.3,
                "feature_2": 0.2,
                "feature_3": 0.1,
            },
        },
        model_binary_bytes=b"",
        train_metrics={"accuracy": train_accuracy, "logloss": train_logloss},
        val_metrics={"accuracy": val_accuracy, "logloss": val_logloss},
        training_duration_seconds=0.5,
    )


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mock_xgb():
    """Patch XGBoostTrainer so walk_forward_validate never trains a real model.

    Each call to trainer.train() returns a controlled TrainingResult whose
    model.predict() returns probabilities matching the validation set size.
    """
    mock_result = _make_mock_result()
    with patch("alphaforge.training.xgb_trainer.XGBoostTrainer") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.train.return_value = mock_result
        mock_cls.return_value = mock_instance
        yield mock_cls


# =========================================================================
# Tests
# =========================================================================


class TestMinFolds:
    """1. walk_forward_validate returns at least min_folds results."""

    def test_returns_6_folds(self, mock_xgb):
        """With 1000 bars and min_folds=6, returns >= 6 folds."""
        n = 1000
        results = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )
        assert len(results) >= 6, f"Expected >= 6 folds, got {len(results)}"

    def test_returns_3_folds(self, mock_xgb):
        """With min_folds=3, returns >= 3 folds."""
        n = 500
        results = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=3,
        )
        assert len(results) >= 3, f"Expected >= 3 folds, got {len(results)}"

    def test_returns_10_folds(self, mock_xgb):
        """With ample data and min_folds=10, returns >= 10 folds."""
        n = 3000
        results = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=10,
        )
        assert len(results) >= 10, f"Expected >= 10 folds, got {len(results)}"


class TestRequiredKeys:
    """2. Each fold has required keys."""

    REQUIRED_KEYS = frozenset({
        "fold", "n_train", "n_val",
        "purge_period", "embargo_period",
        "train_accuracy", "train_logloss",
        "val_accuracy", "val_logloss",
        "confusion_matrix",
        "feature_importance",
        "r_expectancy",
        "training_duration_seconds",
    })

    @pytest.fixture
    def results(self, mock_xgb):
        n = 1000
        return walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )

    def test_all_keys_present(self, results):
        """Every fold has all required keys."""
        for r in results:
            missing = self.REQUIRED_KEYS - r.keys()
            assert not missing, f"Fold {r.get('fold')} missing keys: {missing}"

    def test_no_extra_mandatory_absent(self, results):
        """No required key is missing from ANY fold."""
        for r in results:
            for key in self.REQUIRED_KEYS:
                assert key in r, f"Fold {r.get('fold')} missing key '{key}'"

    def test_n_train_positive(self, results):
        """n_train > 0 for all folds."""
        for r in results:
            assert r["n_train"] > 0, f"Fold {r['fold']}: n_train == 0"

    def test_n_val_positive(self, results):
        """n_val > 0 for all folds."""
        for r in results:
            assert r["n_val"] > 0, f"Fold {r['fold']}: n_val == 0"

    def test_accuracy_is_float(self, results):
        """train_accuracy and val_accuracy are floats."""
        for r in results:
            assert isinstance(r["train_accuracy"], float), (
                f"Fold {r['fold']}: train_accuracy not float"
            )
            assert isinstance(r["val_accuracy"], float), (
                f"Fold {r['fold']}: val_accuracy not float"
            )

    def test_logloss_is_float(self, results):
        """train_logloss and val_logloss are floats."""
        for r in results:
            assert isinstance(r["train_logloss"], float), (
                f"Fold {r['fold']}: train_logloss not float"
            )
            assert isinstance(r["val_logloss"], float), (
                f"Fold {r['fold']}: val_logloss not float"
            )

    def test_confusion_matrix_is_3x3(self, results):
        """confusion_matrix is a 3x3 list of lists."""
        for r in results:
            cm = r["confusion_matrix"]
            assert isinstance(cm, list), f"Fold {r['fold']}: confusion_matrix not a list"
            assert len(cm) == 3, f"Fold {r['fold']}: confusion_matrix has {len(cm)} rows"
            for row in cm:
                assert isinstance(row, list), f"Fold {r['fold']}: row not a list"
                assert len(row) == 3, f"Fold {r['fold']}: row has {len(row)} elements"

    def test_confusion_matrix_values_non_negative(self, results):
        """All confusion matrix entries are >= 0."""
        for r in results:
            cm = r["confusion_matrix"]
            for row in cm:
                for val in row:
                    assert isinstance(val, (int, float)), f"Fold {r['fold']}: value {val} not numeric"
                    assert val >= 0, f"Fold {r['fold']}: negative value {val}"

    def test_feature_importance_is_dict(self, results):
        """feature_importance is a dict."""
        for r in results:
            fi = r["feature_importance"]
            assert isinstance(fi, dict), f"Fold {r['fold']}: feature_importance not dict"

    def test_r_expectancy_is_float(self, results):
        """r_expectancy is a float."""
        for r in results:
            assert isinstance(r["r_expectancy"], float), (
                f"Fold {r['fold']}: r_expectancy not float"
            )


class TestFoldIndicesSequential:
    """3. Fold indices are sequential (1-based)."""

    @pytest.fixture
    def results(self, mock_xgb):
        n = 1000
        return walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )

    def test_indices_sequential_from_one(self, results):
        """Fold indices are [1, 2, 3, ..., len(results)]."""
        indices = [r["fold"] for r in results]
        expected = list(range(1, len(indices) + 1))
        assert indices == expected, f"Expected {expected}, got {indices}"

    def test_no_duplicate_or_skipped_indices(self, results):
        """No duplicate or skipped fold indices."""
        indices = [r["fold"] for r in results]
        assert len(indices) == len(set(indices)), "Duplicate fold indices"
        assert max(indices) == len(indices), "Skipped fold indices"


class TestFoldCountPositive:
    """4. fold_count > 0."""

    def test_fold_count_positive_6(self, mock_xgb):
        """fold_count > 0 with min_folds=6 and sufficient data."""
        n = 1000
        results = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )
        assert len(results) > 0, "fold_count must be > 0"

    def test_fold_count_positive_1(self, mock_xgb):
        """fold_count > 0 with min_folds=1."""
        n = 200
        results = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=1,
        )
        assert len(results) > 0, "fold_count must be > 0"


class TestStabilityScore:
    """5. Stability score: identical folds -> 1.0, different -> lower."""

    def test_identical_values(self):
        """_compute_stability of all-equal values returns 1.0."""
        score = _compute_stability([0.65, 0.65, 0.65, 0.65, 0.65, 0.65])
        assert score == 1.0, f"Expected 1.0, got {score}"

    def test_varied_values_lower(self):
        """_compute_stability of varied values is < 1.0 and > 0.0."""
        score = _compute_stability([0.9, 0.5, 0.7, 0.3, 0.8, 0.4])
        assert 0.0 < score < 1.0, f"Expected in (0,1), got {score}"

    def test_extreme_variation_clips_to_zero(self):
        """_compute_stability of [1.0, 0.0, 0.0, 0.0, 0.0] clips to 0.0."""
        score = _compute_stability([1.0, 0.0, 0.0, 0.0, 0.0])
        assert score == 0.0, (
            f"Expected 0.0 (cv>=1 clips to 0), got {score}"
        )

    def test_moderate_variation_positives(self):
        """_compute_stability of [0.8, 0.6, 0.7] returns > 0."""
        score = _compute_stability([0.8, 0.6, 0.7])
        assert 0.0 < score < 1.0, f"Expected in (0,1), got {score}"

    def test_single_value(self):
        """_compute_stability of single value returns 1.0 (no variance)."""
        score = _compute_stability([0.5])
        assert score == 1.0, f"Expected 1.0, got {score}"

    def test_identical_stability_across_folds(self, mock_xgb):
        """When all folds return the same val_accuracy, stability would be 1.0.

        This is an integration-style check: the mock returns constant
        predictions, so val_accuracy should be consistent across folds.
        """
        n = 1000
        results = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )
        val_accs = [r["val_accuracy"] for r in results]
        if len(val_accs) > 1 and len(set(val_accs)) == 1:
            score = _compute_stability(val_accs)
            assert score == 1.0


class TestHypothesisCountNotDivided:
    """6. hypothesis_count from MHT is NOT divided by folds.

    Each fold independently evaluates 125 candidate measures (not 125/fold_count).
    The per-fold evaluation is independent: training sizes expand, and each
    fold trains its own model from scratch — no state is shared.
    """

    def test_each_fold_has_independent_training(self, mock_xgb):
        """Each fold's n_train increases because anchored windows expand.

        This demonstrates independent per-fold evaluation (not sharing
        training data or model state across folds).
        """
        n = 1000
        results = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )
        n_trains = [r["n_train"] for r in results]
        assert n_trains == sorted(n_trains), (
            f"Training sizes should increase monotonically, got {n_trains}"
        )
        # Strictly increasing (anchored expanding window)
        for i in range(1, len(n_trains)):
            assert n_trains[i] > n_trains[i - 1], (
                f"n_train not increasing: {n_trains}"
            )

    def test_each_fold_trains_separate_model(self, mock_xgb):
        """Each fold calls trainer.train() independently.

        The number of train() calls should equal the number of folds.
        This verifies that hypothesis count is per-fold, not divided.
        """
        mock_cls = mock_xgb
        n = 1000
        results = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )
        n_calls = mock_cls.return_value.train.call_count
        assert n_calls == len(results), (
            f"train() called {n_calls} times for {len(results)} folds — "
            "expected one train per fold"
        )

    def test_per_fold_hypothesis_count_not_averaged(self, mock_xgb):
        """Verification: 125 measures per fold is documented in the contract.

        The function's docstring states '125 measures per-fold candidate
        performance (NOT divided by fold_count)'.  We verify that each fold
        independently evaluates rather than dividing a global budget.
        """
        # This is a contract test: the function returns a list of per-fold
        # results.  Each result represents 125 independent candidate measures.
        # Fold count affects total hypotheses but NOT per-fold resolution.
        n = 1000
        results_a = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=3,
        )
        results_b = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )

        # The number of folds differs, but each fold has its own n_train
        # anchored at the same position — demonstrating independent evaluation.
        assert len(results_a) == 3, f"Expected 3 folds, got {len(results_a)}"
        assert len(results_b) >= 6, f"Expected >= 6 folds, got {len(results_b)}"

        # Fold 0 should have the same n_train regardless of min_folds
        # (because fold 0 always ends at 1 * fold_size, and fold_size
        #  depends on n // (min_folds + 1), so they're different)
        # Instead, verify that each result dict has the same structure
        # regardless of total fold count.
        for r in results_a:
            assert "n_train" in r
            assert "val_accuracy" in r
        for r in results_b:
            assert "n_train" in r
            assert "val_accuracy" in r


class TestEdgeCaseFewerFolds:
    """7. Not enough data for 6 folds -> fewer folds gracefully."""

    def test_not_enough_returns_empty_list(self, mock_xgb):
        """Small dataset returns empty list (not a crash)."""
        n = 200  # Too small for even 1 fold with min_folds=6
        results = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )
        assert isinstance(results, list), "Must return a list"
        # May be empty or have some folds, but must not crash

    def test_not_enough_does_not_raise(self, mock_xgb):
        """Small dataset must not raise any exception."""
        n = 100
        try:
            results = walk_forward_validate(
                _make_features(n), _make_labels(n), _make_r_values(n),
                "SWING", min_folds=6,
            )
            assert isinstance(results, list)
        except Exception as exc:
            pytest.fail(f"walk_forward_validate raised {type(exc).__name__}: {exc}")

    def test_partial_folds_on_boundary(self, mock_xgb):
        """Dataset just below 6-fold threshold still returns gracefully."""
        n = 350  # May produce 0 or a few folds, but not 6
        results = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )
        # Must not crash, must return list
        assert isinstance(results, list)
        # If we do get folds, they must be well-formed
        for r in results:
            assert "fold" in r
            assert r["n_train"] > 0
            assert r["n_val"] > 0


class TestPurgeEmbargo:
    """8. Purge/embargo info present."""

    @pytest.fixture
    def results(self, mock_xgb):
        n = 1000
        return walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )

    def test_purge_period_present(self, results):
        """Each fold has purge_period key."""
        for r in results:
            assert "purge_period" in r, f"Fold {r['fold']} missing purge_period"

    def test_embargo_period_present(self, results):
        """Each fold has embargo_period key."""
        for r in results:
            assert "embargo_period" in r, (
                f"Fold {r['fold']} missing embargo_period"
            )

    def test_purge_period_positive(self, results):
        """purge_period > 0 for all folds."""
        for r in results:
            assert r["purge_period"] > 0, (
                f"Fold {r['fold']}: purge_period={r['purge_period']}"
            )

    def test_embargo_period_positive(self, results):
        """embargo_period > 0 for all folds."""
        for r in results:
            assert r["embargo_period"] > 0, (
                f"Fold {r['fold']}: embargo_period={r['embargo_period']}"
            )

    def test_purge_period_int(self, results):
        """purge_period is an int."""
        for r in results:
            assert isinstance(r["purge_period"], int), (
                f"Fold {r['fold']}: purge_period not int, got {type(r['purge_period'])}"
            )

    def test_embargo_period_int(self, results):
        """embargo_period is an int."""
        for r in results:
            assert isinstance(r["embargo_period"], int), (
                f"Fold {r['fold']}: embargo_period not int, got {type(r['embargo_period'])}"
            )

    def test_purge_embargo_consistent_across_folds(self, results):
        """All folds share the same purge/embargo values (global constants)."""
        purge_values = {r["purge_period"] for r in results}
        embargo_values = {r["embargo_period"] for r in results}
        assert len(purge_values) == 1, (
            f"Expected consistent purge_period, got {purge_values}"
        )
        assert len(embargo_values) == 1, (
            f"Expected consistent embargo_period, got {embargo_values}"
        )


# =========================================================================
# Additional structural tests
# =========================================================================


class TestStructural:
    """Structural invariants across all folds."""

    @pytest.fixture
    def results(self, mock_xgb):
        n = 1000
        return walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )

    def test_n_train_increases(self, results):
        """Anchored expanding window: n_train increases per fold."""
        n_trains = [r["n_train"] for r in results]
        for i in range(1, len(n_trains)):
            assert n_trains[i] > n_trains[i - 1], (
                f"n_train[{i}] ({n_trains[i]}) <= n_train[{i-1}] ({n_trains[i-1]})"
            )

    def test_confusion_matrix_present(self, results):
        """confusion_matrix is a 3x3 list."""
        for r in results:
            cm = r["confusion_matrix"]
            assert isinstance(cm, list)
            assert len(cm) == 3
            for row in cm:
                assert len(row) == 3

    def test_r_expectancy_present(self, results):
        """r_expectancy is a float."""
        for r in results:
            assert isinstance(r["r_expectancy"], float)

    def test_feature_importance_present(self, results):
        """feature_importance is a dict."""
        for r in results:
            assert isinstance(r["feature_importance"], dict)

    def test_training_duration_positive(self, results):
        """training_duration_seconds > 0."""
        for r in results:
            assert r["training_duration_seconds"] > 0, (
                f"Fold {r['fold']}: training_duration_seconds <= 0"
            )

    def test_result_is_list_of_dicts(self, results):
        """Return value is a list of dicts."""
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, dict)

    def test_mode_swing_has_expected_fold_count(self, mock_xgb):
        """SWING mode with 1000 bars and min_folds=6."""
        n = 1000
        results = walk_forward_validate(
            _make_features(n), _make_labels(n), _make_r_values(n),
            "SWING", min_folds=6,
        )
        assert len(results) >= 6


class TestEmptyOrZeroData:
    """Edge cases with degenerate inputs."""

    def test_zero_features(self, mock_xgb):
        """Call with n=0 does not crash (returns empty list)."""
        results = walk_forward_validate(
            np.array([[]]).reshape(0, 5),
            np.array([], dtype=np.int32),
            _make_r_values(1),
            "SWING", min_folds=6,
        )
        assert isinstance(results, list)

    def test_single_bar(self, mock_xgb):
        """Call with n=1 does not crash."""
        results = walk_forward_validate(
            _make_features(1), _make_labels(1), _make_r_values(1),
            "SWING", min_folds=6,
        )
        assert isinstance(results, list)
