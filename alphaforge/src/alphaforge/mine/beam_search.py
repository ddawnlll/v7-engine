"""Beam Search Miner — Level 3 triple condition discovery via beam search.

Extends the level3_scan concept with a beam-search algorithm that
efficiently explores the space of condition combinations. At each depth
level, only the top-N candidates (by score) are retained for further
expansion.

Design constraints:
  - Deterministic: same inputs always produce identical output
  - numpy only (no pandas or sklearn dependency in core computation)
  - Pruning when adding conditions does not improve score
  - Redundant condition detection via correlation threshold
  - Support-fraction filtering via min_support

Usage::

    miner = BeamSearchMiner(min_support=0.01)
    results = miner.search(
        seed_rules=[{"conditions": ["log_return_4h__d01"], "score": 0.12}],
        masks={
            "log_return_4h__d01": np.array([True, False, ...]),
            "rsi_4h__d05": np.array([False, True, ...]),
        },
        target=np.array([0.5, -0.2, ...]),
        beam_width=100,
        max_depth=3,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BEAM_WIDTH: int = 100
"""Default beam width — number of top candidates retained per level."""

DEFAULT_MAX_DEPTH: int = 3
"""Default maximum number of conditions per rule (triple conditions)."""

DEFAULT_MIN_SUPPORT: float = 0.01
"""Default minimum support fraction (1 % of samples)."""

CORRELATION_THRESHOLD: float = 0.95
"""Pearson correlation threshold above which a candidate is deemed redundant."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MinedRule:
    """A discovered condition combination with its discovery score.

    Attributes:
        conditions: Sorted list of mask_ref strings that form the rule.
        score: Mean target value where all conditions are simultaneously True.
        support_count: Number of samples satisfying all conditions.
        depth: Number of conditions in this rule.
    """

    conditions: List[str] = field(default_factory=list)
    score: float = 0.0
    support_count: int = 0
    depth: int = 0


# ---------------------------------------------------------------------------
# BeamSearchMiner
# ---------------------------------------------------------------------------


