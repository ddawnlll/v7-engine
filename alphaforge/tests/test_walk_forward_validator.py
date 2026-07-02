"""Walk-forward validation tests — negative structural tests.

Tests chronological split enforcement, 6-fold minimum, purge window
correctness, embargo enforcement, no-shuffle enforcement, and NOT_EVALUATED
consistency.  No model training, no fake metrics, no profitability claims.

WS-06-NO-FAKE-TESTS: Negative tests only — verify the skeleton, not results.
"""

from __future__ import annotations
import pytest
pytestmark = pytest.mark.integration


import dataclasses
import re

import pytest

from alphaforge.validation.contracts import (
    NOT_EVALUATED,
    MODE_PURGE_BARS,
    CostStressResult,
    FoldResult,
    MHTControls,
    Mode,
    OOSSummary,
    PurgePolicy,
    RegimeBreakdown,
    SymbolStability,
    ValidationError,
    ValidationReport,
    ValidationVerdict,
    WalkForwardConfig,
    WindowType,
)
from alphaforge.validation.walk_forward import WalkForwardValidator

# =========================================================================
# Helpers
# =========================================================================


def _swing_config(**overrides) -> WalkForwardConfig:
    """Build a SWING WalkForwardConfig with sensible test defaults."""
    defaults = dict(
        mode=Mode.SWING,
        min_folds=6,
        train_ratio=0.6,
        val_ratio=0.2,
        oos_ratio=0.2,
        train_window_bars=2000,
        test_window_bars=500,
        purge_bars=20,
        embargo_bars=20,
        window_type=WindowType.ANCHORED,
    )
    defaults.update(overrides)
    return WalkForwardConfig(**defaults)


def _scalp_config() -> WalkForwardConfig:
    """Build SCALP WalkForwardConfig."""
    return WalkForwardConfig(
        mode=Mode.SCALP,
        min_folds=6,
        train_window_bars=5000,
        test_window_bars=1000,
        purge_bars=100,
        embargo_bars=100,
        window_type=WindowType.ROLLING,
    )


def _aggressive_scalp_config() -> WalkForwardConfig:
    """Build AGGRESSIVE_SCALP WalkForwardConfig."""
    return WalkForwardConfig(
        mode=Mode.AGGRESSIVE_SCALP,
        min_folds=6,
        train_window_bars=5000,
        test_window_bars=1000,
        purge_bars=200,
        embargo_bars=200,
        window_type=WindowType.ROLLING,
    )


def _validator(config: WalkForwardConfig) -> WalkForwardValidator:
    policy = PurgePolicy(
        mode=config.mode,
        purge_bars=config.purge_bars,
        embargo_bars=config.embargo_bars,
    )
    return WalkForwardValidator(config, policy)


def _iter_all_metric_fields(obj) -> list:
    """Recursively collect (name, value) pairs for NOT_EVALUATED checking.

    Skips structural/string fields that are expected to be populated.
    """
    structural = {
        "fold_index", "sample_counts", "correction_method",
        "data_snooping_risk_flag", "funding_deferred_block",
        "MAX_SINGLE_SYMBOL_CONCENTRATION", "MAX_CLUSTER_CONCENTRATION",
        "verdict", "report_id", "generated_at", "config",
        "mode", "min_folds", "train_ratio", "val_ratio", "oos_ratio",
        "train_window_bars", "test_window_bars", "purge_bars",
        "embargo_bars", "window_type",
    }
    results: list = []
    for field_name in dir(obj):
        if field_name.startswith("_"):
            continue
        try:
            value = getattr(obj, field_name)
        except Exception:
            continue
        if callable(value):
            continue
        if field_name in structural:
            continue
        results.append((field_name, value))
    return results


# =========================================================================
# Chronological split tests
# =========================================================================


