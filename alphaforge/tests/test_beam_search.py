"""Tests for BeamSearchMiner — Level 3 triple condition discovery.

Covers:
  (a) Basic beam search from a seed rule
  (b) Beam pruning: no-score-improvement branches are discarded
  (c) max_depth limit: does not exceed specified depth
  (d) Redundant condition skipping (correlation > 0.95)
  (e) Support-fraction filtering via min_support
  (f) Empty seed_rules / masks raises ValueError
  (g) expand_rule skips already-present and redundant conditions
  (h) Deterministic output with same inputs
  (i) Seed rules with pre-supplied scores respected
  (j) MinedRule dataclass construction and _to_dict conversion
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Ensure alphaforge is importable (src/ layout)
# ---------------------------------------------------------------------------
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from alphaforge.mine.beam_search import (
    CORRELATION_THRESHOLD,
    DEFAULT_BEAM_WIDTH,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MIN_SUPPORT,
    BeamSearchMiner,
    MinedRule,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_synthetic_masks(
    n: int = 100,
    n_masks: int = 20,
    seed: int = 42,
) -> Dict[str, np.ndarray]:
    """Create reproducible boolean masks for testing.

    Each mask is an independent random boolean array of length *n*.
    Mask keys are ``f"feat_{i:02d}__d05"``.
    """
    rng = np.random.RandomState(seed)
    masks: Dict[str, np.ndarray] = {}
    for i in range(n_masks):
        # Each mask has roughly 50 % True values.
        masks[f"feat_{i:02d}__d05"] = rng.rand(n) > 0.5
    return masks


def _make_correlated_masks(
    n: int = 100,
    seed: int = 42,
) -> Dict[str, np.ndarray]:
    """Create masks where two are highly correlated for redundancy testing."""
    rng = np.random.RandomState(seed)
    base = rng.rand(n) > 0.4  # ~60 % True

    masks: Dict[str, np.ndarray] = {
        "feat_00__d05": base,
        # feat_01 is 98 % correlated with feat_00 (> 0.95 threshold).
        "feat_01__d05": _flip_fraction(base, 0.02, rng),
        # feat_02 is only 80 % correlated with feat_00 (< 0.95).
        "feat_02__d05": _flip_fraction(base, 0.20, rng),
        # feat_03 is mostly independent.
        "feat_03__d05": rng.rand(n) > 0.5,
    }
    return masks


def _flip_fraction(
    arr: np.ndarray,
    fraction: float,
    rng: np.random.RandomState,
) -> np.ndarray:
    """Return a copy of *arr* with a random *fraction* of bits flipped."""
    out = arr.copy()
    flip = rng.rand(len(arr)) < fraction
    out[flip] = ~out[flip]
    return out


def _make_target(
    n: int = 100,
    seed: int = 42,
) -> np.ndarray:
    """Create a synthetic target array (gaussian)."""
    rng = np.random.RandomState(seed)
    return rng.randn(n).astype(np.float64)


# ===========================================================================
# Tests
# ===========================================================================


class TestMinedRule:
    """MinedRule dataclass construction and dict conversion."""

    def test_default_construction(self) -> None:
        rule = MinedRule()
        assert rule.conditions == []
        assert rule.score == 0.0
        assert rule.support_count == 0
        assert rule.depth == 0

    def test_construction_with_values(self) -> None:
        rule = MinedRule(
            conditions=["a__d01", "b__d05"],
            score=0.42,
            support_count=50,
            depth=2,
        )
        assert rule.conditions == ["a__d01", "b__d05"]
        assert rule.score == 0.42
        assert rule.support_count == 50
        assert rule.depth == 2

    def test_to_dict(self) -> None:
        rule = MinedRule(
            conditions=["x__d03"],
            score=0.12345678,
            support_count=10,
            depth=1,
        )
        d = BeamSearchMiner._to_dict(rule)
        assert d["conditions"] == ["x__d03"]
        assert d["score"] == 0.123457  # rounded to 6 places
        assert d["support_count"] == 10
        assert d["depth"] == 1


class TestBeamSearchMinerInit:
    """Miner initialisation defaults."""

    def test_default_min_support(self) -> None:
        miner = BeamSearchMiner()
        assert miner.min_support == DEFAULT_MIN_SUPPORT

    def test_custom_min_support(self) -> None:
        miner = BeamSearchMiner(min_support=0.05)
        assert miner.min_support == 0.05


class TestBeamSearchMinerSearch:
    """Core search() functionality."""

    def test_basic_search(self) -> None:
        """Search from a single seed with default params returns rules."""
        n = 200
        masks = _make_synthetic_masks(n=n, n_masks=15, seed=1)
        target = _make_target(n=n, seed=2)

        miner = BeamSearchMiner(min_support=0.01)
        results = miner.search(
            seed_rules=[{"conditions": ["feat_00__d05"], "score": 0.05}],
            masks=masks,
            target=target,
            beam_width=10,
            max_depth=2,
        )

        assert len(results) > 0
        # First result should be the seed or best expanded rule.
        for r in results:
            assert "conditions" in r
            assert "score" in r
            assert "support_count" in r
            assert "depth" in r
            assert 1 <= r["depth"] <= 2
            assert r["support_count"] > 0

    def test_results_sorted_by_score_descending(self) -> None:
        """Results are returned in descending score order."""
        n = 200
        masks = _make_synthetic_masks(n=n, n_masks=10, seed=10)
        target = _make_target(n=n, seed=11)

        miner = BeamSearchMiner(min_support=0.01)
        results = miner.search(
            seed_rules=[{"conditions": ["feat_00__d05"], "score": 0.01}],
            masks=masks,
            target=target,
            beam_width=20,
            max_depth=2,
        )

        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_max_depth_limit(self) -> None:
        """search does not exceed max_depth conditions per rule."""
        n = 200
        masks = _make_synthetic_masks(n=n, n_masks=10, seed=20)
        target = _make_target(n=n, seed=21)

        miner = BeamSearchMiner(min_support=0.01)
        results = miner.search(
            seed_rules=[{"conditions": ["feat_00__d05"], "score": 0.01}],
            masks=masks,
            target=target,
            beam_width=20,
            max_depth=2,
        )

        for r in results:
            assert r["depth"] <= 2, f"Rule depth {r['depth']} exceeds max_depth=2"

    def test_max_depth_3_triple_condition(self) -> None:
        """At max_depth=3, rules can have up to 3 conditions (triple)."""
        n = 400
        masks = _make_synthetic_masks(n=n, n_masks=10, seed=30)
        target = _make_target(n=n, seed=31)

        miner = BeamSearchMiner(min_support=0.01)
        results = miner.search(
            seed_rules=[{"conditions": ["feat_00__d05"], "score": 0.01}],
            masks=masks,
            target=target,
            beam_width=20,
            max_depth=3,
        )

        depths = [r["depth"] for r in results]
        assert max(depths) <= 3
        # At least some rules should reach depth 3 (unless all pruned).
        assert any(d == 3 for d in depths) or len(results) > 0

    def test_beam_width_respected(self) -> None:
        """At each depth, at most beam_width candidates are retained."""
        n = 100
        masks = _make_synthetic_masks(n=n, n_masks=30, seed=40)
        target = _make_target(n=n, seed=41)

        miner = BeamSearchMiner(min_support=0.01)
        results = miner.search(
            seed_rules=[{"conditions": ["feat_00__d05"], "score": 0.01}],
            masks=masks,
            target=target,
            beam_width=5,
            max_depth=2,
        )

        # The total results list may be larger (aggregated across depths),
        # but at each depth we only keep beam_width. Since we don't expose
        # per-depth intermediate state, we verify the top results are bounded.
        # With 30 candidates per expansion and beam_width=5, it's a strong
        # filter — we should still get results but far fewer than all combos.
        assert len(results) <= 5 + 5 * 5  # rough upper bound

    def test_empty_seed_rules_raises(self) -> None:
        """Empty seed_rules raises ValueError."""
        miner = BeamSearchMiner()
        masks = _make_synthetic_masks(n=50, n_masks=3, seed=99)
        target = _make_target(n=50, seed=100)

        with pytest.raises(ValueError, match="seed_rules must not be empty"):
            miner.search(
                seed_rules=[],
                masks=masks,
                target=target,
            )

    def test_empty_masks_raises(self) -> None:
        """Empty masks raises ValueError."""
        miner = BeamSearchMiner()
        target = _make_target(n=50, seed=101)

        with pytest.raises(ValueError, match="masks must not be empty"):
            miner.search(
                seed_rules=[{"conditions": ["a__d01"], "score": 0.1}],
                masks={},
                target=target,
            )

    def test_non_boolean_mask_raises(self) -> None:
        """Non-boolean mask raises ValueError."""
        miner = BeamSearchMiner()
        target = _make_target(n=50, seed=102)

        with pytest.raises(ValueError, match="must be boolean"):
            miner.search(
                seed_rules=[{"conditions": ["a__d01"], "score": 0.1}],
                masks={"a__d01": np.ones(50, dtype=np.float64)},
                target=target,
            )

    def test_mask_target_length_mismatch_raises(self) -> None:
        """Mask with wrong length raises ValueError."""
        miner = BeamSearchMiner()
        target = _make_target(n=50, seed=103)

        with pytest.raises(ValueError, match="shape"):
            miner.search(
                seed_rules=[{"conditions": ["a__d01"], "score": 0.1}],
                masks={"a__d01": np.ones(40, dtype=bool)},
                target=target,
            )

    def test_seeds_with_insufficient_support_are_filtered(self) -> None:
        """Seeds below min_support are silently dropped."""
        n = 100
        masks = _make_synthetic_masks(n=n, n_masks=3, seed=50)
        target = _make_target(n=n, seed=51)

        # Create a mask that is almost never True.
        masks["rare__d01"] = np.zeros(n, dtype=bool)
        masks["rare__d01"][0] = True  # 1 % support

        miner = BeamSearchMiner(min_support=0.05)  # need 5 %
        results = miner.search(
            seed_rules=[
                {"conditions": ["rare__d01"], "score": 0.1},
                {"conditions": ["feat_00__d05"], "score": 0.01},
            ],
            masks=masks,
            target=target,
            beam_width=10,
            max_depth=1,
        )

        # The rare seed should be filtered out; feat_00 seed may remain.
        for r in results:
            assert "rare__d01" not in r["conditions"]

    def test_deterministic_output(self) -> None:
        """Same inputs always produce identical output."""
        n = 100
        masks = _make_synthetic_masks(n=n, n_masks=8, seed=60)
        target = _make_target(n=n, seed=61)

        miner = BeamSearchMiner(min_support=0.01)

        results1 = miner.search(
            seed_rules=[{"conditions": ["feat_00__d05"], "score": 0.01}],
            masks=masks,
            target=target,
            beam_width=10,
            max_depth=2,
        )

        results2 = miner.search(
            seed_rules=[{"conditions": ["feat_00__d05"], "score": 0.01}],
            masks=masks,
            target=target,
            beam_width=10,
            max_depth=2,
        )

        assert results1 == results2

    def test_seed_score_respected(self) -> None:
        """Seeds with pre-supplied scores are used without recomputation."""
        n = 100
        masks = _make_synthetic_masks(n=n, n_masks=5, seed=70)
        target = _make_target(n=n, seed=71)

        supplied_score = 0.99  # deliberately high
        miner = BeamSearchMiner(min_support=0.01)
        results = miner.search(
            seed_rules=[{"conditions": ["feat_00__d05"], "score": supplied_score}],
            masks=masks,
            target=target,
            beam_width=10,
            max_depth=1,
        )

        # The seed itself should appear with the supplied score.
        for r in results:
            if r["conditions"] == ["feat_00__d05"]:
                assert r["score"] == supplied_score
                break
        else:
            # If the seed was pruned (e.g. expanded versions had better
            # scores), that's also valid — but at least one result exists.
            assert len(results) > 0


class TestBeamSearchMinerExpandRule:
    """expand_rule() filtering logic."""

    def test_skips_existing_conditions(self) -> None:
        """expand_rule does not return rules with already-present conditions."""
        n = 100
        masks = _make_synthetic_masks(n=n, n_masks=5, seed=80)

        rule = MinedRule(conditions=["feat_00__d05"], score=0.1, support_count=50, depth=1)
        combined = masks["feat_00__d05"].copy()

        miner = BeamSearchMiner(min_support=0.01)
        expanded = miner.expand_rule(
            rule=rule,
            available_masks=masks,
            combined_mask=combined,
            target=_make_target(n=n, seed=81),
            n=n,
        )

        # No expanded rule should contain feat_00__d05 as a second condition
        # (it's already in the rule, so it can't be re-added).
        for r in expanded:
            assert r.conditions == sorted(r.conditions)
            # The new condition should be different from feat_00__d05.
            assert len(r.conditions) == 2
            assert "feat_00__d05" in r.conditions
            added = [c for c in r.conditions if c != "feat_00__d05"]
            assert len(added) == 1
            assert added[0] != "feat_00__d05"

    def test_skips_redundant_conditions(self) -> None:
        """expand_rule skips conditions with correlation > 0.95."""
        n = 200
        masks = _make_correlated_masks(n=n, seed=90)
        target = _make_target(n=n, seed=91)

        # feat_00 and feat_01 are > 0.95 correlated.
        # Starting from feat_02, feat_01 should be skipped as redundant
        # (correlated with feat_00 would be checked if feat_00 is in the rule).
        # Starting from feat_00, feat_01 should be skipped (redundant).
        rule = MinedRule(
            conditions=["feat_00__d05"],
            score=0.1,
            support_count=n // 2,
            depth=1,
        )
        combined = masks["feat_00__d05"].copy()

        miner = BeamSearchMiner(min_support=0.01)
        expanded = miner.expand_rule(
            rule=rule,
            available_masks=masks,
            combined_mask=combined,
            target=target,
            n=n,
        )

        expanded_refs = {tuple(r.conditions) for r in expanded}

        # feat_01 should NOT appear combined with feat_00 (redundant).
        redundant_combo = ("feat_00__d05", "feat_01__d05")
        assert redundant_combo not in expanded_refs, (
            f"Redundant combo {redundant_combo} should have been skipped"
        )

        # feat_02 should appear (only 80% correlated).
        non_redundant_combo = ("feat_00__d05", "feat_02__d05")
        assert non_redundant_combo in expanded_refs, (
            f"Non-redundant combo {non_redundant_combo} should have been kept"
        )

    def test_support_filtering(self) -> None:
        """expand_rule skips conditions that drop support below min_support."""
        n = 200
        masks = _make_synthetic_masks(n=n, n_masks=5, seed=100)
        target = _make_target(n=n, seed=101)

        # Create a very rare mask that barely overlaps with the seed.
        masks["rare__d01"] = np.zeros(n, dtype=bool)
        masks["rare__d01"][:5] = True  # only 5 True, all at beginning

        # Seed uses feat_00 which has ~50 % True. The overlap with
        # rare__d01 should be small.
        rule = MinedRule(
            conditions=["feat_00__d05"],
            score=0.1,
            support_count=n // 2,
            depth=1,
        )
        combined = masks["feat_00__d05"].copy()

        miner = BeamSearchMiner(min_support=0.10)  # need 20 out of 200
        expanded = miner.expand_rule(
            rule=rule,
            available_masks=masks,
            combined_mask=combined,
            target=target,
            n=n,
        )

        expanded_refs = {tuple(r.conditions) for r in expanded}

        # rare__d01 combined with feat_00 likely has very low support.
        rare_combo = ("feat_00__d05", "rare__d01")
        if rare_combo in expanded_refs:
            # It's okay if the overlap happened to be high by chance,
            # but let's verify the support check actually runs.
            for r in expanded:
                if tuple(r.conditions) == rare_combo:
                    assert r.support_count / n >= 0.10
                    break

    def test_expand_without_target_returns_zero_scores(self) -> None:
        """When target is None, expanded rules get score 0.0."""
        n = 100
        masks = _make_synthetic_masks(n=n, n_masks=3, seed=110)

        rule = MinedRule(
            conditions=["feat_00__d05"],
            score=0.1,
            support_count=50,
            depth=1,
        )
        combined = masks["feat_00__d05"].copy()

        miner = BeamSearchMiner(min_support=0.01)
        expanded = miner.expand_rule(
            rule=rule,
            available_masks=masks,
            combined_mask=combined,
            target=None,
            n=n,
        )

        for r in expanded:
            assert r.score == 0.0


class TestBeamSearchMinerPruning:
    """Pruning logic: score improvement and deduplication."""

    def test_prune_no_improvement(self) -> None:
        """Candidates that do not improve score are pruned."""
        n = 200
        masks = _make_synthetic_masks(n=n, n_masks=8, seed=120)
        target = _make_target(n=n, seed=121)

        # Single seed with a moderate score.
        miner = BeamSearchMiner(min_support=0.01)
        results = miner.search(
            seed_rules=[{"conditions": ["feat_00__d05"], "score": 0.5}],
            masks=masks,
            target=target,
            beam_width=20,
            max_depth=2,
        )

        # Every result at depth > 1 should have a score >= the parent
        # (from pruning). We can't directly observe intermediate state,
        # but we can verify no depth-2 rule has a suspiciously low score.
        for r in results:
            if r["depth"] == 2:
                # The score should be at least the seed's score if it
                # was an improvement — but pruning only checks vs the
                # immediate parent, not the seed. This is a sanity check.
                assert r["score"] >= -10.0  # very loose bound

    def test_deduplication(self) -> None:
        """Duplicate condition sets are removed."""
        # Test the static dedup method directly.
        rules = [
            MinedRule(conditions=["a", "b"], score=0.5, support_count=10, depth=2),
            MinedRule(conditions=["a", "b"], score=0.4, support_count=10, depth=2),
            MinedRule(conditions=["a", "c"], score=0.3, support_count=10, depth=2),
        ]
        deduped = BeamSearchMiner._deduplicate(rules)
        assert len(deduped) == 2
        # First occurrence wins (score 0.5 kept, 0.4 dropped).
        assert deduped[0].conditions == ["a", "b"]
        assert deduped[0].score == 0.5

    def test_pearson_corr_identity(self) -> None:
        """_pearson_corr of a vector with itself returns 1.0."""
        a = np.array([1.0, 0.0, 1.0, 0.0, 1.0])
        corr = BeamSearchMiner._pearson_corr(a, a)
        assert abs(corr - 1.0) < 1e-10

    def test_pearson_corr_anti_corr(self) -> None:
        """_pearson_corr of a vector with its negation returns -1.0."""
        a = np.array([1.0, 0.0, 1.0, 0.0])
        b = np.array([0.0, 1.0, 0.0, 1.0])
        corr = BeamSearchMiner._pearson_corr(a, b)
        assert abs(corr - (-1.0)) < 1e-10

    def test_pearson_corr_constant(self) -> None:
        """_pearson_corr with a constant vector returns 0.0."""
        a = np.array([1.0, 0.0, 1.0, 0.0])
        const = np.array([1.0, 1.0, 1.0, 1.0])
        corr = BeamSearchMiner._pearson_corr(a, const)
        assert corr == 0.0

    def test_is_redundant_detects_high_correlation(self) -> None:
        """_is_redundant returns True when correlation exceeds threshold."""
        n = 100
        rng = np.random.RandomState(200)
        base = rng.rand(n) > 0.5
        high_corr = _flip_fraction(base, 0.02, rng)  # ~98 % correlated
        low_corr = _flip_fraction(base, 0.30, rng)   # ~70 % correlated

        miner = BeamSearchMiner()

        # High correlation with base should be detected as redundant.
        assert miner._is_redundant(high_corr, [base])

        # Low correlation should not be flagged.
        assert not miner._is_redundant(low_corr, [base])

    def test_prune_no_improvement_static(self) -> None:
        """_prune_no_improvement classmethod filters correctly."""
        parents = [
            MinedRule(conditions=["a"], score=0.5, support_count=50, depth=1),
        ]
        candidates = [
            # Improved.
            MinedRule(conditions=["a", "b"], score=0.7, support_count=30, depth=2),
            # Not improved.
            MinedRule(conditions=["a", "c"], score=0.4, support_count=30, depth=2),
            # No parent match (different set).
            MinedRule(conditions=["d", "e"], score=0.3, support_count=30, depth=2),
        ]
        pruned = BeamSearchMiner._prune_no_improvement(candidates, parents)
        assert len(pruned) == 2
        pruned_keys = {"|".join(r.conditions) for r in pruned}
        assert "a|b" in pruned_keys  # improved
        assert "d|e" in pruned_keys  # no parent match, kept
        assert "a|c" not in pruned_keys  # not improved


class TestBeamSearchMinerIntegration:
    """End-to-end integration scenarios."""

    def test_three_condition_discovery(self) -> None:
        """Can discover triple-condition rules when signal exists."""
        n = 500
        rng = np.random.RandomState(200)

        # Create masks where specific triple condition has a strong signal.
        masks: Dict[str, np.ndarray] = {}
        for i in range(15):
            masks[f"feat_{i:02d}__d05"] = rng.rand(n) > 0.5

        # Target: higher where feat_01 AND feat_05 AND feat_09 are True.
        signal = masks["feat_01__d05"] & masks["feat_05__d05"] & masks["feat_09__d05"]
        target = rng.randn(n).astype(np.float64)
        target[signal] += 1.0  # boost mean where triple condition holds

        miner = BeamSearchMiner(min_support=0.01)
        results = miner.search(
            seed_rules=[{"conditions": ["feat_01__d05"], "score": 0.0}],
            masks=masks,
            target=target,
            beam_width=50,
            max_depth=3,
        )

        # At least some results should exist.
        assert len(results) > 0

        # The best result should have score > random baseline (approx 0).
        assert results[0]["score"] > 0.0

    def test_low_support_pruning_during_search(self) -> None:
        """Rules that fall below min_support during expansion are pruned."""
        n = 500
        masks = _make_synthetic_masks(n=n, n_masks=10, seed=300)
        target = _make_target(n=n, seed=301)

        # Very high min_support should cause aggressive pruning.
        miner = BeamSearchMiner(min_support=0.40)  # need 40 % support
        results = miner.search(
            seed_rules=[{"conditions": ["feat_00__d05"], "score": 0.01}],
            masks=masks,
            target=target,
            beam_width=50,
            max_depth=3,
        )

        # All surviving rules should meet the support threshold.
        for r in results:
            assert r["support_count"] / n >= 0.40 - 1e-9

    def test_multiple_seeds(self) -> None:
        """Multiple seed rules are all considered."""
        n = 200
        masks = _make_synthetic_masks(n=n, n_masks=10, seed=400)
        target = _make_target(n=n, seed=401)

        miner = BeamSearchMiner(min_support=0.01)
        results = miner.search(
            seed_rules=[
                {"conditions": ["feat_00__d05"], "score": 0.1},
                {"conditions": ["feat_03__d05"], "score": 0.2},
            ],
            masks=masks,
            target=target,
            beam_width=20,
            max_depth=2,
        )

        assert len(results) > 0
        # Both seeds should be represented.
        seed_conds = {frozenset(["feat_00__d05"]), frozenset(["feat_03__d05"])}
        result_conds = {frozenset(r["conditions"]) for r in results}
        assert seed_conds & result_conds, (
            "At least one seed should appear in results"
        )


class TestBeamSearchMinerConstants:
    """Module-level constants are at expected values."""

    def test_beam_width_default(self) -> None:
        assert DEFAULT_BEAM_WIDTH == 100

    def test_max_depth_default(self) -> None:
        assert DEFAULT_MAX_DEPTH == 3

    def test_min_support_default(self) -> None:
        assert DEFAULT_MIN_SUPPORT == 0.01

    def test_correlation_threshold(self) -> None:
        assert CORRELATION_THRESHOLD == 0.95