class BeamSearchMiner:
    """Level 3 triple condition miner using beam search.

    Explores the condition space by iteratively expanding the best partial
    rules. At each depth level, retains only the top ``beam_width`` candidates.
    Prunes branches where adding a condition does not improve the score.
    Skips conditions that are redundant (correlation > 0.95) with any existing
    condition in the rule.

    Parameters
    ----------
    min_support : float, default ``0.01``
        Minimum support fraction (0 .. 1). Conditions and combined rules
        with support below this threshold are pruned.
    """

    def __init__(self, min_support: float = DEFAULT_MIN_SUPPORT):
        """Initialise the miner with a support threshold.

        Args:
            min_support: Minimum support fraction (0 .. 1). Rules whose
                support fraction falls below this value are discarded.
        """
        self.min_support = min_support

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        seed_rules: List[Dict[str, Any]],
        masks: Dict[str, np.ndarray],
        target: np.ndarray,
        beam_width: int = DEFAULT_BEAM_WIDTH,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> List[Dict[str, Any]]:
        """Run beam search to discover high-scoring condition combinations.

        Starting from seed rules, iteratively expands the best partial
        rules by adding compatible conditions. At each depth level, retains
        only the top ``beam_width`` candidates. Returns all discovered rules
        at every depth, sorted by score descending.

        Args:
            seed_rules: Initial condition sets. Each entry is a dict with
                ``conditions`` (list of mask_ref strings) and an optional
                ``score`` (float). If score is omitted or zero it is
                recomputed from target.
            masks: Dict mapping mask_ref -> boolean numpy array of length N.
                Masks are the boolean conditions available for expansion.
            target: Target array of shape ``(N,)``. The score of a rule is
                ``target[combined_mask].mean()`` where ``combined_mask`` is
                the AND of all conditions in the rule.
            beam_width: Maximum number of candidates to retain per depth
                level. Default 100.
            max_depth: Maximum number of conditions per rule. Default 3.
                The effective depth explored is ``max_depth`` levels beyond
                the number of conditions in the seed rules.

        Returns:
            List of dicts with keys: ``conditions`` (list of str),
            ``score`` (float), ``support_count`` (int), ``depth`` (int).
            Sorted by score descending.

        Raises:
            ValueError: If inputs have inconsistent lengths, non-boolean
                masks, or empty seed_rules / masks.
        """
        self._validate_inputs(seed_rules, masks, target)

        n = self._infer_n(masks)

        # Normalise seed rules to MinedRule objects with verified support
        # and recomputed scores.
        beam: List[MinedRule] = self._normalise_seeds(seed_rules, masks, target, n)

        if not beam:
            return []

        all_results: List[MinedRule] = list(beam)

        # Beam search iterations: expand depth by depth.
        for current_depth in range(1, max_depth + 1):
            if not beam:
                break

            candidates: List[MinedRule] = []

            for rule in beam:
                if rule.depth >= max_depth:
                    continue

                # Build the combined mask for this rule once.
                rule_mask = self._compute_combined_mask(rule.conditions, masks)

                expanded = self.expand_rule(
                    rule=rule,
                    available_masks=masks,
                    combined_mask=rule_mask,
                    target=target,
                    n=n,
                )
                candidates.extend(expanded)

            if not candidates:
                break

            # Deduplicate: treat condition sets as unordered.
            candidates = self._deduplicate(candidates)

            # Score improvement pruning: discard candidates whose score does
            # not exceed the score of their parent rule.
            candidates = self._prune_no_improvement(candidates, beam)

            if not candidates:
                break

            # Sort by score descending, then by support descending.
            candidates.sort(key=lambda r: (-r.score, -r.support_count))

            # Keep top beam_width.
            beam = candidates[:beam_width]

            all_results.extend(beam)

        # Final sort: all results by score descending.
        all_results.sort(key=lambda r: (-r.score, -r.support_count))

        return [self._to_dict(r) for r in all_results]

    def expand_rule(
        self,
        rule: MinedRule,
        available_masks: Dict[str, np.ndarray],
        combined_mask: Optional[np.ndarray] = None,
        target: Optional[np.ndarray] = None,
        n: int = 0,
    ) -> List[MinedRule]:
        """Expand a single rule by trying all compatible new conditions.

        For each available mask, checks:
        - Not already present in the rule.
        - Not redundant (Pearson correlation > 0.95 with any existing
          condition in the rule).
        - Combined support >= min_support * n.

        Args:
            rule: The rule to expand.
            available_masks: All candidate masks keyed by mask_ref.
            combined_mask: Pre-computed AND of all conditions in ``rule``.
                If None, recomputed from ``available_masks``.
            target: Target array for score computation. If None, scores
                are set to 0.0 (caller may recompute later).
            n: Total number of samples. Inferred from ``available_masks``
                if not given.

        Returns:
            List of new MinedRule objects, each with one additional
            condition appended.
        """
        if combined_mask is None:
            combined_mask = self._compute_combined_mask(rule.conditions, available_masks)
        if n == 0:
            n = self._infer_n(available_masks)

        existing_conditions: Set[str] = set(rule.conditions)

        # Pre-compute existing mask arrays for the redundancy check.
        existing_vecs: List[np.ndarray] = [
            available_masks[ref] for ref in rule.conditions
        ]

        new_rules: List[MinedRule] = []

        for ref, mask in available_masks.items():
            # Skip if already in the rule.
            if ref in existing_conditions:
                continue

            # Skip redundant conditions (high correlation with existing).
            if self._is_redundant(mask, existing_vecs):
                continue

            # Compute combined mask with the new condition.
            new_combined = combined_mask & mask
            support = int(new_combined.sum())

            # Support check.
            if support / n < self.min_support or support == 0:
                continue

            # Compute score.
            if target is not None:
                score = float(target[new_combined].mean())
            else:
                score = 0.0

            new_rules.append(
                MinedRule(
                    conditions=sorted([*rule.conditions, ref]),
                    score=score,
                    support_count=support,
                    depth=rule.depth + 1,
                )
            )

        return new_rules

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_inputs(
        self,
        seed_rules: List[Dict[str, Any]],
        masks: Dict[str, np.ndarray],
        target: np.ndarray,
    ) -> None:
        """Validate search inputs, raising ValueError on invalid data."""
        if not seed_rules:
            raise ValueError("seed_rules must not be empty")
        if not masks:
            raise ValueError("masks must not be empty")
        if target.ndim != 1:
            raise ValueError(
                f"target must be 1-dimensional, got {target.ndim}D"
            )

        n = len(target)
        for name, mask in masks.items():
            if mask.dtype != bool:
                raise ValueError(
                    f"mask '{name}' must be boolean, got {mask.dtype}"
                )
            if mask.shape != (n,):
                raise ValueError(
                    f"mask '{name}' shape {mask.shape} does not match "
                    f"target length ({n},)"
                )

    @staticmethod
    def _infer_n(masks: Dict[str, np.ndarray]) -> int:
        """Infer the number of samples from the first mask in the dict."""
        if not masks:
            return 0
        return len(next(iter(masks.values())))

    def _normalise_seeds(
        self,
        seed_rules: List[Dict[str, Any]],
        masks: Dict[str, np.ndarray],
        target: np.ndarray,
        n: int,
    ) -> List[MinedRule]:
        """Convert seed rule dicts to MinedRule objects with verified scores.

        Seeds with insufficient support are filtered out.
        """
        beam: List[MinedRule] = []

        for seed in seed_rules:
            conditions = seed.get("conditions", [])
            if not conditions:
                continue

            combined = self._compute_combined_mask(conditions, masks)
            support = int(combined.sum())

            if support / n < self.min_support:
                continue

            score = seed.get("score", 0.0)
            # Recompute if score is missing or zero.
            if score == 0.0:
                score = float(target[combined].mean())

            beam.append(
                MinedRule(
                    conditions=sorted(conditions),
                    score=score,
                    support_count=support,
                    depth=len(conditions),
                )
            )

        return beam

    @staticmethod
    def _compute_combined_mask(
        conditions: List[str],
        masks: Dict[str, np.ndarray],
    ) -> np.ndarray:
        """Compute the element-wise AND of all condition masks for a rule.

        Args:
            conditions: List of mask_ref keys.
            masks: Dict mapping mask_ref -> boolean array.

        Returns:
            Boolean numpy array of shape ``(n,)`` where True indicates
            all conditions are satisfied.

        Raises:
            ValueError: If conditions list is empty.
        """
        if not conditions:
            raise ValueError(
                "Cannot compute combined mask for an empty condition list"
            )
        combined = masks[conditions[0]].copy()
        for ref in conditions[1:]:
            combined &= masks[ref]
        return combined

    def _is_redundant(
        self,
        candidate: np.ndarray,
        existing_vecs: List[np.ndarray],
    ) -> bool:
        """Check if a candidate mask is redundant with existing conditions.

        A condition is redundant if its Pearson correlation with any
        existing condition exceeds ``CORRELATION_THRESHOLD`` (0.95).

        Args:
            candidate: Candidate boolean mask, shape ``(n,)``.
            existing_vecs: List of boolean masks for existing conditions,
                each of shape ``(n,)``.

        Returns:
            True if the candidate is redundant with any existing condition.
        """
        c_float = candidate.astype(np.float64)
        for existing in existing_vecs:
            corr = self._pearson_corr(c_float, existing.astype(np.float64))
            if corr > CORRELATION_THRESHOLD:
                return True
        return False

    @staticmethod
    def _pearson_corr(a: np.ndarray, b: np.ndarray) -> float:
        """Compute Pearson correlation between two float arrays.

        Args:
            a: First float array, shape ``(n,)``.
            b: Second float array, shape ``(n,)``.

        Returns:
            Pearson correlation coefficient as a float. Returns 0.0 when
            the denominator is zero (constant input).
        """
        a_centered = a - a.mean()
        b_centered = b - b.mean()
        num = (a_centered * b_centered).sum()
        den = np.sqrt((a_centered ** 2).sum() * (b_centered ** 2).sum())
        if den == 0.0:
            return 0.0
        return float(num / den)

    @staticmethod
    def _prune_no_improvement(
        candidates: List[MinedRule],
        parents: List[MinedRule],
    ) -> List[MinedRule]:
        """Prune candidates whose score does not exceed their parent's score.

        For each candidate, finds the parent rule with the same conditions
        minus one. If no parent has a lower score, the candidate is pruned.
        This implements the "no score improvement" pruning rule.

        Args:
            candidates: Expanded candidate rules (one level deeper).
            parents: Parent rules at the previous depth level.

        Returns:
            Filtered list containing only candidates that improve upon
            their parent's score.
        """
        # Build a lookup from parent condition set key -> parent score.
        parent_scores: Dict[str, float] = {}
        for p in parents:
            key = "|".join(p.conditions)
            parent_scores[key] = p.score

        pruned: List[MinedRule] = []
        for c in candidates:
            # The parent should have all conditions except the last one
            # added. Since conditions are sorted, we try removing each
            # condition and check if the remainder matches a known parent.
            best_parent_score = -np.inf
            for i in range(len(c.conditions)):
                parent_key = "|".join(
                    c.conditions[:i] + c.conditions[i + 1:]
                )
                if parent_key in parent_scores:
                    ps = parent_scores[parent_key]
                    if ps > best_parent_score:
                        best_parent_score = ps

            if best_parent_score == -np.inf:
                # No parent found — keep the candidate.
                pruned.append(c)
            elif c.score > best_parent_score:
                # Score improved — keep.
                pruned.append(c)
            # else: no improvement, prune.

        return pruned

    @staticmethod
    def _deduplicate(rules: List[MinedRule]) -> List[MinedRule]:
        """Remove duplicate condition sets (order-insensitive).

        Args:
            rules: List of MinedRule objects.

        Returns:
            List with duplicate condition sets removed. The first
            occurrence of each condition set is kept.
        """
        seen: Set[str] = set()
        deduped: List[MinedRule] = []
        for rule in rules:
            key = "|".join(rule.conditions)
            if key not in seen:
                seen.add(key)
                deduped.append(rule)
        return deduped

    @staticmethod
    def _to_dict(rule: MinedRule) -> Dict[str, Any]:
        """Convert a MinedRule to a JSON-serialisable dict.

        Args:
            rule: The mined rule to serialise.

        Returns:
            Dict with keys: ``conditions``, ``score``, ``support_count``,
            ``depth``.
        """
        return {
            "conditions": rule.conditions,
            "score": round(rule.score, 6),
            "support_count": rule.support_count,
            "depth": rule.depth,
        }
