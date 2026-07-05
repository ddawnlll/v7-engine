"""Rule deduplication and alpha-family clustering.

Deduplicates mining rules using:
1. Condition similarity (same feature family, overlapping buckets)
2. Row-mask Jaccard similarity
3. Return profile correlation
4. Primary feature family detection

Assigns each rule to an alpha family with a representative rule.

Authority boundary:
  - This module does NOT modify simulation truth or outcome labels.
  - It operates purely on mined rule metadata and boolean masks.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature family detection
# ---------------------------------------------------------------------------

_FAMILY_KEYWORDS = {
    "volatility": ["volatility", "atr", "spread"],
    "momentum": ["momentum", "return", "rsi", "roc", "strength"],
    "volume": ["volume", "taker"],
    "regime": ["regime", "trend", "slope"],
    "range_position": ["range", "distance", "pullback", "breakout"],
    "btc_regime": ["btc"],
    "cross_sectional": ["rank", "relative", "cs_"],
    "session": ["hour", "session", "weekday", "time_bucket"],
    "funding": ["funding", "oi"],
    "side": ["side"],
    "mode": ["mode"],
}


def _detect_feature_family(feature_name: str) -> str:
    """Detect the primary feature family from a feature/condition name."""
    name_lower = feature_name.lower()
    for family, keywords in _FAMILY_KEYWORDS.items():
        if any(kw in name_lower for kw in keywords):
            return family
    return "other"


def _extract_family_from_conditions(conditions: List[str]) -> str:
    """Extract the dominant feature family from a rule's conditions."""
    families = [_detect_feature_family(c) for c in conditions]
    # Count families, return most common (excluding side/mode)
    family_counts: Dict[str, int] = {}
    for f in families:
        if f not in ("side", "mode"):
            family_counts[f] = family_counts.get(f, 0) + 1
    if not family_counts:
        return "other"
    return max(family_counts, key=family_counts.get)


# ---------------------------------------------------------------------------
# Jaccard similarity
# ---------------------------------------------------------------------------

