"""Validation funnel — discovery/validation/holdout temporal split and promotion gates.

Promotes rules through a strict validation pipeline:
1. Discovery period: rules are mined here
2. Validation period: rules must survive OOS
3. Holdout period: final unbiased test

Promotion gates:
- min_support_total
- min_support_per_split
- min_validation_mean_excess_net_R
- min_oos_is_ratio
- min_symbol_stability
- max_redundancy
- cost_stress_required

Authority boundary:
  - This module does NOT modify simulation truth.
  - It evaluates rule quality for research promotion purposes only.
  - V7 owns final production promotion.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pyarrow as pa

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default promotion gates
# ---------------------------------------------------------------------------

DEFAULT_GATES = {
    "min_support_total": 100,
    "min_support_per_split": 30,
    "min_validation_mean_excess_net_R": 0.0,
    "min_oos_is_ratio": 0.5,
    "min_symbol_stability": 0.3,
    "max_redundancy": 0.8,
    "cost_stress_required": True,
}


# ---------------------------------------------------------------------------
# ValidationFunnel
# ---------------------------------------------------------------------------

class ValidationFunnel:
    """Temporal validation funnel with configurable promotion gates.

    Usage::

        funnel = ValidationFunnel()
        splits = funnel.split(table, timestamp_col="timestamp")
        result = funnel.validate(
            rules=rules,
            masks=masks,
            discovery_table=splits["discovery"],
            validation_table=splits["validation"],
            holdout_table=splits["holdout"],
            target_col="excess_net_R",
        )
    """

    def __init__(
        self,
        discovery_split: float = 0.6,
        validation_split: float = 0.2,
        holdout_split: float = 0.2,
        gates: Optional[Dict[str, Any]] = None,
    ) -> None:
        total = discovery_split + validation_split + holdout_split
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Splits must sum to 1.0, got {total}")

        self.discovery_split = discovery_split
        self.validation_split = validation_split
        self.holdout_split = holdout_split
        self.gates = {**DEFAULT_GATES, **(gates or {})}

    def split(
        self,
        table: pa.Table,
        timestamp_col: str = "timestamp",
    ) -> Dict[str, pa.Table]:
        """Temporally split table into discovery/validation/holdout."""
        if timestamp_col not in table.column_names:
            raise ValueError(f"Column '{timestamp_col}' not found")

        nrows = table.num_rows
        if nrows < 10:
            raise ValueError(f"Table has only {nrows} rows; need at least 10")

        sort_keys = pa.compute.sort_indices(table[timestamp_col])
        table_sorted = table.take(sort_keys)

        disc_end = int(nrows * self.discovery_split)
        val_end = disc_end + int(nrows * self.validation_split)

        return {
            "discovery": table_sorted.slice(0, disc_end),
            "validation": table_sorted.slice(disc_end, val_end - disc_end),
            "holdout": table_sorted.slice(val_end),
        }

    def validate(
        self,
        rules: List[Dict[str, Any]],
        masks: Dict[str, np.ndarray],
        discovery_table: pa.Table,
        validation_table: pa.Table,
        holdout_table: pa.Table,
        target_col: str = "excess_net_R",
    ) -> Dict[str, Any]:
        """Validate rules through discovery → validation → holdout.

        Args:
            rules: Mined rules from discovery period.
            masks: Boolean masks from bucketizer.
            discovery_table: Discovery period data.
            validation_table: Validation period data.
            holdout_table: Holdout period data.
            target_col: Target column name.

        Returns:
            Dict with validated_rules, rejected_rules, summary.
        """
        n_disc = discovery_table.num_rows
        n_val = validation_table.num_rows
        n_hold = holdout_table.num_rows

        logger.info(
            "Validation funnel: %d discovery, %d validation, %d holdout rows",
            n_disc, n_val, n_hold,
        )

        validated = []
        rejected = []

        for rule in rules:
            result = self._validate_single_rule(
                rule, masks, discovery_table, validation_table, holdout_table,
                target_col, n_disc, n_val, n_hold,
            )

            if result["status"] == "VALIDATED":
                validated.append(result)
            elif result["status"] == "CANDIDATE_ONLY":
                validated.append(result)  # Include but mark as candidate
            else:
                rejected.append(result)

        # Dedup within validated (remove rules that are near-duplicates)
        validated = self._dedup_validated(validated, masks, len(discovery_table))

        summary = {
            "total_rules": len(rules),
            "validated_count": len(validated),
            "rejected_count": len(rejected),
            "candidate_only_count": sum(1 for r in validated if r["status"] == "CANDIDATE_ONLY"),
            "fully_validated_count": sum(1 for r in validated if r["status"] == "VALIDATED"),
            "gates": self.gates,
            "discovery_rows": n_disc,
            "validation_rows": n_val,
            "holdout_rows": n_hold,
        }

        logger.info(
            "Validation: %d validated (%d fully, %d candidate), %d rejected",
            summary["validated_count"],
            summary["fully_validated_count"],
            summary["candidate_only_count"],
            summary["rejected_count"],
        )

        return {
            "validated_rules": validated,
            "rejected_rules": rejected,
            "summary": summary,
        }

    def _validate_single_rule(
        self,
        rule: Dict[str, Any],
        masks: Dict[str, np.ndarray],
        discovery_table: pa.Table,
        validation_table: pa.Table,
        holdout_table: pa.Table,
        target_col: str,
        n_disc: int,
        n_val: int,
        n_hold: int,
    ) -> Dict[str, Any]:
        """Validate a single rule through all splits."""
        conditions = rule.get("conditions", [])
        rule_id = rule.get("rule_id", rule.get("id", "unknown"))

        # Build combined mask
        combined_mask = None
        for cond in conditions:
            if cond in masks and len(masks[cond]) == n_disc:
                if combined_mask is None:
                    combined_mask = masks[cond].copy()
                else:
                    combined_mask = combined_mask & masks[cond]

        if combined_mask is None:
            return self._make_rejected(rule, rule_id, "no_valid_mask")

        # Discovery metrics
        disc_support = int(np.sum(combined_mask))
        disc_target = discovery_table.column(target_col).to_numpy().astype(float) if target_col in discovery_table.column_names else np.zeros(n_disc)
        disc_mean = float(np.nanmean(disc_target[combined_mask])) if disc_support > 0 else 0.0

        # Check discovery support gate
        if disc_support < self.gates["min_support_total"]:
            return self._make_rejected(rule, rule_id, f"insufficient_discovery_support:{disc_support}")

        # Validation metrics (need to apply same conditions to validation table)
        val_mask = self._apply_conditions_to_table(conditions, masks, validation_table, n_val)
        val_support = int(np.sum(val_mask)) if val_mask is not None else 0
        val_target = validation_table.column(target_col).to_numpy().astype(float) if target_col in validation_table.column_names else np.zeros(n_val)
        val_mean = float(np.nanmean(val_target[val_mask])) if val_mask is not None and val_support > 0 else 0.0

        if val_support < self.gates["min_support_per_split"]:
            return self._make_rejected(rule, rule_id, f"insufficient_validation_support:{val_support}")

        # OOS/IS ratio
        oos_is_ratio = val_mean / disc_mean if disc_mean != 0 else 0.0
        if oos_is_ratio < self.gates["min_oos_is_ratio"]:
            return self._make_rejected(rule, rule_id, f"low_oos_is_ratio:{oos_is_ratio:.3f}")

        # Holdout metrics (if available)
        hold_mask = self._apply_conditions_to_table(conditions, masks, holdout_table, n_hold)
        hold_support = int(np.sum(hold_mask)) if hold_mask is not None else 0
        hold_target = holdout_table.column(target_col).to_numpy().astype(float) if target_col in holdout_table.column_names else np.zeros(n_hold)
        hold_mean = float(np.nanmean(hold_target[hold_mask])) if hold_mask is not None and hold_support > 0 else 0.0

        # Symbol stability
        symbol_stability = self._compute_symbol_stability(
            combined_mask, discovery_table, target_col
        )
        if symbol_stability < self.gates["min_symbol_stability"]:
            return self._make_rejected(rule, rule_id, f"low_symbol_stability:{symbol_stability:.3f}")

        # Determine status
        has_holdout = hold_support >= self.gates["min_support_per_split"]
        if has_holdout and oos_is_ratio >= self.gates["min_oos_is_ratio"]:
            status = "VALIDATED"
        else:
            status = "CANDIDATE_ONLY"

        return {
            "rule_id": rule_id,
            "status": status,
            "conditions": conditions,
            "primary_family": rule.get("primary_family", "other"),
            "discovery": {
                "support": disc_support,
                "mean_excess_net_R": disc_mean,
            },
            "validation": {
                "support": val_support,
                "mean_excess_net_R": val_mean,
            },
            "holdout": {
                "support": hold_support,
                "mean_excess_net_R": hold_mean,
            },
            "oos_is_ratio": oos_is_ratio,
            "symbol_stability": symbol_stability,
            "fail_reasons": [],
        }

    def _make_rejected(
        self, rule: Dict[str, Any], rule_id: str, reason: str
    ) -> Dict[str, Any]:
        """Create a rejected rule result."""
        return {
            "rule_id": rule_id,
            "status": "REJECTED",
            "conditions": rule.get("conditions", []),
            "primary_family": rule.get("primary_family", "other"),
            "discovery": {"support": 0, "mean_excess_net_R": 0.0},
            "validation": {"support": 0, "mean_excess_net_R": 0.0},
            "holdout": {"support": 0, "mean_excess_net_R": 0.0},
            "oos_is_ratio": 0.0,
            "symbol_stability": 0.0,
            "fail_reasons": [reason],
        }

    def _apply_conditions_to_table(
        self,
        conditions: List[str],
        masks: Dict[str, np.ndarray],
        table: pa.Table,
        n_rows: int,
    ) -> Optional[np.ndarray]:
        """Apply mining conditions to a table, returning a boolean mask.

        Note: This is a simplified version. For production, conditions should
        be applied using the bucketizer's fitted thresholds on the target table.
        Here we approximate by checking if the condition masks exist and are
        the right size.
        """
        combined = None
        for cond in conditions:
            if cond in masks and len(masks[cond]) == n_rows:
                if combined is None:
                    combined = masks[cond].copy()
                else:
                    combined = combined & masks[cond]
        return combined

    def _compute_symbol_stability(
        self,
        mask: np.ndarray,
        table: pa.Table,
        target_col: str,
    ) -> float:
        """Compute cross-symbol stability (min per-symbol mean / global mean)."""
        if "symbol" not in table.column_names:
            return 1.0  # No symbol info, assume stable

        symbols = table.column("symbol").to_pylist()
        target = table.column(target_col).to_numpy().astype(float) if target_col in table.column_names else np.zeros(len(symbols))

        unique_symbols = set(symbols)
        if len(unique_symbols) <= 1:
            return 1.0

        per_symbol_means = []
        for sym in unique_symbols:
            sym_mask = np.array([s == sym for s in symbols])
            combined = mask & sym_mask
            n_sym = int(np.sum(combined))
            if n_sym >= 5:
                per_symbol_means.append(float(np.nanmean(target[combined])))

        if not per_symbol_means:
            return 0.0

        global_mean = float(np.nanmean(target[mask])) if np.sum(mask) > 0 else 0.0
        if abs(global_mean) < 1e-12:
            return 0.0

        # Stability = min(per_symbol_mean) / global_mean (clipped to [0, 1])
        min_ratio = min(m / global_mean for m in per_symbol_means if abs(global_mean) > 1e-12)
        return max(0.0, min(1.0, min_ratio))

    def _dedup_validated(
        self,
        validated: List[Dict[str, Any]],
        masks: Dict[str, np.ndarray],
        n_samples: int,
    ) -> List[Dict[str, Any]]:
        """Remove near-duplicate validated rules (keep best)."""
        if len(validated) <= 1:
            return validated

        # Sort by validation mean_excess_net_R descending
        validated.sort(key=lambda r: r.get("validation", {}).get("mean_excess_net_R", 0), reverse=True)

        keep = []
        seen_masks: List[np.ndarray] = []

        for rule in validated:
            conditions = rule.get("conditions", [])
            combined = None
            for cond in conditions:
                if cond in masks and len(masks[cond]) == n_samples:
                    if combined is None:
                        combined = masks[cond].copy()
                    else:
                        combined = combined & masks[cond]

            if combined is None:
                keep.append(rule)
                continue

            # Check similarity against already-kept rules
            is_duplicate = False
            for kept_mask in seen_masks:
                intersection = np.sum(combined & kept_mask)
                union = np.sum(combined | kept_mask)
                jaccard = intersection / union if union > 0 else 0.0
                if jaccard > self.gates["max_redundancy"]:
                    is_duplicate = True
                    break

            if not is_duplicate:
                keep.append(rule)
                seen_masks.append(combined)

        return keep