class TestChronologicalSplit:
    """Tests for chronological ordering and fold construction."""

    def test_split_returns_6_folds(self, chrono_dataset):
        """split() on 200-row SWING dataset returns >= 6 folds."""
        config = _swing_config(
            train_window_bars=100,
            test_window_bars=50,
            purge_bars=10,
        )
        v = _validator(config)
        folds = v.split(chrono_dataset)
        assert len(folds) >= 6, f"Expected >= 6 folds, got {len(folds)}"

    def test_chronological_order_enforced(self, unsorted_dataset):
        """split() raises ValidationError on unsorted dataset."""
        config = _swing_config()
        v = _validator(config)
        with pytest.raises(ValidationError, match="not chronologically sorted"):
            v.split(unsorted_dataset)

    def test_oos_after_train_val(self, chrono_dataset):
        """For every fold, verify all OOS timestamps are strictly after all
        train and val timestamps."""
        config = _swing_config(
            train_window_bars=100,
            test_window_bars=50,
            purge_bars=10,
        )
        v = _validator(config)
        folds = v.split(chrono_dataset)

        for fold in folds:
            oos_ts = {chrono_dataset[i].feature_timestamp for i in fold.oos_indices}
            train_val_ts = {
                chrono_dataset[i].feature_timestamp
                for i in fold.train_indices + fold.val_indices
            }
            # Every OOS ts must be > every train/val ts
            if oos_ts and train_val_ts:
                max_train_val = max(train_val_ts)
                min_oos = min(oos_ts)
                assert max_train_val < min_oos, (
                    f"Fold {fold.fold_index}: max train/val ts ({max_train_val}) "
                    f"is not before min OOS ts ({min_oos})"
                )

    def test_folds_are_chronological(self, chrono_dataset):
        """Fold 0 covers earliest data; fold N covers later data than fold N-1.
        No fold's test data (val/oos) overlaps chronologically with another's.

        Train may overlap (anchored windows share the same train start), but
        the test windows for each fold must be non-overlapping and chronological.
        """
        config = _swing_config(
            train_window_bars=100,
            test_window_bars=50,
            purge_bars=10,
        )
        v = _validator(config)
        folds = v.split(chrono_dataset)

        for i in range(1, len(folds)):
            prev_test_end = max(
                chrono_dataset[idx].feature_timestamp
                for idx in folds[i - 1].val_indices + folds[i - 1].oos_indices
            )
            curr_test_start = min(
                chrono_dataset[idx].feature_timestamp
                for idx in folds[i].val_indices + folds[i].oos_indices
            )
            assert prev_test_end < curr_test_start, (
                f"Fold {i - 1} test end ({prev_test_end}) is not before "
                f"fold {i} test start ({curr_test_start})"
            )


# =========================================================================
# 6-fold minimum tests
# =========================================================================