def _jaccard_similarity(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    """Compute Jaccard similarity between two boolean masks."""
    intersection = np.sum(mask_a & mask_b)
    union = np.sum(mask_a | mask_b)
    if union == 0:
        return 0.0
    return float(intersection / union)


def _overlap_coefficient(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    """Compute overlap coefficient between two boolean masks."""
    intersection = np.sum(mask_a & mask_b)
    smaller = min(np.sum(mask_a), np.sum(mask_b))
    if smaller == 0:
        return 0.0
    return float(intersection / smaller)


# ---------------------------------------------------------------------------
# Return profile correlation
# ---------------------------------------------------------------------------

def _return_correlation(
    target_a: np.ndarray, mask_a: np.ndarray,
    target_b: np.ndarray, mask_b: np.ndarray,
) -> float:
    """Compute correlation of returns between two rule selections.

    Uses the union of both masks to align return vectors.
    """
    union_mask = mask_a | mask_b
    n = np.sum(union_mask)
    if n < 5:
        return 0.0

    a_vals = np.where(mask_a[union_mask], target_a[union_mask], 0.0)
    b_vals = np.where(mask_b[union_mask], target_b[union_mask], 0.0)

    # Remove zeros from both (unselected rows)
    valid = (mask_a[union_mask]) | (mask_b[union_mask])
    if np.sum(valid) < 3:
        return 0.0

    a_valid = a_vals[valid]
    b_valid = b_vals[valid]

    if np.std(a_valid) < 1e-12 or np.std(b_valid) < 1e-12:
        return 0.0

    corr = np.corrcoef(a_valid, b_valid)[0, 1]
    return float(corr) if not np.isnan(corr) else 0.0


# ---------------------------------------------------------------------------
# RuleDeduplicator
# ---------------------------------------------------------------------------

class RuleDeduplicator:
    """Deduplicates mining rules and assigns alpha families.

    Usage::

        deduper = RuleDeduplicator(jaccard_threshold=0.7)
        result = deduper.deduplicate(rules, masks, target)
        families = result["families"]
        duplicates = result["duplicates"]
    """

    def __init__(
        self,
        jaccard_threshold: float = 0.7,
        correlation_threshold: float = 0.8,
        min_family_size: int = 2,
    ) -> None:
        self.jaccard_threshold = jaccard_threshold
        self.correlation_threshold = correlation_threshold
        self.min_family_size = min_family_size

    def deduplicate(
        self,
        rules: List[Dict[str, Any]],
        masks: Dict[str, np.ndarray],
        target: np.ndarray,
    ) -> Dict[str, Any]:
        """Deduplicate rules and assign families.

        Args:
            rules: List of rule dicts with 'conditions', 'mean_net_R', etc.
            masks: Dict of mask_ref -> boolean array (from bucketizer).
            target: Target array (net_R or excess_net_R).

        Returns:
            Dict with 'families', 'duplicates', 'family_assignments'.
        """
        if not rules:
            return {"families": [], "duplicates": [], "family_assignments": []}

        n_rules = len(rules)
        logger.info("Deduplicating %d rules...", n_rules)

        # Step 1: Compute row masks for each rule
        rule_masks = self._build_rule_masks(rules, masks, len(target))

        # Step 2: Assign feature families
        for i, rule in enumerate(rules):
            rule["primary_family"] = _extract_family_from_conditions(
                rule.get("conditions", [])
            )

        # Step 3: Compute pairwise similarity matrix
        sim_matrix = np.zeros((n_rules, n_rules), dtype=np.float64)
        for i in range(n_rules):
            for j in range(i + 1, n_rules):
                if rule_masks[i] is None or rule_masks[j] is None:
                    continue
                jaccard = _jaccard_similarity(rule_masks[i], rule_masks[j])
                corr = _return_correlation(target, rule_masks[i], target, rule_masks[j])
                # Combined similarity: weighted average
                combined = 0.6 * jaccard + 0.4 * abs(corr)
                sim_matrix[i, j] = combined
                sim_matrix[j, i] = combined

        # Step 4: Cluster rules into families using connected components
        families = self._cluster_families(rules, sim_matrix)

        # Step 5: Select representative for each family
        for family in families:
            member_indices = family["member_indices"]
            # Representative = highest mean_net_R
            best_idx = max(member_indices, key=lambda i: rules[i].get("mean_net_R", 0))
            family["representative_index"] = best_idx
            family["representative_rule_id"] = rules[best_idx].get(
                "rule_id", rules[best_idx].get("id", f"rule_{best_idx}")
            )

        # Step 6: Build duplicate list
        duplicates = []
        family_map = {}  # rule_index -> family_id
        for family in families:
            for idx in family["member_indices"]:
                family_map[idx] = family["family_id"]
                if idx != family["representative_index"]:
                    duplicates.append({
                        "rule_index": idx,
                        "rule_id": rules[idx].get("rule_id", rules[idx].get("id", f"rule_{idx}")),
                        "duplicate_of": family["representative_rule_id"],
                        "family_id": family["family_id"],
                        "similarity": float(sim_matrix[idx, family["representative_index"]]),
                    })

        # Step 7: Build family assignments
        assignments = []
        for i, rule in enumerate(rules):
            fid = family_map.get(i, f"family_orphan_{i}")
            assignments.append({
                "rule_index": i,
                "rule_id": rule.get("rule_id", rule.get("id", f"rule_{i}")),
                "family_id": fid,
                "primary_family": rule.get("primary_family", "other"),
                "is_representative": i in [f["representative_index"] for f in families],
                "duplicate_of": next(
                    (d["duplicate_of"] for d in duplicates if d["rule_index"] == i),
                    None,
                ),
            })

        logger.info(
            "Dedup: %d rules → %d families, %d duplicates",
            n_rules, len(families), len(duplicates),
        )

        return {
            "families": families,
            "duplicates": duplicates,
            "family_assignments": assignments,
        }

    def _build_rule_masks(
        self,
        rules: List[Dict[str, Any]],
        masks: Dict[str, np.ndarray],
        n_samples: int,
    ) -> List[Optional[np.ndarray]]:
        """Build combined boolean mask for each rule."""
        rule_masks = []
        for rule in rules:
            conditions = rule.get("conditions", [])
            combined = None
            for cond in conditions:
                if cond in masks and len(masks[cond]) == n_samples:
                    if combined is None:
                        combined = masks[cond].copy()
                    else:
                        combined = combined & masks[cond]
            rule_masks.append(combined)
        return rule_masks

    def _cluster_families(
        self,
        rules: List[Dict[str, Any]],
        sim_matrix: np.ndarray,
    ) -> List[Dict[str, Any]]:
        """Cluster rules into families using threshold-based connected components."""
        n = len(rules)
        visited = set()
        families = []
        family_counter = 0

        for i in range(n):
            if i in visited:
                continue

            # BFS from rule i
            cluster = [i]
            queue = [i]
            visited.add(i)

            while queue:
                current = queue.pop(0)
                for j in range(n):
                    if j not in visited and sim_matrix[current, j] >= self.jaccard_threshold:
                        visited.add(j)
                        cluster.append(j)
                        queue.append(j)

            # Create family
            family_counter += 1
            member_rules = [rules[idx] for idx in cluster]
            primary_families = [r.get("primary_family", "other") for r in member_rules]
            dominant_family = max(set(primary_families), key=primary_families.count)

            families.append({
                "family_id": f"family_{family_counter:03d}",
                "primary_feature_family": dominant_family,
                "member_indices": cluster,
                "member_count": len(cluster),
                "mean_net_R": float(np.mean([r.get("mean_net_R", 0) for r in member_rules])),
                "max_net_R": float(max(r.get("mean_net_R", 0) for r in member_rules)),
                "representative_index": -1,  # filled later
                "representative_rule_id": "",
            })

        return families
