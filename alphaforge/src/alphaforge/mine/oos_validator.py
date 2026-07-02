"""OOSValidator — Discovery/Validation/Holdout temporal split and overfit detection.

Splits data temporally (not randomly) into three partitions:
  - Discovery  (first 60%): rules are developed here
  - Validation (next 20%): hyperparameters / rule pruning
  - Holdout    (last 20%): final unbiased test

The validator scores discovery rules on the validation and holdout partitions,
computes a consistency_score (min OOS/IS ratio across rules), and flags
overfitting when out-of-sample performance substantially lags in-sample.

Domain boundary:
  - AlphaForge owns OOS validation design and execution.
  - V7 owns final promotion gate authority (G5+).
  - This module does NOT train models, compute profitability, or execute trades.

Usage:
    validator = OOSValidator(discovery_split=0.6, validation_split=0.2)
    parts = validator.split(table, timestamp_col="timestamp")
    result = validator.validate(
        discovery_rules=rules,
        validation_table=parts["validation"],
        holdout_table=parts["holdout"],
    )
    summary = validator.summary()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pyarrow as pa

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_CONSISTENCY_RATIO: float = 0.5
"""Minimum acceptable OOS/IS consistency ratio before overfit warning fires."""

_DEFAULT_RULE_SCORE_COL: str = "target"
"""Default column used to measure rule performance when no target_col is given."""


# ---------------------------------------------------------------------------
# OOSValidator
# ---------------------------------------------------------------------------


class OOSValidator:
    """Temporal discovery/validation/holdout splitter and overfit detector.

    Parameters
    ----------
    discovery_split : float, default 0.6
        Fraction of data used for discovery (first portion).
    validation_split : float, default 0.2
        Fraction of data used for validation (middle portion).
    holdout_split : float, default 0.2
        Fraction of data used for final holdout test (last portion).

    The three splits must sum to 1.0.
    """

    def __init__(
        self,
        discovery_split: float = 0.6,
        validation_split: float = 0.2,
        holdout_split: float = 0.2,
    ) -> None:
        total = discovery_split + validation_split + holdout_split
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"Splits must sum to 1.0, got {discovery_split} + "
                f"{validation_split} + {holdout_split} = {total}"
            )
        self.discovery_split = discovery_split
        self.validation_split = validation_split
        self.holdout_split = holdout_split

        # Mutable state populated by validate()
        self._discovery_rule_count: int = 0
        self._validation_survived: int = 0
        self._holdout_survived: int = 0
        self._consistency_score: Optional[float] = None
        self._overfit_warning: Optional[str] = None
        self._validated: bool = False

    # ------------------------------------------------------------------
    # split
    # ------------------------------------------------------------------

    def split(
        self,
        table: pa.Table,
        timestamp_col: str,
    ) -> Dict[str, pa.Table]:
        """Temporally split *table* into discovery / validation / holdout.

        The split is strictly temporal: rows are sorted by *timestamp_col*
        in ascending order and partitioned at the split boundaries. No
        randomisation, no shuffling.

        Parameters
        ----------
        table : pa.Table
            Input data. Must contain *timestamp_col*.
        timestamp_col : str
            Name of the timestamp column used for ordering.

        Returns
        -------
        Dict[str, pa.Table]
            Keys ``"discovery"``, ``"validation"``, ``"holdout"``.
        """
        if timestamp_col not in table.column_names:
            raise ValueError(
                f"Column '{timestamp_col}' not found in table. "
                f"Available columns: {table.column_names}"
            )
        nrows = table.num_rows
        if nrows < 3:
            raise ValueError(
                f"Table has only {nrows} rows; need at least 3 to split."
            )

        # Sort by timestamp ascending
        sort_keys = pa.compute.sort_indices(table[timestamp_col])
        table_sorted = table.take(sort_keys)

        # Compute row boundaries
        disc_end = int(nrows * self.discovery_split)
        val_end = disc_end + int(nrows * self.validation_split)

        discovery = table_sorted.slice(0, disc_end)
        validation = table_sorted.slice(disc_end, val_end - disc_end)
        holdout = table_sorted.slice(val_end)

        return {
            "discovery": discovery,
            "validation": validation,
            "holdout": holdout,
        }

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    def validate(
        self,
        discovery_rules: List[Dict[str, Any]],
        validation_table: pa.Table,
        holdout_table: pa.Table,
        target_col: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Score *discovery_rules* on validation and holdout partitions.

        For each rule the validator:
          1. Applies the rule filter to *validation_table* and computes the
             mean of *target_col* (or ``"target"``) over the filtered rows.
          2. Applies the same filter to *holdout_table*.
          3. Computes the OOS/IS ratio where IS is the rule's stored
             ``is_score``.
          4. The overall ``consistency_score`` is the *minimum* OOS/IS
             ratio across all surviving rules.
          5. If ``consistency_score < 0.5`` an overfit warning is raised,
             and any rule whose OOS/IS ratio falls below 0.5 is considered
             eliminated on that partition.

        Parameters
        ----------
        discovery_rules : List[Dict]
            Rules discovered on the discovery partition. Each dict must have
            at minimum:
              - ``"feature"`` (str): column name the rule applies to.
              - ``"operator"`` (str): one of ``"gt"``, ``"gte"``, ``"lt"``,
                ``"lte"``, ``"eq"``.
              - ``"threshold"`` (float): threshold value.
              - ``"is_score"`` (float): in-sample performance score used as
                the IS baseline for OOS/IS ratio computation.
        validation_table : pa.Table
            Rows for the validation partition.
        holdout_table : pa.Table
            Rows for the holdout partition.
        target_col : str, optional
            Column whose mean serves as the rule score. Defaults to
            ``"target"``.

        Returns
        -------
        Dict
            Keys: ``"consistency_score"``, ``"survived_validation"``,
            ``"survived_holdout"``, ``"overfit_warning"``,
            ``"rule_results"``.
        """
        _target = target_col or _DEFAULT_RULE_SCORE_COL
        self._discovery_rule_count = len(discovery_rules)
        self._validated = True

        if self._discovery_rule_count == 0:
            self._consistency_score = 1.0
            self._overfit_warning = None
            self._validation_survived = 0
            self._holdout_survived = 0
            return {
                "consistency_score": 1.0,
                "survived_validation": 0,
                "survived_holdout": 0,
                "overfit_warning": None,
                "rule_results": [],
            }

        rule_results: List[Dict[str, Any]] = []
        val_survived = 0
        hold_survived = 0
        oos_is_ratios: List[float] = []

        for rule in discovery_rules:
            result = self._score_rule(
                rule=rule,
                validation_table=validation_table,
                holdout_table=holdout_table,
                target_col=_target,
            )
            rule_results.append(result)

            # Validation survival
            if result.get("validation_score") is not None:
                val_ratio = result.get("validation_oos_is_ratio")
                if val_ratio is not None and val_ratio >= _MIN_CONSISTENCY_RATIO:
                    val_survived += 1
                    if val_ratio is not None:
                        oos_is_ratios.append(val_ratio)

            # Holdout survival
            if result.get("holdout_score") is not None:
                hold_ratio = result.get("holdout_oos_is_ratio")
                if hold_ratio is not None and hold_ratio >= _MIN_CONSISTENCY_RATIO:
                    hold_survived += 1

        self._validation_survived = val_survived
        self._holdout_survived = hold_survived

        # Consistency score: min OOS/IS across all rule-partitions
        if oos_is_ratios:
            self._consistency_score = min(oos_is_ratios)
        else:
            # No rule survived validation — floor the score
            self._consistency_score = 0.0

        # Overfit warning
        if self._consistency_score < _MIN_CONSISTENCY_RATIO:
            self._overfit_warning = (
                f"Consistency score {self._consistency_score:.4f} is below "
                f"threshold {_MIN_CONSISTENCY_RATIO}. "
                f"OOS performance substantially lags IS — likely overfit."
            )
        else:
            self._overfit_warning = None

        return {
            "consistency_score": self._consistency_score,
            "survived_validation": val_survived,
            "survived_holdout": hold_survived,
            "overfit_warning": self._overfit_warning,
            "rule_results": rule_results,
        }

    # ------------------------------------------------------------------
    # summary
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return a summary of the last validation run.

        Returns
        -------
        Dict
            Keys: ``"discovery_rule_count"``, ``"survived_validation"``,
            ``"survived_holdout"``, ``"eliminated_by_validation"``,
            ``"eliminated_by_holdout"``, ``"consistency_score"``,
            ``"overfit_warning"``, ``"final_verdict"``.
        """
        if not self._validated:
            return {
                "discovery_rule_count": 0,
                "survived_validation": 0,
                "survived_holdout": 0,
                "eliminated_by_validation": 0,
                "eliminated_by_holdout": 0,
                "consistency_score": None,
                "overfit_warning": None,
                "final_verdict": "NOT_EVALUATED",
            }

        elim_val = self._discovery_rule_count - self._validation_survived
        elim_hold = self._validation_survived - self._holdout_survived

        if self._holdout_survived == 0:
            verdict = "FAIL"
        elif self._overfit_warning:
            verdict = "PASS_WITH_WARNINGS"
        elif self._consistency_score is not None and self._consistency_score >= 0.8:
            verdict = "PASS"
        else:
            verdict = "PASS_WITH_WARNINGS"

        return {
            "discovery_rule_count": self._discovery_rule_count,
            "survived_validation": self._validation_survived,
            "survived_holdout": self._holdout_survived,
            "eliminated_by_validation": elim_val,
            "eliminated_by_holdout": elim_hold,
            "consistency_score": self._consistency_score,
            "overfit_warning": self._overfit_warning,
            "final_verdict": verdict,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score_rule(
        self,
        rule: Dict[str, Any],
        validation_table: pa.Table,
        holdout_table: pa.Table,
        target_col: str,
    ) -> Dict[str, Any]:
        """Score a single rule on validation and holdout.

        Returns a dict with the rule's feature / operator / threshold and
        ``validation_score``, ``holdout_score``, plus OOS/IS ratios
        computed against ``rule["is_score"]``.
        """
        feature = rule.get("feature", "")
        operator = rule.get("operator", "gt")
        threshold = rule.get("threshold", 0.0)
        is_score = rule.get("is_score")

        result: Dict[str, Any] = {
            "feature": feature,
            "operator": operator,
            "threshold": threshold,
            "is_score": is_score,
        }

        val_score = self._apply_rule_get_mean(
            validation_table, feature, operator, threshold, target_col
        )
        hold_score = self._apply_rule_get_mean(
            holdout_table, feature, operator, threshold, target_col
        )

        result["validation_score"] = val_score
        result["holdout_score"] = hold_score

        # OOS/IS ratios
        if is_score is not None and is_score != 0.0 and val_score is not None:
            result["validation_oos_is_ratio"] = val_score / is_score
        else:
            result["validation_oos_is_ratio"] = None

        if is_score is not None and is_score != 0.0 and hold_score is not None:
            result["holdout_oos_is_ratio"] = hold_score / is_score
        else:
            result["holdout_oos_is_ratio"] = None

        return result

    @staticmethod
    def _apply_rule_get_mean(
        table: pa.Table,
        feature: str,
        operator: str,
        threshold: float,
        target_col: str,
    ) -> Optional[float]:
        """Apply a rule filter to *table* and return the mean of *target_col*.

        Returns ``None`` if the filter produces zero rows or if columns are
        missing.
        """
        if feature not in table.column_names:
            logger.warning("Feature column '%s' not found in table.", feature)
            return None
        if target_col not in table.column_names:
            logger.warning("Target column '%s' not found in table.", target_col)
            return None

        # Build the filter mask
        col = table[feature]
        try:
            if operator == "gt":
                mask = pa.compute.greater(col, threshold)
            elif operator == "gte":
                mask = pa.compute.greater_equal(col, threshold)
            elif operator == "lt":
                mask = pa.compute.less(col, threshold)
            elif operator == "lte":
                mask = pa.compute.less_equal(col, threshold)
            elif operator == "eq":
                mask = pa.compute.equal(col, threshold)
            else:
                logger.warning("Unknown operator '%s'.", operator)
                return None
        except Exception as exc:
            logger.warning("Failed to apply rule filter: %s", exc)
            return None

        # Apply mask and compute mean target
        filtered = table.filter(mask)
        if filtered.num_rows == 0:
            return None

        try:
            mean_val = pa.compute.mean(filtered[target_col])
            if mean_val is None or mean_val.as_py() is None:
                return None
            return float(mean_val.as_py())
        except Exception as exc:
            logger.warning("Failed to compute mean: %s", exc)
            return None