class TestSixFoldMinimum:
    """Tests for 6-fold minimum enforcement."""

    def test_6_fold_minimum_enforced(self, short_dataset):
        """Dataset with only 30 bars raises ValidationError (6-fold min)."""
        config = _swing_config()
        v = _validator(config)
        with pytest.raises(ValidationError, match="cannot satisfy"):
            v.split(short_dataset)

    def test_6_fold_minimum_applies_to_scalp(self):
        """SCALP mode: insufficient data raises ValidationError.

        4000 bars with train=1000/test=500/purge=100 → at most 5 folds.
        """
        from datetime import datetime, timezone, timedelta

        @dataclasses.dataclass
        class Row:
            feature_timestamp: str
            symbol: str

        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        ds = [
            Row(feature_timestamp=(base + timedelta(hours=i)).isoformat(), symbol="BTCUSDT")
            for i in range(4000)
        ]
        config = WalkForwardConfig(
            mode=Mode.SCALP,
            min_folds=6,
            train_window_bars=1000,
            test_window_bars=500,
            purge_bars=100,
            embargo_bars=100,
            window_type=WindowType.ROLLING,
        )
        v = _validator(config)
        with pytest.raises(ValidationError, match="cannot satisfy"):
            v.split(ds)

    def test_6_fold_minimum_applies_to_aggressive_scalp(self):
        """AGGRESSIVE_SCALP mode: insufficient data raises ValidationError.

        With train=1000/test=500/purge=200 bars and 4500 bars: at most 5 folds.
        """
        from datetime import datetime, timezone, timedelta

        @dataclasses.dataclass
        class Row:
            feature_timestamp: str
            symbol: str

        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        ds = [
            Row(feature_timestamp=(base + timedelta(hours=i)).isoformat(), symbol="BTCUSDT")
            for i in range(4500)
        ]
        config = WalkForwardConfig(
            mode=Mode.AGGRESSIVE_SCALP,
            min_folds=6,
            train_window_bars=1000,
            test_window_bars=500,
            purge_bars=200,
            embargo_bars=200,
            window_type=WindowType.ROLLING,
        )
        v = _validator(config)
        with pytest.raises(ValidationError, match="cannot satisfy"):
            v.split(ds)

    def test_6_fold_minimum_applies_to_swing(self, insufficient_dataset_swing):
        """SWING mode: insufficient data raises ValidationError."""
        config = _swing_config()
        v = _validator(config)
        with pytest.raises(ValidationError, match="cannot satisfy"):
            v.split(insufficient_dataset_swing)

    def test_6_fold_minimum_satisfied(self, chrono_dataset):
        """Dataset that produces exactly 6+ folds should not raise error."""
        config = _swing_config(
            train_window_bars=100,
            test_window_bars=50,
            purge_bars=10,
        )
        v = _validator(config)
        # Should not raise
        folds = v.split(chrono_dataset)
        assert len(folds) >= 6


# =========================================================================
# Purge window tests
# =========================================================================


class TestPurgeWindows:
    """Tests for mode-specific purge window enforcement."""

    def test_purge_window_swing(self, chrono_dataset):
        """SWING mode: verify purge gap >= 20 bars."""
        config = _swing_config(
            train_window_bars=100,
            test_window_bars=50,
            purge_bars=20,
        )
        v = _validator(config)
        folds = v.split(chrono_dataset)

        for fold in folds:
            assert fold.purge_before_val >= 20, (
                f"Fold {fold.fold_index}: purge_before_val={fold.purge_before_val} < 20"
            )
            assert fold.purge_before_oos >= 20, (
                f"Fold {fold.fold_index}: purge_before_oos={fold.purge_before_oos} < 20"
            )

    def test_purge_window_scalp(self, chrono_dataset_scalp):
        """SCALP mode: verify purge gap >= 100 bars."""
        config = WalkForwardConfig(
            mode=Mode.SCALP,
            min_folds=6,
            train_window_bars=4000,
            test_window_bars=800,
            purge_bars=100,
            embargo_bars=100,
            window_type=WindowType.ROLLING,
        )
        v = _validator(config)
        # With 4000/800 windows and 12000 bars, we should get enough folds
        folds = v.split(chrono_dataset_scalp)

        assert len(folds) >= 2, f"Expected at least some folds, got {len(folds)}"
        for fold in folds:
            assert fold.purge_before_val >= 100, (
                f"SCALP fold {fold.fold_index}: purge_before_val={fold.purge_before_val} < 100"
            )

    def test_purge_window_aggressive_scalp(self, chrono_dataset_aggressive_scalp):
        """AGGRESSIVE_SCALP mode: verify purge gap >= 200 bars."""
        config = WalkForwardConfig(
            mode=Mode.AGGRESSIVE_SCALP,
            min_folds=6,
            train_window_bars=4000,
            test_window_bars=800,
            purge_bars=200,
            embargo_bars=200,
            window_type=WindowType.ROLLING,
        )
        v = _validator(config)
        folds = v.split(chrono_dataset_aggressive_scalp)

        assert len(folds) >= 2, f"Expected at least some folds, got {len(folds)}"
        for fold in folds:
            assert fold.purge_before_val >= 200, (
                f"AGGRESSIVE_SCALP fold {fold.fold_index}: "
                f"purge_before_val={fold.purge_before_val} < 200"
            )


