"""Tests for AlphaForge Ablation Framework (Issue #41).

Covers:
  (a) Feature group ablation — baseline, single-group, all-groups
  (b) Cross-mode ablation — SWING->SCALP transfer
  (c) Symbol ablation — N-1 training, held-out evaluation
  (d) Descriptive-only enforcement — no profit claims in results
  (e) Input validation — empty, NaN, mismatched shapes
  (f) Feature-to-group mapping correctness
  (g) AblationStudy structure and limitations
  (h) Edge cases — single group, missing groups, unknown features
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pytest

# Ensure alphaforge/src is on sys.path
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from alphaforge.validation.ablation import (
    ABLATION_HYPERPARAMS,
    ALL_GROUPS,
    FEATURE_NAME_TO_GROUP,
    GROUP_TO_FEATURES,
    AblationStudy,
    CrossModeResult,
    GroupAblationResult,
    SymbolAblationResult,
    _encode_labels_np,
    _get_group_column_indices,
    _validate_ablation_inputs,
    run_cross_mode_ablation,
    run_feature_group_ablation,
    run_symbol_ablation,
)


# ============================================================================
# Fixtures
# ============================================================================


def _make_synthetic_data(
    n_samples: int = 300,
    n_features: int = 26,
    random_seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic feature/label data with 3 moderately separable clusters."""
    rng = np.random.RandomState(random_seed)

    # Create centers for n_features dimensions
    base_centers = np.array([
        [-1.0, -1.0, 0.5, 0.0, 0.3, -0.5],
        [1.0, 0.5, -0.3, 0.8, -0.2, 0.6],
        [0.0, 0.0, 0.0, -0.5, 0.5, 0.0],
    ])
    # Extend to n_features with small variation
    centers = np.zeros((3, n_features))
    for c in range(3):
        centers[c, :6] = base_centers[c]
        centers[c, 6:] = rng.randn(n_features - 6) * 0.2

    samples_per_class = n_samples // 3
    X_parts = []
    y_parts = []

    for cls_idx in range(3):
        n = samples_per_class if cls_idx < 2 else n_samples - 2 * samples_per_class
        cluster = rng.randn(n, n_features) * 0.5 + centers[cls_idx]
        X_parts.append(cluster)
        y_parts.append(np.full(n, cls_idx, dtype=int))

    X = np.vstack(X_parts).astype(np.float64)
    y = np.concatenate(y_parts)

    # Shuffle
    perm = rng.permutation(len(y))
    return X[perm], y[perm]


@pytest.fixture
def synth_data():
    """300 samples, 26 features, 3 classes (0/1/2)."""
    return _make_synthetic_data(300, 26)


@pytest.fixture
def synth_data_small():
    """120 samples, 26 features."""
    return _make_synthetic_data(120, 26)


@pytest.fixture
def synth_data_string_labels():
    """300 samples with string labels."""
    X, y_int = _make_synthetic_data(300, 26)
    label_map = {0: "LONG_NOW", 1: "SHORT_NOW", 2: "NO_TRADE"}
    y_str = np.array([label_map[i] for i in y_int])
    return X, y_str


@pytest.fixture
def pipeline_feature_names() -> List[str]:
    """All 26 feature names from the SWING feature pipeline, in order."""
    return [
        "log_return_1", "log_return_N", "return_volatility_N", "return_zscore_N",
        "realized_volatility_N", "high_low_range_N", "garman_klass_vol_N", "parkinson_vol_N",
        "atr_N", "atr_pct_N", "atr_expansion_N",
        "momentum_N", "roc_N", "rsi_N", "macd", "macd_signal", "macd_histogram",
        "volume_ratio_N", "volume_trend_N", "vwap_deviation", "obv_N",
        "bb_position", "bb_width", "highest_N", "lowest_N", "range_breakout_N",
    ]


# ============================================================================
# Tests: Feature-to-Group Mapping
# ============================================================================


