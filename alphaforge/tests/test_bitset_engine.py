"""Tests for BitsetEngine — multi-level exhaustive condition mining.

Test categories:
1. Level 1 — atomic conditions: metrics, sorting, filtering
2. Level 2 — pairwise AND combinations: correctness, IC, top_n
3. Level 3 — beam search: triple combinations, improvement check
4. min_support filtering at every level
5. Empty input handling (empty masks, empty target)
6. Error cases — shape/dtype validation, out-of-range min_support
"""

from __future__ import annotations

import numpy as np
import pytest

from alphaforge.mine.bitset_engine import (
    BitsetEngine,
    _extract_valid,
    _min_count,
    _safe_mean,
    _validate_input,
)

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def simple_masks() -> dict:
    """5 samples, 3 known masks with predictable returns."""
    return {
        "up": np.array([True, True, False, False, False]),
        "down": np.array([False, False, True, True, False]),
        "mixed": np.array([True, False, True, False, False]),
    }


@pytest.fixture
def simple_target() -> np.ndarray:
    """Target: 2 positive, 2 negative, 1 zero."""
    return np.array([1.0, 1.0, -1.0, -1.0, 0.0], dtype=np.float64)


@pytest.fixture
def target_with_nan() -> np.ndarray:
    """Target with one NaN value."""
    return np.array([1.0, np.nan, -1.0, -1.0, 0.0], dtype=np.float64)


@pytest.fixture
def many_masks() -> dict:
    """10 masks over 100 samples for pair/beam tests."""
    rng = np.random.default_rng(42)
    n = 100
    masks = {}
    for i in range(10):
        masks[f"m{i}"] = rng.random(n) > 0.5
    return masks


@pytest.fixture
def many_target() -> np.ndarray:
    """100-sample target with known signal in early samples."""
    rng = np.random.default_rng(42)
    t = rng.normal(0.0, 1.0, 100).astype(np.float64)
    # Inject signal into first 10 samples
    t[:10] += 0.5
    return t


# ===================================================================
# Tests
# ===================================================================