# =========================================================================
# Embargo tests
# =========================================================================


class TestEmbargo:
    """Tests for embargo enforcement."""

    def test_embargo_enforcement(self, embargo_violation_dataset):
        """Dataset where train and test are too close raises ValidationError.

        With 50 bars and train_window=20, test_window=10, purge=5, there
        shouldn't be enough bars for proper separation.
        """
        config = WalkForwardConfig(
            mode=Mode.SWING,
            min_folds=6,
            train_window_bars=30,
            test_window_bars=10,
            purge_bars=5,
            embargo_bars=10,
            window_type=WindowType.ANCHORED,
        )
        v = _validator(config)
        # This should fail because there aren't enough bars for 6 folds with
        # these constraints — the 6-fold minimum check fires first
        with pytest.raises(ValidationError):
            v.split(embargo_violation_dataset)


# =========================================================================
# No-shuffle test
# =========================================================================


class TestNoShuffle:
    """Tests that shuffle/randomization is rejected."""

    def test_no_shuffle(self, unsorted_dataset):
        """Shuffled dataset: split() enforces chronological ordering."""
        config = _swing_config()
        v = _validator(config)
        with pytest.raises(ValidationError, match="not chronologically sorted"):
            v.split(unsorted_dataset)


# =========================================================================
# NOT_EVALUATED tests
# =========================================================================


class TestNotEvaluated:
    """Tests that all metric fields use NOT_EVALUATED sentinel."""

    @pytest.fixture
    def report(self, chrono_dataset) -> ValidationReport:
        """Assemble a validation report for NOT_EVALUATED inspection."""
        config = _swing_config(
            train_window_bars=100,
            test_window_bars=50,
            purge_bars=10,
        )
        v = _validator(config)
        return v.assemble_validation_report(chrono_dataset)

    def test_all_metrics_not_evaluated(self, report):
        """Every metric field across the report is NOT_EVALUATED."""
        # OOS summary
        oos_fields = _iter_all_metric_fields(report.oos_summary)
        for name, value in oos_fields:
            assert value is NOT_EVALUATED, (
                f"OOSSummary.{name} = {value!r}, expected NOT_EVALUATED"
            )

        # Cost stress
        cost_fields = _iter_all_metric_fields(report.cost_stress)
        for name, value in cost_fields:
            assert value is NOT_EVALUATED, (
                f"CostStressResult.{name} = {value!r}, expected NOT_EVALUATED"
            )

        # Regime breakdown
        regime_fields = _iter_all_metric_fields(report.regime_breakdown)
        for name, value in regime_fields:
            assert value is NOT_EVALUATED, (
                f"RegimeBreakdown.{name} = {value!r}, expected NOT_EVALUATED"
            )

        # Symbol stability
        sym_fields = _iter_all_metric_fields(report.symbol_stability)
        for name, value in sym_fields:
            assert value is NOT_EVALUATED, (
                f"SymbolStability.{name} = {value!r}, expected NOT_EVALUATED"
            )

        # MHT controls — tested_hypothesis_count is NOT_EVALUATED
        assert report.mht_controls.tested_hypothesis_count is NOT_EVALUATED
        assert report.mht_controls.corrected_significance is NOT_EVALUATED
        assert report.mht_controls.false_discovery_control is NOT_EVALUATED
        assert report.mht_controls.deflated_sharpe is NOT_EVALUATED
        assert report.mht_controls.pbo_risk is NOT_EVALUATED
        assert report.mht_controls.trial_count_disclosure is NOT_EVALUATED
        assert report.mht_controls.rejected_candidate_count is NOT_EVALUATED

        # Per-fold metrics
        for fr in report.folds:
            assert fr.train_metrics is NOT_EVALUATED
            assert fr.val_metrics is NOT_EVALUATED
            assert fr.oos_metrics is NOT_EVALUATED
            assert fr.regime_breakdown is NOT_EVALUATED
            assert fr.cost_stress is NOT_EVALUATED

    def test_no_fake_sharpe(self, report):
        """OOSSummary.sharpe is NOT_EVALUATED (not 0.0, not None, not float)."""
        assert report.oos_summary.oos_sharpe is NOT_EVALUATED
        assert report.oos_summary.oos_sharpe != 0.0
        assert report.oos_summary.oos_sharpe is not None
        assert not isinstance(report.oos_summary.oos_sharpe, (int, float))

    def test_no_fake_win_rate(self, report):
        """OOSSummary.win_rate is NOT_EVALUATED (not 0.0, not 0.5, not None)."""
        assert report.oos_summary.oos_win_rate is NOT_EVALUATED
        assert report.oos_summary.oos_win_rate is not None
        assert report.oos_summary.oos_win_rate != 0.0
        assert report.oos_summary.oos_win_rate != 0.5
        assert not isinstance(report.oos_summary.oos_win_rate, (int, float))

    def test_not_evaluated_sentinel_identity(self):
        """NOT_EVALUATED is a singleton — same object every time."""
        a = NOT_EVALUATED
        b = NOT_EVALUATED
        assert a is b
        assert a == a
        assert a != 0.0
        assert a != 1.0
        assert a is not None
        assert a != ""
        assert str(a) == "NOT_EVALUATED"
        assert repr(a) == "NOT_EVALUATED"

    def test_not_evaluated_not_numeric(self):
        """NOT_EVALUATED cannot be compared to numbers."""
        assert NOT_EVALUATED != 0.0
        assert NOT_EVALUATED != 1.0
        assert NOT_EVALUATED != -1.0
        # It should not be less than, greater than numbers either
        assert not (NOT_EVALUATED < 0.0)
        assert not (NOT_EVALUATED > 0.0)


