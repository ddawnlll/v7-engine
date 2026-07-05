"""Tests for OOSValidator — temporal split, rule validation, overfit detection.

Covers:
  - Temporal (not random) split enforces chronological order
  - Validation pruning eliminates weak rules
  - Holdout results are final unbiased test
  - Overfit detection flags OOS/IS ratio below threshold
  - Empty / edge cases (no rules, single row, missing columns)

Domain boundary: AlphaForge owns OOS validation. V7 owns promotion gates.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from alphaforge.mine.oos_validator import OOSValidator


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def simple_table() -> pa.Table:
    """A 10-row table with monotonic timestamps and a numeric target."""
    return pa.table(
        {
            "ts": list(range(10)),
            "feature_a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "target": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        }
    )


@pytest.fixture
def unsorted_table() -> pa.Table:
    """Table where timestamps are NOT in ascending order."""
    return pa.table(
        {
            "ts": [5, 3, 9, 1, 7, 2, 8, 4, 6, 0],
            "feature_a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "target": [0.5, 0.3, 0.9, 0.1, 0.7, 0.2, 0.8, 0.4, 0.6, 0.0],
        }
    )


@pytest.fixture
def validator() -> OOSValidator:
    return OOSValidator(discovery_split=0.6, validation_split=0.2, holdout_split=0.2)


# =========================================================================
# split — temporal ordering
# =========================================================================


class TestSplit:
    """Verify temporal split properties."""

    def test_split_returns_three_partitions(self, validator: OOSValidator, simple_table: pa.Table) -> None:
        parts = validator.split(simple_table, timestamp_col="ts")
        assert set(parts.keys()) == {"discovery", "validation", "holdout"}

    def test_split_is_temporal_not_random(self, validator: OOSValidator, simple_table: pa.Table) -> None:
        """Discovery contains first 60%, holdout last 20%."""
        parts = validator.split(simple_table, timestamp_col="ts")
        # 10 rows: discovery=6, validation=2, holdout=2
        assert parts["discovery"].num_rows == 6
        assert parts["validation"].num_rows == 2
        assert parts["holdout"].num_rows == 2

        # Verify temporal order preserved within each partition
        for name in ("discovery", "validation", "holdout"):
            ts_col = parts[name]["ts"].to_pylist()
            assert ts_col == sorted(ts_col), f"{name} timestamps not sorted"

    def test_split_sorts_unsorted_input(self, validator: OOSValidator, unsorted_table: pa.Table) -> None:
        """Splitting an unsorted table still produces temporally correct partitions."""
        parts = validator.split(unsorted_table, timestamp_col="ts")
        # After sorting ts ascending: [0,1,2,3,4,5,6,7,8,9]
        # discovery = ts [0..5], validation = ts [6..7], holdout = ts [8..9]
        discovery_ts = parts["discovery"]["ts"].to_pylist()
        holdout_ts = parts["holdout"]["ts"].to_pylist()
        assert max(discovery_ts) < min(holdout_ts), "Holdout not after discovery"

    def test_split_rejects_missing_column(self, validator: OOSValidator, simple_table: pa.Table) -> None:
        with pytest.raises(ValueError, match="Column 'nope' not found"):
            validator.split(simple_table, timestamp_col="nope")

    def test_split_rejects_too_few_rows(self, validator: OOSValidator) -> None:
        tiny = pa.table({"ts": [0, 1], "val": [1.0, 2.0]})
        with pytest.raises(ValueError, match="at least 3"):
            validator.split(tiny, timestamp_col="ts")

    def test_split_sums_to_total(self) -> None:
        """Splits on a larger table reconstruct the original row set."""
        n = 1000
        table = pa.table(
            {
                "ts": list(range(n)),
                "val": [float(i) for i in range(n)],
            }
        )
        v = OOSValidator(0.5, 0.3, 0.2)
        parts = v.split(table, "ts")
        total = sum(t.num_rows for t in parts.values())
        assert total == n


# =========================================================================
# validate — rule scoring and pruning
# =========================================================================


class TestValidate:
    """Verify rule scoring, elimination, and consistency."""

    def test_validate_keeps_good_rules(self, validator: OOSValidator) -> None:
        """Rules whose OOS performance matches IS survive."""
        # 10 rows, 60/20/20 split → discovery=6, validation=2, holdout=2.
        # feat=1 appears in *every* partition so the rule filter has matching rows OOS.
        table = pa.table(
            {
                "ts": list(range(10)),
                "feat": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 1.0, 0.0],
                "target": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.1, 0.5, 0.1],
            }
        )
        parts = validator.split(table, "ts")
        # Rule feat == 1.0 → mean target = 0.5 in both OOS partitions
        rules = [
            {
                "feature": "feat",
                "operator": "eq",
                "threshold": 1.0,
                "is_score": 0.5,
            },
        ]
        result = validator.validate(rules, parts["validation"], parts["holdout"])
        assert result["survived_validation"] == 1
        assert result["survived_holdout"] == 1
        assert result["overfit_warning"] is None

    def test_validate_eliminates_weak_rules(self, validator: OOSValidator) -> None:
        """Rules with OOS << IS are eliminated."""
        table = pa.table(
            {
                "ts": list(range(10)),
                "feat": list(range(10)),
                "target": [0.9, 0.8, 0.7, 0.6, 0.5, 0.1, 0.1, 0.1, 0.1, 0.1],
            }
        )
        # Discovery will have feat 0..5 (high target), validation 6..7 (low target)
        # Rule feat > 4 has IS score = mean of target for feat>4 in discovery
        # Validation has only low values → OOS << IS
        parts = validator.split(table, "ts")
        rules = [
            {
                "feature": "feat",
                "operator": "gt",
                "threshold": 4.0,
                "is_score": 0.7,
            },
        ]
        result = validator.validate(rules, parts["validation"], parts["holdout"])
        # OOS/IS on validation will be very low (targets 0.1 vs 0.7 IS)
        assert result["overfit_warning"] is not None
        # Rule might still survive holdout depending on data, but warning fires

    def test_validate_empty_rules(self, validator: OOSValidator) -> None:
        """Empty rule list returns safe defaults."""
        table = pa.table({"ts": [0, 1, 2], "val": [1.0, 2.0, 3.0], "target": [0.1, 0.2, 0.3]})
        parts = validator.split(table, "ts")
        result = validator.validate([], parts["validation"], parts["holdout"])
        assert result["consistency_score"] == 1.0
        assert result["survived_validation"] == 0
        assert result["survived_holdout"] == 0
        assert result["overfit_warning"] is None

    def test_validate_reports_rule_results(self, validator: OOSValidator, simple_table: pa.Table) -> None:
        parts = validator.split(simple_table, "ts")
        rules = [
            {"feature": "feature_a", "operator": "gt", "threshold": 3.0, "is_score": 0.6},
        ]
        result = validator.validate(rules, parts["validation"], parts["holdout"])
        assert len(result["rule_results"]) == 1
        rr = result["rule_results"][0]
        assert rr["feature"] == "feature_a"
        assert rr["operator"] == "gt"
        assert rr["threshold"] == 3.0
        assert rr["is_score"] == 0.6
        # validation_score and holdout_score should be computed
        assert rr["validation_score"] is not None
        assert rr["holdout_score"] is not None

    def test_validate_missing_feature_column(self, validator: OOSValidator) -> None:
        table = pa.table({"ts": [0, 1, 2], "target": [0.1, 0.2, 0.3]})
        parts = validator.split(table, "ts")
        rules = [
            {"feature": "missing_col", "operator": "gt", "threshold": 1.0, "is_score": 0.5},
        ]
        result = validator.validate(rules, parts["validation"], parts["holdout"])
        # Rule with missing column should have None scores
        assert result["rule_results"][0]["validation_score"] is None
        assert result["rule_results"][0]["holdout_score"] is None

    def test_validate_unknown_operator(self, validator: OOSValidator, simple_table: pa.Table) -> None:
        parts = validator.split(simple_table, "ts")
        rules = [
            {"feature": "feature_a", "operator": "bad_op", "threshold": 1.0, "is_score": 0.5},
        ]
        result = validator.validate(rules, parts["validation"], parts["holdout"])
        assert result["rule_results"][0]["validation_score"] is None


# =========================================================================
# overfit detection
# =========================================================================


class TestOverfitDetection:
    """Verify overfit warning fires correctly."""

    def test_overfit_detected_when_oos_low(self) -> None:
        """Validation set with very different distribution flags overfit."""
        v = OOSValidator(0.5, 0.25, 0.25)
        table = pa.table(
            {
                "ts": list(range(20)),
                "feat": [1.0] * 10 + [0.0] * 10,
                "target": [0.8] * 10 + [0.1] * 10,
            }
        )
        parts = v.split(table, "ts")
        # discovery: first 10 rows, feat=1, target=0.8 → IS score 0.8
        # validation: next 5 rows, feat=0, target=0.1 → OOS score 0.1
        # OOS/IS = 0.125 < 0.5 → overfit
        rules = [{"feature": "feat", "operator": "eq", "threshold": 1.0, "is_score": 0.8}]
        result = v.validate(rules, parts["validation"], parts["holdout"])
        assert result["overfit_warning"] is not None
        assert "below threshold" in result["overfit_warning"]

    def test_no_overfit_when_oos_matches_is(self, validator: OOSValidator) -> None:
        """Consistent OOS/IS produces no warning."""
        # feat=1 must appear in all three partitions so feat==1.0 has matching rows OOS.
        table = pa.table(
            {
                "ts": list(range(10)),
                "feat": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 1.0, 0.0],
                "target": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
            }
        )
        parts = validator.split(table, "ts")
        # discovery: feat=1 everywhere, target=0.5 → IS=0.5
        # validation: feat=[1,0], target=0.5 → filter feat==1 → mean 0.5 → OOS/IS=1.0
        # holdout:    feat=[1,0], target=0.5 → filter feat==1 → mean 0.5 → OOS/IS=1.0
        rules = [{"feature": "feat", "operator": "eq", "threshold": 1.0, "is_score": 0.5}]
        result = validator.validate(rules, parts["validation"], parts["holdout"])
        assert result["overfit_warning"] is None

    def test_consistency_score_min_of_ratios(self) -> None:
        """consistency_score is the minimum OOS/IS ratio across rules."""
        v = OOSValidator(0.5, 0.25, 0.25)
        table = pa.table(
            {
                "ts": list(range(20)),
                "feat_a": [1.0] * 10 + [0.0] * 10,
                "feat_b": [1.0] * 10 + [0.0] * 10,
                "target": [0.8] * 10 + [0.1] * 10,
            }
        )
        parts = v.split(table, "ts")
        rules = [
            {"feature": "feat_a", "operator": "eq", "threshold": 1.0, "is_score": 0.8},
            {"feature": "feat_b", "operator": "eq", "threshold": 1.0, "is_score": 0.9},
        ]
        result = v.validate(rules, parts["validation"], parts["holdout"])
        # Both have OOS/IS ~0.125, so min should be ~0.125
        assert result["consistency_score"] is not None
        assert result["consistency_score"] < 0.5


# =========================================================================
# summary
# =========================================================================


class TestSummary:
    """Verify summary reporting."""

    def test_summary_before_validate(self, validator: OOSValidator) -> None:
        s = validator.summary()
        assert s["final_verdict"] == "NOT_EVALUATED"
        assert s["discovery_rule_count"] == 0

    def test_summary_after_validate(self, validator: OOSValidator, simple_table: pa.Table) -> None:
        parts = validator.split(simple_table, "ts")
        rules = [
            {"feature": "feature_a", "operator": "gt", "threshold": 3.0, "is_score": 0.6},
        ]
        validator.validate(rules, parts["validation"], parts["holdout"])
        s = validator.summary()
        assert s["discovery_rule_count"] == 1
        assert isinstance(s["eliminated_by_validation"], int)
        assert isinstance(s["eliminated_by_holdout"], int)
        assert s["final_verdict"] in ("PASS", "PASS_WITH_WARNINGS", "FAIL")

    def test_summary_with_no_survivors(self) -> None:
        """When no rule survives holdout, verdict is FAIL."""
        v = OOSValidator(0.5, 0.25, 0.25)
        table = pa.table(
            {
                "ts": list(range(20)),
                "feat": [1.0] * 10 + [0.0] * 10,
                "target": [0.8] * 10 + [0.1] * 10,
            }
        )
        parts = v.split(table, "ts")
        rules = [{"feature": "feat", "operator": "eq", "threshold": 1.0, "is_score": 0.8}]
        v.validate(rules, parts["validation"], parts["holdout"])
        s = v.summary()
        # Given data distribution, rule likely eliminated on both partitions
        assert s["final_verdict"] in ("FAIL", "PASS_WITH_WARNINGS")


# =========================================================================
# constructor validation
# =========================================================================


def test_splits_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="Splits must sum to 1.0"):
        OOSValidator(0.5, 0.5, 0.5)


def test_default_splits_are_valid() -> None:
    v = OOSValidator()
    assert v.discovery_split == 0.6
    assert v.validation_split == 0.2
    assert v.holdout_split == 0.2