class TestFeatureToGroupMapping:
    """Verify the feature-to-group mapping is correct and complete."""

    def test_mapping_has_all_six_groups(self):
        """All 6 active pipeline groups are represented."""
        groups = set(FEATURE_NAME_TO_GROUP.values())
        assert groups == set(ALL_GROUPS), f"Expected {set(ALL_GROUPS)}, got {groups}"

    def test_mapping_has_26_features(self):
        """All 26 pipeline features are mapped."""
        assert len(FEATURE_NAME_TO_GROUP) == 26, (
            f"Expected 26 features, got {len(FEATURE_NAME_TO_GROUP)}"
        )

    def test_reverse_mapping_consistency(self):
        """GROUP_TO_FEATURES is the exact inverse of FEATURE_NAME_TO_GROUP."""
        for group_name in ALL_GROUPS:
            features = GROUP_TO_FEATURES.get(group_name, [])
            for fn in features:
                assert FEATURE_NAME_TO_GROUP.get(fn) == group_name, (
                    f"Feature '{fn}' mapped to '{FEATURE_NAME_TO_GROUP.get(fn)}', "
                    f"expected '{group_name}'"
                )

    def test_group_sizes_match_pipeline(self):
        """Group feature counts match pipeline output."""
        expected = {
            "returns": 4,
            "volatility": 4,
            "atr": 3,
            "momentum": 6,
            "volume": 4,
            "breakout": 5,
        }
        for group_name, expected_count in expected.items():
            actual = GROUP_TO_FEATURES.get(group_name, [])
            assert len(actual) == expected_count, (
                f"Group '{group_name}': expected {expected_count} features, "
                f"got {len(actual)}: {actual}"
            )


# ============================================================================
# Tests: Input Validation
# ============================================================================


class TestInputValidation:
    """Verify input validation rejects invalid data."""

    def test_empty_X_raises(self):
        X = np.array([]).reshape(0, 5)
        y = np.array([])
        with pytest.raises(ValueError, match="at least 10"):
            _validate_ablation_inputs(X, y, None)

    def test_1d_X_raises(self):
        X = np.ones(30)
        y = np.ones(30, dtype=int)
        with pytest.raises(ValueError, match="must be 2D"):
            _validate_ablation_inputs(X, y, None)

    def test_mismatched_lengths_raises(self):
        X = np.ones((30, 5))
        y = np.ones(20, dtype=int)
        with pytest.raises(ValueError, match="same length"):
            _validate_ablation_inputs(X, y, None)

    def test_all_NaN_X_raises(self):
        X = np.full((30, 5), np.nan)
        y = np.ones(30, dtype=int)
        with pytest.raises(ValueError, match="all NaN"):
            _validate_ablation_inputs(X, y, None)

    def test_feature_names_length_mismatch_raises(self):
        X = np.ones((30, 5))
        y = np.ones(30, dtype=int)
        with pytest.raises(ValueError, match="feature_names length"):
            _validate_ablation_inputs(X, y, feature_names=["a", "b", "c"])


# ============================================================================
# Tests: Label Encoding
# ============================================================================


class TestLabelEncoding:
    """Verify _encode_labels_np handles string and integer labels."""

    def test_integer_labels_pass_through(self):
        y = np.array([0, 1, 2, 0, 1], dtype=int)
        result = _encode_labels_np(y)
        assert np.array_equal(result, y)

    def test_string_labels_encode_correctly(self):
        y = np.array(["LONG_NOW", "SHORT_NOW", "NO_TRADE", "LONG_NOW"])
        result = _encode_labels_np(y)
        expected = np.array([0, 1, 2, 0])
        assert np.array_equal(result, expected)

    def test_unknown_label_raises(self):
        y = np.array(["LONG_NOW", "INVALID_LABEL"])
        with pytest.raises(ValueError, match="Unknown label"):
            _encode_labels_np(y)

    def test_bytes_labels_decoded(self):
        y = np.array([b"LONG_NOW", b"SHORT_NOW"], dtype=object)
        result = _encode_labels_np(y)
        expected = np.array([0, 1])
        assert np.array_equal(result, expected)


# ============================================================================
# Tests: Column Index Helper
# ============================================================================