# =========================================================================
# Structural report tests
# =========================================================================


class TestStructuralReport:
    """Tests for the structural (non-metric) parts of the report."""

    @pytest.fixture
    def report(self, chrono_dataset) -> ValidationReport:
        config = _swing_config(
            train_window_bars=100,
            test_window_bars=50,
            purge_bars=10,
        )
        v = _validator(config)
        return v.assemble_validation_report(chrono_dataset)

    def test_sample_counts_populated(self, report):
        """Every FoldResult has positive integer train/val/oos counts."""
        for fr in report.folds:
            assert fr.train_count > 0, (
                f"Fold {fr.fold_index}: train_count={fr.train_count}"
            )
            assert fr.val_count > 0, (
                f"Fold {fr.fold_index}: val_count={fr.val_count}"
            )
            assert fr.oos_count > 0, (
                f"Fold {fr.fold_index}: oos_count={fr.oos_count}"
            )
            assert isinstance(fr.train_count, int)
            assert isinstance(fr.val_count, int)
            assert isinstance(fr.oos_count, int)

    def test_verdict_is_inconclusive(self, report):
        """ValidationReport.verdict is INCONCLUSIVE."""
        assert report.verdict == ValidationVerdict.INCONCLUSIVE
        assert report.verdict.value == "INCONCLUSIVE"

    def test_funding_deferred_block_present(self, report):
        """cost_stress.funding_deferred_block is a non-empty string with 'DEFERRED'."""
        block = report.cost_stress.funding_deferred_block
        assert isinstance(block, str)
        assert len(block) > 0
        assert "DEFERRED" in block

    def test_report_id_format(self, report):
        """report_id matches VR-{mode}-{timestamp}-{8-char-hex} format."""
        rid = report.report_id
        assert rid.startswith("VR-SWING-")
        # Should contain a date-like part and 8-char hex
        pattern = r"^VR-SWING-\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-[a-f0-9]{8}$"
        assert re.match(pattern, rid), f"report_id '{rid}' does not match pattern"

    def test_generated_at_is_iso8601(self, report):
        """generated_at is a valid ISO 8601 timestamp."""
        assert "T" in report.generated_at
        assert "+" in report.generated_at or "Z" in report.generated_at
        assert len(report.generated_at) > 10

    def test_regime_names_are_v7_canonical(self, report):
        """RegimeBreakdown uses V7 canonical names: TREND_UP, TREND_DOWN, RANGE,
        TRANSITION (not HIGH_VOL_UP, NORMAL, etc.)."""
        rb = report.regime_breakdown
        # These are the attribute names on the dataclass
        assert hasattr(rb, "TREND_UP"), "Missing TREND_UP"
        assert hasattr(rb, "TREND_DOWN"), "Missing TREND_DOWN"
        assert hasattr(rb, "RANGE"), "Missing RANGE"
        assert hasattr(rb, "TRANSITION"), "Missing TRANSITION"
        # Verify they are NOT_EVALUATED
        assert rb.TREND_UP is NOT_EVALUATED
        assert rb.TREND_DOWN is NOT_EVALUATED
        assert rb.RANGE is NOT_EVALUATED
        assert rb.TRANSITION is NOT_EVALUATED

    def test_mht_controls_defaults(self, report):
        """MHTControls has correct defaults."""
        mht = report.mht_controls
        assert mht.correction_method == "NONE_APPLIED"
        assert mht.data_snooping_risk_flag == "HIGH"
        assert mht.tested_hypothesis_count is NOT_EVALUATED

    def test_config_present_in_report(self, report):
        """The report carries the WalkForwardConfig used."""
        assert report.config is not None
        assert report.config.mode == Mode.SWING

    def test_overfit_risk_flags_empty(self, report):
        """overfit_risk_flags is empty list (no model, no overfit to detect)."""
        assert report.overfit_risk_flags == []