class TestBitsetEngine:
    """BitsetEngine construction, all three scan levels, edge cases."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def test_default_min_support(self) -> None:
        """Default min_support is 0.01."""
        engine = BitsetEngine()
        assert engine.min_support == 0.01

    def test_custom_min_support(self) -> None:
        """Custom min_support is stored correctly."""
        engine = BitsetEngine(min_support=0.05)
        assert engine.min_support == 0.05

    def test_invalid_min_support_raises(self) -> None:
        """Out-of-range min_support raises ValueError."""
        with pytest.raises(ValueError, match="min_support"):
            BitsetEngine(min_support=-0.1)
        with pytest.raises(ValueError, match="min_support"):
            BitsetEngine(min_support=1.5)

    # ------------------------------------------------------------------
    # Level 1 — known results
    # ------------------------------------------------------------------

    def test_level1_known_metrics(
        self, simple_masks: dict, simple_target: np.ndarray
    ) -> None:
        """Level 1 returns correct metrics for known mask/target pairs."""
        engine = BitsetEngine(min_support=0.0)
        results = engine.level1_scan(simple_masks, simple_target)

        # Should have 3 results (no min_support filter)
        assert len(results) == 3

        # "up" mask: support=2, mean_net_R=1.0, win_rate=1.0, lift=1.0/0.0
        up = [r for r in results if r["conditions"] == ["up"]][0]
        assert up["support"] == 2
        assert up["mean_net_R"] == pytest.approx(1.0)
        assert up["win_rate"] == pytest.approx(1.0)

        # "down" mask: support=2, mean_net_R=-1.0, win_rate=0.0
        down = [r for r in results if r["conditions"] == ["down"]][0]
        assert down["support"] == 2
        assert down["mean_net_R"] == pytest.approx(-1.0)
        assert down["win_rate"] == pytest.approx(0.0)

        # "mixed" mask: support=2, mean_net_R=(1.0 + -1.0)/2 = 0.0
        mixed = [r for r in results if r["conditions"] == ["mixed"]][0]
        assert mixed["support"] == 2
        assert mixed["mean_net_R"] == pytest.approx(0.0)
        assert mixed["win_rate"] == pytest.approx(0.5)

    def test_level1_sorted_by_mean_net_r(
        self, simple_masks: dict, simple_target: np.ndarray
    ) -> None:
        """Level 1 results sorted descending by mean_net_R."""
        engine = BitsetEngine(min_support=0.0)
        results = engine.level1_scan(simple_masks, simple_target)

        mean_rs = [r["mean_net_R"] for r in results]
        assert mean_rs == sorted(mean_rs, reverse=True)

        # "up" (1.0) should be first, "mixed" (0.0) second, "down" (-1.0) last
        assert results[0]["conditions"] == ["up"]
        assert results[-1]["conditions"] == ["down"]

    def test_level1_lift_calculation(
        self, simple_masks: dict, simple_target: np.ndarray
    ) -> None:
        """Lift = mean_net_R / target.mean()."""
        engine = BitsetEngine(min_support=0.0)
        results = engine.level1_scan(simple_masks, simple_target)

        target_mean = np.mean(simple_target)  # (1+1-1-1+0)/5 = 0.0
        # target_mean is 0, so lift should be 0 for all
        for r in results:
            assert r["lift"] == pytest.approx(0.0)

    # ------------------------------------------------------------------
    # Level 1 — NaN handling
    # ------------------------------------------------------------------

    def test_level1_nan_in_target(
        self, simple_masks: dict, target_with_nan: np.ndarray
    ) -> None:
        """NaN values in target are excluded from mean and win_rate."""
        engine = BitsetEngine(min_support=0.0)
        results = engine.level1_scan(simple_masks, target_with_nan)

        # "up" mask: samples 0 (1.0) and 1 (NaN) -> only sample 0 is valid
        up = [r for r in results if r["conditions"] == ["up"]][0]
        assert up["support"] == 2
        # Only one valid value (1.0) in mask
        assert up["mean_net_R"] == pytest.approx(1.0)

    # ------------------------------------------------------------------
    # Level 2 — pairwise combinations
    # ------------------------------------------------------------------

    def test_level2_pair_count(
        self, simple_masks: dict, simple_target: np.ndarray
    ) -> None:
        """Level 2 with 3 masks produces only pairs with non-zero overlap."""
        engine = BitsetEngine(min_support=0.0)
        results = engine.level2_scan(simple_masks, simple_target, top_n=5000)

        # (up,down) has zero overlap (mask positions [0,1] vs [2,3])
        # so only 2 pairs survive: (up,mixed) and (down,mixed)
        assert len(results) == 2

    def test_level2_known_pair_metrics(
        self, simple_masks: dict, simple_target: np.ndarray
    ) -> None:
        """Verify metrics for a specific pair."""
        engine = BitsetEngine(min_support=0.0)
        results = engine.level2_scan(simple_masks, simple_target, top_n=5000)

        # up AND down: no overlap (indices 0,1 vs 2,3) -> support=0
        ud = [r for r in results if set(r["conditions"]) == {"up", "down"}]
        assert len(ud) == 0 or ud[0]["support"] == 0

        # up AND mixed: overlap at index 0 only
        # up = [T,T,F,F,F], mixed = [T,F,T,F,F] -> AND = [T,F,F,F,F]
        um = [r for r in results if set(r["conditions"]) == {"up", "mixed"}]
        assert len(um) == 1
        assert um[0]["support"] == 1
        # Only sample 0 is in both, target[0] = 1.0
        assert um[0]["mean_net_R"] == pytest.approx(1.0)
        assert um[0]["win_rate"] == pytest.approx(1.0)

    def test_level2_top_n_limit(
        self, many_masks: dict, many_target: np.ndarray
    ) -> None:
        """top_n limits the number of returned pairs."""
        engine = BitsetEngine(min_support=0.0)
        results = engine.level2_scan(many_masks, many_target, top_n=5)
        assert len(results) <= 5

    # ------------------------------------------------------------------
    # Level 2 — IC calculation
    # ------------------------------------------------------------------

    def test_level2_ic_in_results(
        self, simple_masks: dict, simple_target: np.ndarray
    ) -> None:
        """Level 2 results contain an 'ic' field."""
        engine = BitsetEngine(min_support=0.0)
        results = engine.level2_scan(simple_masks, simple_target, top_n=5000)

        for r in results:
            assert "ic" in r
            assert isinstance(r["ic"], float)

    def test_level2_ic_positive_correlation(self) -> None:
        """IC is positive when mask aligns with positive returns."""
        n = 10
        target = np.array([1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, -1.0])
        masks = {
            "good": np.array(
                [True, True, True, True, True, False, False, False, False, False]
            ),
            # mask and target perfectly covary -> positive IC for good+mask2
            "mask2": np.array(
                [True, True, True, True, True, False, False, False, False, False]
            ),
        }
        engine = BitsetEngine(min_support=0.0)
        results = engine.level2_scan(masks, target)

        # good AND mask2 = same as each mask, should have positive IC > 0
        g2 = [r for r in results if set(r["conditions"]) == {"good", "mask2"}]
        assert len(g2) > 0
        # Perfect alignment: mask indicator [1,1,1,1,1,0,0,0,0,0]
        # target: [1,1,1,1,1,-1,-1,-1,-1,-1]
        # These are perfectly correlated -> IC should be close to 1.0
        assert g2[0]["ic"] > 0.9

    # ------------------------------------------------------------------
    # Level 3 — beam search
    # ------------------------------------------------------------------

    def test_level3_produces_triples(
        self, many_masks: dict, many_target: np.ndarray
    ) -> None:
        """Level 3 produces triple-condition results with improvement."""
        engine = BitsetEngine(min_support=0.0)
        l2 = engine.level2_scan(many_masks, many_target, top_n=20)
        l3 = engine.level3_scan(l2, many_masks, many_target, beam_width=10)

        if l3:
            for r in l3:
                # Each result should have exactly 3 conditions
                assert len(r["conditions"]) == 3
                # Should have the improvement key
                assert "improvement" in r
                # Improvement should be positive (strict improvement check)
                assert r["improvement"] > 0

    def test_level3_sorted_by_mean_net_r(
        self, many_masks: dict, many_target: np.ndarray
    ) -> None:
        """Level 3 results sorted descending by mean_net_R."""
        engine = BitsetEngine(min_support=0.0)
        l2 = engine.level2_scan(many_masks, many_target, top_n=20)
        l3 = engine.level3_scan(l2, many_masks, many_target, beam_width=10)

        if l3:
            mean_rs = [r["mean_net_R"] for r in l3]
            assert mean_rs == sorted(mean_rs, reverse=True)

    def test_level3_no_duplicate_conditions(self) -> None:
        """Triple conditions do NOT repeat a condition already in the pair."""
        masks = {
            "a": np.array([True, True, False, False, False, False]),
            "b": np.array([False, False, True, True, False, False]),
            "c": np.array([False, False, False, False, True, True]),
        }
        target = np.array([2.0, 1.0, 0.5, -0.5, -1.0, -2.0])

        engine = BitsetEngine(min_support=0.0)
        l2 = engine.level2_scan(masks, target, top_n=10)
        l3 = engine.level3_scan(l2, masks, target, beam_width=5)

        for r in l3:
            conds = r["conditions"]
            assert len(conds) == 3
            assert len(set(conds)) == 3  # All unique

    def test_level3_improvement_gate(self) -> None:
        """Triple is rejected when no third condition improves the pair."""
        # All three masks are identical: every pair equals every triple.
        masks = {
            "a": np.array([True, True, False, False]),
            "b": np.array([True, True, False, False]),
            "c": np.array([True, True, False, False]),
        }
        target = np.array([2.0, -1.0, 0.5, -0.5])

        engine = BitsetEngine(min_support=0.0)
        l2 = engine.level2_scan(masks, target, top_n=10)
        l3 = engine.level3_scan(l2, masks, target, beam_width=5)

        # All pairs mean = 0.5, all triples mean = 0.5 -> no improvement
        assert len(l3) == 0

    def test_level3_empty_level2_input(self) -> None:
        """Empty level2_results produces empty level3 results."""
        engine = BitsetEngine()
        result = engine.level3_scan([], {"a": np.array([True])}, np.array([1.0]))
        assert result == []

    # ------------------------------------------------------------------
    # min_support filtering
    # ------------------------------------------------------------------

    def test_min_support_filters_low_support_masks(
        self, simple_masks: dict, simple_target: np.ndarray
    ) -> None:
        """Conditions below min_support threshold are excluded."""
        # all masks have support=2 out of 5 -> need min_support > 0.4
        engine = BitsetEngine(min_support=0.5)
        results = engine.level1_scan(simple_masks, simple_target)
        assert len(results) == 0

    def test_min_support_keeps_high_support(
        self, simple_masks: dict, simple_target: np.ndarray
    ) -> None:
        """Conditions above min_support threshold are included."""
        engine = BitsetEngine(min_support=0.3)  # 30% of 5 = 1.5 -> ceil = 2
        results = engine.level1_scan(simple_masks, simple_target)
        assert len(results) == 3  # all have support=2

    def test_min_support_zero_includes_all(
        self, simple_masks: dict, simple_target: np.ndarray
    ) -> None:
        """min_support=0 includes everything."""
        engine = BitsetEngine(min_support=0.0)
        results = engine.level1_scan(simple_masks, simple_target)
        assert len(results) == 3

    def test_min_support_level2(
        self, simple_masks: dict, simple_target: np.ndarray
    ) -> None:
        """min_support filters Level 2 pairs."""
        engine = BitsetEngine(min_support=0.5)
        results = engine.level2_scan(simple_masks, simple_target, top_n=5000)
        # All pairs have support <= 1 (20%), so all filtered
        assert len(results) == 0

    # ------------------------------------------------------------------
    # Empty input handling
    # ------------------------------------------------------------------

    def test_empty_masks_dict(self) -> None:
        """Empty masks dict returns empty results for all levels."""
        engine = BitsetEngine(min_support=0.0)
        target = np.array([1.0, 2.0, 3.0])

        assert engine.level1_scan({}, target) == []
        assert engine.level2_scan({}, target) == []
        assert engine.level3_scan([], {}, target) == []

    def test_single_mask_no_pairs(self) -> None:
        """Single mask produces zero pairs in Level 2."""
        engine = BitsetEngine(min_support=0.0)
        masks = {"a": np.array([True, False])}
        target = np.array([1.0, -1.0])
        assert engine.level2_scan(masks, target) == []

    def test_all_nan_target(self) -> None:
        """All-NaN target returns empty results."""
        engine = BitsetEngine(min_support=0.0)
        masks = {"a": np.array([True, False])}
        target = np.array([np.nan, np.nan])
        assert engine.level1_scan(masks, target) == []
        assert engine.level2_scan(masks, target) == []
        assert engine.level3_scan([], masks, target) == []

    # ------------------------------------------------------------------
    # Error cases
    # ------------------------------------------------------------------

    def test_shape_mismatch_raises(self) -> None:
        """Mask with wrong shape raises ValueError."""
        engine = BitsetEngine()
        masks = {"a": np.array([True, False, True])}
        target = np.array([1.0, -1.0])
        with pytest.raises(ValueError, match="shape"):
            engine.level1_scan(masks, target)

    def test_dtype_mismatch_raises(self) -> None:
        """Mask with non-bool dtype raises ValueError."""
        engine = BitsetEngine()
        masks = {"a": np.array([1, 0, 1], dtype=np.int64)}
        target = np.array([1.0, -1.0, 0.0])
        with pytest.raises(ValueError, match="dtype"):
            engine.level1_scan(masks, target)

    # ------------------------------------------------------------------
    # Support fraction
    # ------------------------------------------------------------------

    def test_support_frac_in_results(
        self, simple_masks: dict, simple_target: np.ndarray
    ) -> None:
        """Results contain support_frac = support / n."""
        engine = BitsetEngine(min_support=0.0)
        results = engine.level1_scan(simple_masks, simple_target)

        for r in results:
            expected_frac = r["support"] / 5
            assert r["support_frac"] == pytest.approx(expected_frac)

    # ------------------------------------------------------------------
    # Determinism with seed
    # ------------------------------------------------------------------

    def test_deterministic_results(
        self, many_masks: dict, many_target: np.ndarray
    ) -> None:
        """Results are deterministic (same input -> same output)."""
        engine = BitsetEngine(min_support=0.0)
        r1 = engine.level2_scan(many_masks, many_target, top_n=10)
        r2 = engine.level2_scan(many_masks, many_target, top_n=10)

        for a, b in zip(r1, r2):
            assert a["conditions"] == b["conditions"]
            assert a["mean_net_R"] == b["mean_net_R"]


# ===================================================================
# Module-level helper tests
# ===================================================================


class TestHelpers:
    """Unit tests for module-level helpers."""

    def test_safe_mean_normal(self) -> None:
        """_safe_mean returns mean of normal array."""
        arr = np.array([1.0, 2.0, 3.0])
        assert _safe_mean(arr) == pytest.approx(2.0)

    def test_safe_mean_with_nan(self) -> None:
        """_safe_mean ignores NaN."""
        arr = np.array([1.0, np.nan, 3.0])
        assert _safe_mean(arr) == pytest.approx(2.0)

    def test_safe_mean_all_nan(self) -> None:
        """_safe_mean returns NaN for all-NaN array."""
        arr = np.array([np.nan, np.nan])
        assert np.isnan(_safe_mean(arr))

    def test_safe_mean_empty(self) -> None:
        """_safe_mean returns NaN for empty array."""
        arr = np.array([])
        assert np.isnan(_safe_mean(arr))

    def test_min_count_zero(self) -> None:
        """_min_count returns 0 when min_support is 0."""
        assert _min_count(100, 0.0) == 0

    def test_min_count_ceil(self) -> None:
        """_min_count uses ceil to convert fraction to absolute count."""
        assert _min_count(10, 0.15) == 2  # ceil(1.5) = 2

    def test_min_count_clamp_min_1(self) -> None:
        """_min_count returns at least 1 when min_support > 0."""
        assert _min_count(100, 0.001) == 1

    def test_extract_valid(self) -> None:
        """_extract_valid returns non-NaN target values at mask positions."""
        target = np.array([1.0, np.nan, 3.0, np.nan, 5.0])
        mask = np.array([True, True, False, True, True])
        result = _extract_valid(target, mask)
        # mask selects indices 0,1,3,4 -> values [1.0, nan, nan, 5.0]
        # after removing NaN -> [1.0, 5.0]
        assert list(result) == [1.0, 5.0]

    def test_validate_input_passes(self) -> None:
        """Valid masks pass validation."""
        masks = {"a": np.array([True, False])}
        target = np.array([1.0, -1.0])
        _validate_input(masks, target)  # should not raise

    def test_validate_input_empty_masks(self) -> None:
        """Empty masks dict skips validation."""
        _validate_input({}, np.array([1.0]))  # should not raise