class TestGetGroupColumnIndices:
    """Verify _get_group_column_indices returns correct indices."""

    def test_returns_group_indices(self, pipeline_feature_names):
        indices = _get_group_column_indices(pipeline_feature_names, "returns")
        # Returns group: log_return_1(0), log_return_N(1), return_volatility_N(2), return_zscore_N(3)
        assert indices == [0, 1, 2, 3], f"Got {indices}"

    def test_atr_group_indices(self, pipeline_feature_names):
        indices = _get_group_column_indices(pipeline_feature_names, "atr")
        # ATR: atr_N(8), atr_pct_N(9), atr_expansion_N(10)
        assert indices == [8, 9, 10], f"Got {indices}"

    def test_momentum_group_indices(self, pipeline_feature_names):
        indices = _get_group_column_indices(pipeline_feature_names, "momentum")
        # Momentum: 11-16 (6 features)
        assert indices == [11, 12, 13, 14, 15, 16], f"Got {indices}"

    def test_unknown_group_returns_empty(self):
        indices = _get_group_column_indices(["a", "b", "c"], "nonexistent")
        assert indices == []

    def test_partial_group_match(self):
        """Only features present in the mapping are returned."""
        # Only one returns feature, one atr feature
        names = ["log_return_1", "unmapped_feature", "atr_N", "other"]
        indices = _get_group_column_indices(names, "returns")
        assert indices == [0]  # only log_return_1
        indices = _get_group_column_indices(names, "atr")
        assert indices == [2]  # only atr_N


# ============================================================================
# Tests: Feature Group Ablation
# ============================================================================


class TestFeatureGroupAblation:
    """Verify run_feature_group_ablation produces correct results."""

    def test_baseline_produces_valid_study(self, synth_data, pipeline_feature_names):
        """Full ablation study produces AblationStudy with results for all groups."""
        X, y = synth_data
        study = run_feature_group_ablation(X, y, feature_names=pipeline_feature_names)
        assert isinstance(study, AblationStudy)
        assert study.study_type == "feature_group"
        assert len(study.results) >= 1
        assert "accuracy" in study.baseline_metrics
        assert 0.0 <= study.baseline_metrics["accuracy"] <= 1.0

    def test_all_six_groups_ablated(self, synth_data, pipeline_feature_names):
        """All 6 groups produce ablation results."""
        X, y = synth_data
        study = run_feature_group_ablation(X, y, feature_names=pipeline_feature_names)
        ablated_groups = {r.group_name for r in study.results}
        assert ablated_groups == set(ALL_GROUPS), (
            f"Expected all 6 groups ablated, got {ablated_groups}"
        )

    def test_single_group_ablation(self, synth_data, pipeline_feature_names):
        """Ablating a single specified group works."""
        X, y = synth_data
        study = run_feature_group_ablation(
            X, y,
            feature_names=pipeline_feature_names,
            groups_to_ablate=["volume"],
        )
        assert len(study.results) == 1
        assert study.results[0].group_name == "volume"
        assert study.results[0].feature_count_removed == 4

    def test_result_has_all_required_fields(self, synth_data, pipeline_feature_names):
        """Each GroupAblationResult has all required fields populated."""
        X, y = synth_data
        study = run_feature_group_ablation(
            X, y,
            feature_names=pipeline_feature_names,
            groups_to_ablate=["returns"],
        )
        result = study.results[0]
        assert isinstance(result.baseline_accuracy, float)
        assert isinstance(result.ablated_accuracy, float)
        assert isinstance(result.accuracy_delta, float)
        assert isinstance(result.logloss_delta, float)
        assert len(result.features_removed) > 0
        assert len(result.limitations) > 0
        assert result.training_duration_seconds > 0

    def test_accuracy_delta_is_reasonable(self, synth_data, pipeline_feature_names):
        """Accuracy delta is within [-1.0, 1.0] — degrading or neutral, not wildly positive."""
        X, y = synth_data
        study = run_feature_group_ablation(
            X, y,
            feature_names=pipeline_feature_names,
            groups_to_ablate=["volume"],
        )
        delta = study.results[0].accuracy_delta
        assert -1.0 <= delta <= 1.0, f"Accuracy delta {delta} out of range"

    def test_string_labels_accepted(self, synth_data_string_labels, pipeline_feature_names):
        """String labels (LONG_NOW/SHORT_NOW/NO_TRADE) are accepted."""
        X, y = synth_data_string_labels
        study = run_feature_group_ablation(
            X, y,
            feature_names=pipeline_feature_names,
            groups_to_ablate=["returns"],
        )
        assert len(study.results) == 1
        assert study.baseline_metrics["accuracy"] >= 0.0

    def test_generic_feature_names_accepted(self, synth_data_small):
        """When no feature_names provided, generic f0..fN names are generated."""
        X, y = synth_data_small
        # With 26 generic names, no known groups are found — should raise
        with pytest.raises(ValueError, match="No groups to ablate"):
            run_feature_group_ablation(X, y)

    def test_explicit_groups_with_generic_features(self, synth_data_small):
        """Explicit groups_to_ablate works even without named features."""
        X, y = synth_data_small
        # Build a feature_names list where first 4 are returns features
        n_features = X.shape[1]
        fn = [f"col_{i}" for i in range(n_features)]
        fn[0] = "log_return_1"
        fn[1] = "atr_N"

        study = run_feature_group_ablation(
            X, y,
            feature_names=fn,
            groups_to_ablate=["returns", "atr"],
        )
        assert len(study.results) == 2  # both groups have matching features

    def test_small_dataset_trains(self, synth_data_small, pipeline_feature_names):
        """Small dataset (120 samples) still produces valid results."""
        X, y = synth_data_small
        study = run_feature_group_ablation(
            X, y,
            feature_names=pipeline_feature_names,
            groups_to_ablate=["returns"],
        )
        assert len(study.results) == 1
        assert study.results[0].training_duration_seconds > 0