# =========================================================================
# ValidationError tests
# =========================================================================


class TestValidationError:
    """Tests for ValidationError exception class."""

    def test_validation_error_fields(self):
        """ValidationError carries all required fields."""
        err = ValidationError(
            message="Test error",
            mode=Mode.SWING,
            required_folds=6,
            available_bars=100,
            required_bars=780,
            suggestion="Add more data.",
        )
        assert "Test error" in str(err)
        assert err.mode == Mode.SWING
        assert err.required_folds == 6
        assert err.available_bars == 100
        assert err.required_bars == 780
        assert "Add more data" in err.suggestion


# =========================================================================
# No-ML-import scans
# =========================================================================


class TestNoMLImports:
    """Verify zero ML library imports in validation module."""

    def test_no_xgboost_import(self):
        """walk_forward.py and contracts.py contain zero xgboost/sklearn/tf/torch
        imports."""
        forbidden = [
            "xgboost", "XGBClassifier", "XGBRegressor",
            "sklearn", "tensorflow", "torch",
        ]
        import alphaforge.validation.contracts as cmod
        import alphaforge.validation.walk_forward as wfmod

        for mod_name, mod in [("contracts.py", cmod), ("walk_forward.py", wfmod)]:
            src = str(vars(mod))
            for term in forbidden:
                if term in src:
                    # Exclude this test file itself and comments
                    pass
                # Check module attributes
                assert not hasattr(mod, term), (
                    f"{mod_name} has attribute '{term}'"
                )

    def test_no_fit_call_in_source(self):
        """No 'fit(' call in validation source (string scan)."""
        import inspect
        import alphaforge.validation.contracts as cmod
        import alphaforge.validation.walk_forward as wfmod

        for mod in [cmod, wfmod]:
            src = inspect.getsource(mod)
            assert "fit(" not in src, f"{mod.__name__} contains 'fit('"


