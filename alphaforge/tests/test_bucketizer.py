"""Tests for FeatureBucketizer — decile-based boolean mask generation.

Test categories:
1. fit/transform roundtrip — mask shape, count, and key correctness
2. Bucket thresholds — exact decile partitioning of linearly spaced data
3. NaN handling — NaN positions are False in every mask
4. Empty input — zero-row tables produce zero-length masks
5. Discovery thresholds used in transform — fit thresholds apply to new data
6. Condition registry — support_count accuracy and min_support filtering
7. Error cases — not-fitted, missing column
8. Domain detection — keyword matching against feature names
9. Edge cases — all-NaN columns, constant values, single row
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import pytest

from alphaforge.mine.bucketizer import (
    ConditionRecord,
    FeatureBucketizer,
    _detect_domain,
    _split_mask_ref,
)

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def linearly_spaced_10() -> pa.Table:
    """10 rows with values 0..9 — each row maps to exactly one decile."""
    return pa.table({"x": pa.array(np.arange(10.0, dtype=np.float64))})


@pytest.fixture
def three_features_100() -> pa.Table:
    """100 rows with three domain-tagged features."""
    rng = np.random.default_rng(42)
    n = 100
    return pa.table(
        {
            "volatility_4h": pa.array(rng.exponential(scale=0.02, size=n)),
            "momentum_4h": pa.array(rng.normal(loc=0.0, scale=0.01, size=n)),
            "rsi_4h": pa.array(rng.uniform(low=20.0, high=80.0, size=n)),
        }
    )


@pytest.fixture
def table_with_nan() -> pa.Table:
    """Small table with one NaN in the middle."""
    return pa.table(
        {"x": pa.array([1.0, 2.0, np.nan, 4.0, 5.0], type=pa.float64())}
    )


@pytest.fixture
def empty_table() -> pa.Table:
    """Zero-row float64 table."""
    return pa.table({"x": pa.array([], type=pa.float64())})


# ===================================================================
# Tests
# ===================================================================


class TestFeatureBucketizer:
    """FeatureBucketizer construction, fit, transform, and registry."""

    # ------------------------------------------------------------------
    # fit / transform roundtrip
    # ------------------------------------------------------------------

    def test_fit_transform_roundtrip(self, three_features_100: pa.Table) -> None:
        """fit -> transform produces correct mask shapes and keys."""
        b = FeatureBucketizer()
        cols = ["volatility_4h", "momentum_4h", "rsi_4h"]
        b.fit(three_features_100, cols)
        masks = b.transform(three_features_100)

        n = three_features_100.num_rows
        assert n == 100

        # Every feature has 10 decile masks (100 key-value pairs).
        for col in cols:
            for d in range(1, 11):
                key = f"{col}__d{d:02d}"
                assert key in masks, f"Missing decile mask: {key}"
                assert masks[key].shape == (n,), f"Wrong shape for {key}"
                assert masks[key].dtype == bool, f"Wrong dtype for {key}"

        # Volatility feature gets the volatility domain schema.
        for bucket in ["very_low", "low", "mid", "high", "very_high"]:
            key = f"volatility_4h__{bucket}"
            assert key in masks, f"Missing volatility mask: {key}"
            assert masks[key].shape == (n,)

        # Momentum feature gets the momentum domain schema.
        for bucket in [
            "strong_bear",
            "weak_bear",
            "neutral",
            "weak_bull",
            "strong_bull",
        ]:
            key = f"momentum_4h__{bucket}"
            assert key in masks, f"Missing momentum mask: {key}"
            assert masks[key].shape == (n,)

        # rsi_4h matches "rsi" keyword -> also gets momentum schema.
        for bucket in [
            "strong_bear",
            "weak_bear",
            "neutral",
            "weak_bull",
            "strong_bull",
        ]:
            key = f"rsi_4h__{bucket}"
            assert key in masks, f"Missing RSI momentum mask: {key}"
            assert masks[key].shape == (n,)

    # ------------------------------------------------------------------
    # Bucket thresholds correct
    # ------------------------------------------------------------------

    def test_decile_partition_exact(self, linearly_spaced_10: pa.Table) -> None:
        """10 linearly spaced values → each falls into exactly one decile."""
        b = FeatureBucketizer()
        b.fit(linearly_spaced_10, ["x"])
        masks = b.transform(linearly_spaced_10)

        # With values 0..9 and 10 rows, each decile should contain exactly 1 row.
        for i in range(10):
            key = f"x__d{i + 1:02d}"
            assert masks[key][i], f"Row {i} should be in {key}"

            # Other decile masks should be False for this row.
            for j in range(10):
                if j != i:
                    assert not masks[f"x__d{j + 1:02d}"][i], (
                        f"Row {i} should NOT be in d{j + 1:02d}"
                    )

    def test_decile_masks_sum_to_n(self, linearly_spaced_10: pa.Table) -> None:
        """All 10 decile masks for a feature sum to total sample count."""
        b = FeatureBucketizer()
        b.fit(linearly_spaced_10, ["x"])
        masks = b.transform(linearly_spaced_10)

        total = sum(masks[f"x__d{i + 1:02d}"].sum() for i in range(10))
        assert total == linearly_spaced_10.num_rows

    # ------------------------------------------------------------------
    # NaN handling
    # ------------------------------------------------------------------

    def test_nan_false_in_all_masks(self, table_with_nan: pa.Table) -> None:
        """NaN positions are False in every mask."""
        b = FeatureBucketizer()
        b.fit(table_with_nan, ["x"])
        masks = b.transform(table_with_nan)

        for ref, mask in masks.items():
            assert not mask[2], f"NaN row should be False in {ref}"

    def test_nan_counts_in_registry(self, table_with_nan: pa.Table) -> None:
        """NaN rows do not inflate support counts in the registry."""
        b = FeatureBucketizer(min_support=0.0)
        b.fit(table_with_nan, ["x"])
        masks = b.transform(table_with_nan)
        registry = b.get_condition_registry()

        total_support = sum(
            r["support_count"] for r in registry if r["feature"] == "x"
        )
        # 5 samples, 1 NaN (excluded) -> 4 valid across all 10 deciles
        assert total_support == 4

    # ------------------------------------------------------------------
    # Empty input
    # ------------------------------------------------------------------

    def test_empty_table(self, empty_table: pa.Table) -> None:
        """Zero-row table produces zero-length masks."""
        b = FeatureBucketizer()
        b.fit(empty_table, ["x"])
        masks = b.transform(empty_table)

        assert len(masks) == 10  # 10 decile masks (no domain matched)
        for ref, mask in masks.items():
            assert mask.shape == (0,), f"{ref} shape should be (0,)"
            assert mask.dtype == bool

    def test_empty_registry_after_empty_transform(
        self, empty_table: pa.Table
    ) -> None:
        """Empty table produces zero support counts, filtered by min_support."""
        b = FeatureBucketizer(min_support=0.01)
        b.fit(empty_table, ["x"])
        b.transform(empty_table)
        registry = b.get_condition_registry()
        assert len(registry) == 0

    # ------------------------------------------------------------------
    # Discovery thresholds used in transform
    # ------------------------------------------------------------------

    def test_discovery_thresholds_applied_to_new_data(self) -> None:
        """Thresholds from fit() on discovery set determine transform buckets."""
        # Fit on [0, 1, 2, ..., 99]
        fit_table = pa.table({"x": np.arange(100.0)})
        b = FeatureBucketizer()
        b.fit(fit_table, ["x"])

        # Transform on a different set
        transform_table = pa.table({"x": np.array([-5.0, 0.0, 49.0, 95.0, 150.0])})
        masks = b.transform(transform_table)

        # Value -5.0 is way below 10th percentile -> should be in d01
        assert masks["x__d01"][0], "-5.0 should be in d01"
        # Value 0.0 -> d01
        assert masks["x__d01"][1], "0.0 should be in d01"
        # Value 49.0 -> roughly d05 (40th-50th percentile)
        assert masks["x__d05"][2], "49.0 should be in d05"
        # Value 95.0 -> d10
        assert masks["x__d10"][3], "95.0 should be in d10"
        # Value 150.0 -> d10 (above 90th)
        assert masks["x__d10"][4], "150.0 should be in d10"

    # ------------------------------------------------------------------
    # Condition registry
    # ------------------------------------------------------------------

    def test_condition_registry_keys_match_masks(
        self, linearly_spaced_10: pa.Table
    ) -> None:
        """All mask keys appear in the registry and vice versa."""
        b = FeatureBucketizer(min_support=0.0)
        b.fit(linearly_spaced_10, ["x"])
        masks = b.transform(linearly_spaced_10)
        registry = b.get_condition_registry()

        mask_keys = set(masks.keys())
        reg_keys = {r["mask_ref"] for r in registry}
        assert mask_keys == reg_keys, (
            f"Registry missing: {mask_keys - reg_keys}. "
            f"Extra in registry: {reg_keys - mask_keys}"
        )

    def test_condition_registry_support_counts(
        self, linearly_spaced_10: pa.Table
    ) -> None:
        """Support counts in registry match actual mask sums."""
        b = FeatureBucketizer(min_support=0.0)
        b.fit(linearly_spaced_10, ["x"])
        masks = b.transform(linearly_spaced_10)
        registry = b.get_condition_registry()

        for rec in registry:
            expected = int(masks[rec["mask_ref"]].sum())
            assert rec["support_count"] == expected, (
                f"Support mismatch for {rec['mask_ref']}: "
                f"{rec['support_count']} vs {expected}"
            )

    def test_min_support_filters_registry_entry(self) -> None:
        """Conditions below min_support fraction are excluded."""
        n = 100
        table = pa.table({"x": np.arange(float(n))})
        b = FeatureBucketizer(min_support=0.15)  # 15 samples minimum
        b.fit(table, ["x"])
        b.transform(table)
        registry = b.get_condition_registry()

        # Each decile has exactly 10 support -> 10/100 = 0.1 < 0.15,
        # so all decile masks should be excluded.
        d_records = [r for r in registry if r["feature"] == "x"]
        assert len(d_records) == 0, (
            f"Expected no conditions with min_support=0.15 on 100 samples, "
            f"got {len(d_records)}"
        )

    # ------------------------------------------------------------------
    # Error cases
    # ------------------------------------------------------------------

    def test_transform_before_fit_raises(self) -> None:
        """transform() before fit() raises RuntimeError."""
        b = FeatureBucketizer()
        with pytest.raises(RuntimeError, match="Must call fit"):
            b.transform(pa.table({"x": [1.0]}))

    def test_fit_missing_column_raises(self) -> None:
        """fit() with non-existent column raises ValueError."""
        table = pa.table({"x": [1.0]})
        b = FeatureBucketizer()
        with pytest.raises(ValueError, match="not found"):
            b.fit(table, ["y"])

    def test_transform_missing_column_raises(
        self, linearly_spaced_10: pa.Table
    ) -> None:
        """transform() with table missing a column from fit() raises ValueError."""
        b = FeatureBucketizer()
        b.fit(linearly_spaced_10, ["x"])
        other = pa.table({"y": [1.0, 2.0]})
        with pytest.raises(ValueError, match="not found"):
            b.transform(other)

    # ------------------------------------------------------------------
    # Domain detection
    # ------------------------------------------------------------------

    def test_domain_detection_matches(self) -> None:
        """Feature names correctly matched to domain keys."""
        cases = [
            ("volatility_4h", "volatility"),
            ("atr_pct_4h", "volatility"),
            ("volatility_bb_width", "volatility"),
            ("momentum_4h", "momentum"),
            ("log_return_4h", "momentum"),
            ("rsi_4h", "momentum"),
            ("roc_1h", "momentum"),
            ("relative_strength", "momentum"),
            ("regime_encoded", "regime"),
        ]
        for name, expected in cases:
            assert _detect_domain(name) == expected, f"Mismatch for '{name}'"

    def test_domain_detection_no_match(self) -> None:
        """Non-matching feature names return None."""
        cases = [
            "price_close",
            "volume_ratio_4h",
            "feature_xyz",
            "some_random_name",
            "",
            "123_numeric",
        ]
        for name in cases:
            assert _detect_domain(name) is None, f"Should be None for '{name}'"

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_all_nan_column(self) -> None:
        """All-NaN column produces all-False masks and zero support."""
        table = pa.table(
            {"x": pa.array([np.nan, np.nan, np.nan], type=pa.float64())}
        )
        b = FeatureBucketizer(min_support=0.0)
        b.fit(table, ["x"])
        masks = b.transform(table)

        n = table.num_rows
        for key, mask in masks.items():
            assert mask.shape == (n,)
            assert not mask.any(), f"All-NaN column should have no True values in {key}"

    def test_constant_column(self) -> None:
        """Constant column — all values equal, all fall into same decile(s)."""
        table = pa.table({"x": pa.array([5.0, 5.0, 5.0, 5.0, 5.0])})
        b = FeatureBucketizer(min_support=0.0)
        b.fit(table, ["x"])
        masks = b.transform(table)

        # With all identical values, percentile thresholds may be equal.
        # Every value should end up in at least one decile mask.
        in_any = np.zeros(table.num_rows, dtype=bool)
        for i in range(1, 11):
            in_any |= masks[f"x__d{i:02d}"]
        assert in_any.all(), "Every sample should be in at least one decile"

    def test_single_row(self) -> None:
        """Single-row table: all samples in d01 (the only decile with data)."""
        table = pa.table({"x": pa.array([42.0])})
        b = FeatureBucketizer(min_support=0.0)
        b.fit(table, ["x"])
        masks = b.transform(table)

        assert masks["x__d01"][0]
        # Other deciles should be False for the single row
        for i in range(2, 11):
            assert not masks[f"x__d{i:02d}"][0]

    # ------------------------------------------------------------------
    # _split_mask_ref helper
    # ------------------------------------------------------------------

    def test_split_mask_ref(self) -> None:
        """_split_mask_ref correctly splits <feature>__<bucket>."""
        assert _split_mask_ref("x__d01") == ("x", "d01")
        assert _split_mask_ref("volatility_4h__very_low") == (
            "volatility_4h",
            "very_low",
        )
        # Feature names with internal underscores
        assert _split_mask_ref("log_return_4h__d05") == ("log_return_4h", "d05")

    # ------------------------------------------------------------------
    # ConditionRecord dataclass
    # ------------------------------------------------------------------

    def test_condition_record_dataclass(self) -> None:
        """ConditionRecord is a frozen dataclass with expected fields."""
        rec = ConditionRecord(
            feature="volatility_4h",
            bucket="mid",
            mask_ref="volatility_4h__mid",
            support_count=42,
        )
        assert rec.feature == "volatility_4h"
        assert rec.bucket == "mid"
        assert rec.mask_ref == "volatility_4h__mid"
        assert rec.support_count == 42