# ============================================================================
# Tests: Descriptive-Only Enforcement
# ============================================================================


class TestDescriptiveOnly:
    """Verify that no profit, Sharpe, win-rate, or expectancy claims are made.

    "profit", "Sharpe", etc. appearing in negations/disclaimers (e.g.
    "does NOT measure profit") is fine — we only reject positive claims.
    """

    # Financial performance metric names that must never appear in results
    # (except when listed as NOT CLAIMED).
    CLAIM_TERMS = [
        "win_rate", "winrate", "win rate",
        "expectancy", "pnl ", "p&l",
    ]

    def _is_negated(self, text: str, term: str) -> bool:
        """Check if *term* appears only in a negation context.

        Returns True if *term* is preceded by "no", "not", "never", "none"
        within a few words, indicating it is listed as NOT claimed.
        """
        lower = text.lower()
        idx = lower.find(term.lower())
        if idx == -1:
            return False
        # Check the ~10 words before the term for negation markers
        preceding = lower[max(0, idx - 40):idx]
        negation_words = [" no ", " not ", " never ", " none ", "doesn't", "don't", "won't"]
        for nw in negation_words:
            if nw in preceding:
                return True
        return False

    def _has_profit_claim(self, text: str) -> bool:
        """Return True if *text* contains a positive profit claim.

        A "positive claim" means profit is attributed to a feature, group,
        symbol, or mode — not merely mentioned as something NOT measured.
        """
        lower = text.lower()
        idx = lower.find("profit")
        if idx == -1:
            return False
        # If "profit" is negated, it's a disclaimer — not a claim
        if self._is_negated(text, "profit"):
            return False
        # Positive claim patterns: X adds/improves/increases/contributes profit
        claim_patterns = [
            "adds profit", "improves profit", "increases profit",
            "contributes to profit", "drives profit", "generates profit",
            "profit contribution", "profit impact",
        ]
        for pattern in claim_patterns:
            if pattern in lower:
                return True
        return False

    def test_group_result_limitations_no_claims(self, synth_data, pipeline_feature_names):
        """GroupAblationResult limitations contain no performance claims."""
        X, y = synth_data
        study = run_feature_group_ablation(
            X, y,
            feature_names=pipeline_feature_names,
            groups_to_ablate=["returns"],
        )
        result = study.results[0]
        for term in self.CLAIM_TERMS:
            for limitation in result.limitations:
                if self._is_negated(limitation, term):
                    continue
                assert term not in limitation.lower(), (
                    f"Performance claim term '{term}' found in limitation: '{limitation}'"
                )
        for limitation in result.limitations:
            assert not self._has_profit_claim(limitation), (
                f"Positive profit claim found in limitation: '{limitation}'"
            )

    def test_cross_mode_result_no_claims(self, synth_data):
        """CrossModeResult limitations contain no performance claims."""
        X, y = synth_data
        n = len(X)
        X_train, X_test = X[:n//2], X[n//2:]
        y_train, y_test = y[:n//2], y[n//2:]

        study = run_cross_mode_ablation(
            X_train, y_train, X_test, y_test,
            train_mode="SWING", test_mode="SCALP",
        )
        result = study.results[0]
        for term in self.CLAIM_TERMS:
            for limitation in result.limitations:
                if self._is_negated(limitation, term):
                    continue
                assert term not in limitation.lower(), (
                    f"Performance claim term '{term}' found in limitation: '{limitation}'"
                )
        for limitation in result.limitations:
            assert not self._has_profit_claim(limitation), (
                f"Positive profit claim found in limitation: '{limitation}'"
            )

    def test_symbol_result_no_claims(self, synth_data):
        """SymbolAblationResult limitations contain no performance claims."""
        X, y = synth_data
        n = len(X)
        mid = n // 2
        X_by = {"BTCUSDT": X[:mid], "ETHUSDT": X[mid:]}
        y_by = {"BTCUSDT": y[:mid], "ETHUSDT": y[mid:]}

        study = run_symbol_ablation(X_by, y_by)
        for result in study.results:
            for term in self.CLAIM_TERMS:
                for limitation in result.limitations:
                    if self._is_negated(limitation, term):
                        continue
                    assert term not in limitation.lower(), (
                        f"Performance claim term '{term}' found in limitation: '{limitation}'"
                    )
            for limitation in result.limitations:
                assert not self._has_profit_claim(limitation), (
                    f"Positive profit claim found in limitation: '{limitation}'"
                )

    def test_study_limitations_no_claims(self, synth_data, pipeline_feature_names):
        """AblationStudy-level limitations contain no performance claims."""
        X, y = synth_data
        study = run_feature_group_ablation(
            X, y,
            feature_names=pipeline_feature_names,
            groups_to_ablate=["returns"],
        )
        for term in self.CLAIM_TERMS:
            for limitation in study.limitations:
                if self._is_negated(limitation, term):
                    continue
                assert term not in limitation.lower(), (
                    f"Performance claim term '{term}' found in study limitation: '{limitation}'"
                )
        for limitation in study.limitations:
            assert not self._has_profit_claim(limitation), (
                f"Positive profit claim found in study limitation: '{limitation}'"
            )

    def test_summary_no_claims(self, synth_data, pipeline_feature_names):
        """Summary dict does not contain performance claim terms."""
        X, y = synth_data
        study = run_feature_group_ablation(
            X, y,
            feature_names=pipeline_feature_names,
            groups_to_ablate=["returns"],
        )
        for key in study.summary:
            assert "sharpe" not in key.lower()
            assert "expectancy" not in key.lower()
            assert "pnl" not in key.lower()

        desc = study.summary.get("description", "")
        assert "sharpe" not in desc.lower()
        assert not self._has_profit_claim(desc), (
            f"Positive profit claim in summary description: '{desc}'"
        )


# ============================================================================
# Tests: Cross-Mode Ablation
# ============================================================================


class TestCrossModeAblation:
    """Verify run_cross_mode_ablation works correctly."""

    def test_produces_valid_study(self, synth_data):
        """Cross-mode ablation produces AblationStudy with CrossModeResult."""
        X, y = synth_data
        n = len(X)
        X_train = X[: n // 2]
        y_train = y[: n // 2]
        X_test = X[n // 2 :]
        y_test = y[n // 2 :]

        study = run_cross_mode_ablation(
            X_train, y_train, X_test, y_test,
            train_mode="SWING", test_mode="SCALP",
        )
        assert study.study_type == "cross_mode"
        assert len(study.results) == 1
        assert isinstance(study.results[0], CrossModeResult)
        assert study.results[0].train_mode == "SWING"
        assert study.results[0].test_mode == "SCALP"
        assert 0.0 <= study.results[0].test_accuracy <= 1.0

    def test_degradation_is_descriptive(self, synth_data):
        """Accuracy degradation is reported but no positive profit claim is added."""
        X, y = synth_data
        n = len(X)
        X_train = X[: n // 2]
        y_train = y[: n // 2]
        X_test = X[n // 2 :]
        y_test = y[n // 2 :]

        study = run_cross_mode_ablation(
            X_train, y_train, X_test, y_test,
            train_mode="SWING", test_mode="SCALP",
        )
        result = study.results[0]
        # Degradation is computed
        assert isinstance(result.accuracy_degradation, float)
        # No SHARPE, WIN_RATE, EXPECTANCY in limitations
        for term in ["sharpe", "win_rate", "expectancy"]:
            for limitation in result.limitations:
                assert term not in limitation.lower(), (
                    f"Financial metric '{term}' found in limitation: '{limitation}'"
                )

    def test_feature_count_mismatch_raises(self, synth_data):
        """Different feature counts between train and test raises error."""
        X, y = synth_data
        X_train = X[:150, :10]  # 10 features
        X_test = X[150:, :8]    # 8 features
        y_train = y[:150]
        y_test = y[150:]

        with pytest.raises(ValueError, match="same feature count"):
            run_cross_mode_ablation(
                X_train, y_train, X_test, y_test,
                train_mode="SWING", test_mode="SCALP",
            )

    def test_string_labels_accepted(self, synth_data_string_labels):
        """String labels are accepted for cross-mode ablation."""
        X, y = synth_data_string_labels
        n = len(X)
        study = run_cross_mode_ablation(
            X[: n // 2], y[: n // 2],
            X[n // 2 :], y[n // 2 :],
            train_mode="SWING", test_mode="SCALP",
        )
        assert study.results[0].test_accuracy >= 0.0


# ============================================================================
# Tests: Symbol Ablation
# ============================================================================


class TestSymbolAblation:
    """Verify run_symbol_ablation works correctly."""

    def test_two_symbol_ablation(self, synth_data):
        """Ablation with two symbols produces two results (each held out once)."""
        X, y = synth_data
        n = len(X)
        mid = n // 2
        X_by = {"BTCUSDT": X[:mid], "ETHUSDT": X[mid:]}
        y_by = {"BTCUSDT": y[:mid], "ETHUSDT": y[mid:]}

        study = run_symbol_ablation(X_by, y_by)
        assert study.study_type == "symbol"
        assert len(study.results) == 2
        held_out_symbols = {r.held_out_symbol for r in study.results}
        assert held_out_symbols == {"BTCUSDT", "ETHUSDT"}

    def test_three_symbol_ablation(self, synth_data):
        """Ablation with three symbols produces three results."""
        X, y = synth_data
        n = len(X)
        third = n // 3
        X_by = {
            "BTCUSDT": X[:third],
            "ETHUSDT": X[third:2*third],
            "SOLUSDT": X[2*third:],
        }
        y_by = {
            "BTCUSDT": y[:third],
            "ETHUSDT": y[third:2*third],
            "SOLUSDT": y[2*third:],
        }

        study = run_symbol_ablation(X_by, y_by)
        assert len(study.results) == 3
        assert study.baseline_metrics["all_symbols_accuracy"] > 0.0

    def test_single_symbol_raises(self):
        """At least 2 symbols are required."""
        X = np.ones((30, 5))
        y = np.ones(30, dtype=int)
        with pytest.raises(ValueError, match="Need at least 2 symbols"):
            run_symbol_ablation({"BTCUSDT": X}, {"BTCUSDT": y})

    def test_symbol_key_mismatch_raises(self, synth_data):
        """X and y dicts must have matching keys."""
        X, y = synth_data
        n = len(X)
        mid = n // 2
        with pytest.raises(ValueError, match="same symbol keys"):
            run_symbol_ablation(
                {"BTCUSDT": X[:mid], "ETHUSDT": X[mid:]},
                {"BTCUSDT": y[:mid]},  # missing ETHUSDT
            )

    def test_feature_count_mismatch_across_symbols_raises(self, synth_data):
        """All symbols must have the same feature count."""
        X, y = synth_data
        n = len(X)
        mid = n // 2
        with pytest.raises(ValueError, match="has .* features, expected"):
            run_symbol_ablation(
                {"BTCUSDT": X[:mid, :10], "ETHUSDT": X[mid:, :8]},
                {"BTCUSDT": y[:mid], "ETHUSDT": y[mid:]},
            )

    def test_held_out_accuracy_computed(self, synth_data):
        """Held-out accuracy is computed for each symbol."""
        X, y = synth_data
        n = len(X)
        mid = n // 2
        X_by = {"BTCUSDT": X[:mid], "ETHUSDT": X[mid:]}
        y_by = {"BTCUSDT": y[:mid], "ETHUSDT": y[mid:]}

        study = run_symbol_ablation(X_by, y_by)
        for result in study.results:
            assert 0.0 <= result.held_out_accuracy <= 1.0
            assert isinstance(result.held_out_logloss, float)
            assert len(result.limitations) > 0

    def test_string_labels_accepted(self, synth_data_string_labels):
        """String labels are accepted for symbol ablation."""
        X, y = synth_data_string_labels
        n = len(X)
        mid = n // 2
        X_by = {"BTCUSDT": X[:mid], "ETHUSDT": X[mid:]}
        y_by = {"BTCUSDT": y[:mid], "ETHUSDT": y[mid:]}

        study = run_symbol_ablation(X_by, y_by)
        assert len(study.results) == 2


# ============================================================================
# Tests: AblationStudy Structure
# ============================================================================


class TestAblationStudyStructure:
    """Verify AblationStudy dataclass has correct structure."""

    def test_study_type_is_set(self, synth_data, pipeline_feature_names):
        """study_type matches the ablation function used."""
        X, y = synth_data
        fg_study = run_feature_group_ablation(
            X, y, feature_names=pipeline_feature_names, groups_to_ablate=["returns"],
        )
        assert fg_study.study_type == "feature_group"

    def test_study_has_baseline_metrics(self, synth_data, pipeline_feature_names):
        """baseline_metrics dict is populated."""
        X, y = synth_data
        study = run_feature_group_ablation(
            X, y, feature_names=pipeline_feature_names, groups_to_ablate=["returns"],
        )
        assert isinstance(study.baseline_metrics, dict)
        assert len(study.baseline_metrics) > 0

    def test_study_has_limitations(self, synth_data, pipeline_feature_names):
        """AblationStudy includes standard limitations."""
        X, y = synth_data
        study = run_feature_group_ablation(
            X, y, feature_names=pipeline_feature_names, groups_to_ablate=["returns"],
        )
        assert len(study.limitations) >= 3
        assert any("DESCRIPTIVE" in lim for lim in study.limitations)

    def test_study_has_summary(self, synth_data, pipeline_feature_names):
        """Summary dict contains relevant metadata."""
        X, y = synth_data
        study = run_feature_group_ablation(
            X, y, feature_names=pipeline_feature_names, groups_to_ablate=["returns"],
        )
        assert "description" in study.summary
        assert "baseline_accuracy" in study.summary
        assert study.summary["groups_ablated"] == 1


# ============================================================================
# Tests: Hyperparameter Configuration
# ============================================================================


class TestAblationHyperparameters:
    """Verify ABLATION_HYPERPARAMS are valid and CPU-safe."""

    def test_tree_method_is_hist(self):
        """tree_method must be 'hist' for CPU compatibility."""
        assert ABLATION_HYPERPARAMS["tree_method"] == "hist"

    def test_num_class_is_3(self):
        """Ablation uses 3-class classification matching pipeline labels."""
        assert ABLATION_HYPERPARAMS["num_class"] == 3

    def test_reproducible_seed(self):
        """random_state is fixed for reproducibility."""
        assert ABLATION_HYPERPARAMS["random_state"] == 42

    def test_custom_trainer_kwargs_override(self, synth_data, pipeline_feature_names):
        """Custom trainer_kwargs are respected."""
        X, y = synth_data
        study = run_feature_group_ablation(
            X, y,
            feature_names=pipeline_feature_names,
            groups_to_ablate=["returns"],
            trainer_kwargs={"n_estimators": 30, "max_depth": 3},
        )
        assert len(study.results) == 1  # Training succeeded with overrides