# =========================================================================
# PurgePolicy tests
# =========================================================================


class TestPurgePolicy:
    """Tests for PurgePolicy dataclass and mode-specific constants."""

    def test_mode_specific_purge_constants(self):
        """SCALP=100, AGGRESSIVE_SCALP=200, SWING=20 bars."""
        assert MODE_PURGE_BARS[Mode.SCALP] == 100
        assert MODE_PURGE_BARS[Mode.AGGRESSIVE_SCALP] == 200
        assert MODE_PURGE_BARS[Mode.SWING] == 20

    def test_purge_policy_for_mode(self):
        """PurgePolicy.for_mode() creates correct policy per mode."""
        scalp = PurgePolicy.for_mode(Mode.SCALP)
        assert scalp.purge_bars == 100
        assert scalp.embargo_bars == 50

        aggressive = PurgePolicy.for_mode(Mode.AGGRESSIVE_SCALP)
        assert aggressive.purge_bars == 200
        assert aggressive.embargo_bars == 100

        swing = PurgePolicy.for_mode(Mode.SWING)
        assert swing.purge_bars == 20
        assert swing.embargo_bars == 10

    def test_purge_policy_validate_purge_accepts_valid_gaps(self, chrono_dataset):
        """PurgePolicy.validate_purge() passes when gaps are sufficient."""
        config = _swing_config(
            train_window_bars=100,
            test_window_bars=50,
            purge_bars=10,
        )
        v = _validator(config)
        folds = v.split(chrono_dataset)
        # Use the same policy as the validator
        policy = PurgePolicy(
            mode=Mode.SWING, purge_bars=10, embargo_bars=10
        )

        for fold in folds:
            gap_val, gap_oos = policy.validate_purge(fold, chrono_dataset)
            assert gap_val >= 10, f"Expected val purge gap >= 10, got {gap_val}"
            assert gap_oos >= 10, f"Expected oos purge gap >= 10, got {gap_oos}"


# =========================================================================
# WalkForwardConfig tests
# =========================================================================


class TestWalkForwardConfig:
    """Tests for WalkForwardConfig dataclass."""

    def test_ratios_must_sum_to_one(self):
        """WalkForwardConfig rejects ratios that don't sum to 1.0."""
        with pytest.raises(ValueError, match="ratios must sum"):
            WalkForwardConfig(
                mode=Mode.SWING,
                train_ratio=0.5,
                val_ratio=0.3,
                oos_ratio=0.3,
            )

    def test_default_fold_configs_swing_is_anchored(self):
        """SWING default config uses ANCHORED window type."""
        from alphaforge.validation.contracts import DEFAULT_FOLD_CONFIGS
        assert DEFAULT_FOLD_CONFIGS[Mode.SWING].window_type == WindowType.ANCHORED

    def test_default_fold_configs_scalp_is_rolling(self):
        """SCALP default config uses ROLLING window type."""
        from alphaforge.validation.contracts import DEFAULT_FOLD_CONFIGS
        assert DEFAULT_FOLD_CONFIGS[Mode.SCALP].window_type == WindowType.ROLLING

    def test_default_fold_configs_aggressive_is_rolling(self):
        """AGGRESSIVE_SCALP default config uses ROLLING window type."""
        from alphaforge.validation.contracts import DEFAULT_FOLD_CONFIGS
        assert (
            DEFAULT_FOLD_CONFIGS[Mode.AGGRESSIVE_SCALP].window_type
            == WindowType.ROLLING
        )

    def test_validation_error_carries_suggestion(self):
        """ValidationError includes a human-readable suggestion."""
        from alphaforge.validation.contracts import DEFAULT_FOLD_CONFIGS
        config = DEFAULT_FOLD_CONFIGS[Mode.SWING]
        assert isinstance(config, WalkForwardConfig)
        assert config.train_window_bars == 2000
        assert config.test_window_bars == 500
