"""Continuous feature bucketizer — decile thresholds into boolean mask bitsets.

Transforms continuous feature columns into boolean masks for use as bitsets
in the mining engine. Supports generic decile buckets and domain-specific
named bucket schemas (volatility, regime, momentum).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pyarrow as pa

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bucket schemas — each maps a human-readable bucket name to an inclusive
# decile range [lo, hi] where deciles are 1-indexed (1 = 0th-10th percentile,
# 2 = 10th-20th, ..., 10 = 90th-100th).
# ---------------------------------------------------------------------------

# Volatility: 5 buckets, wider mid-band for normal-range regimes.
VOLATILITY_BUCKETS: Dict[str, Tuple[int, int]] = {
    "very_low": (1, 1),
    "low": (2, 3),
    "mid": (4, 7),
    "high": (8, 9),
    "very_high": (10, 10),
}

# Regime: 3 buckets, balanced ternary split.
REGIME_BUCKETS: Dict[str, Tuple[int, int]] = {
    "down": (1, 3),
    "range": (4, 7),
    "up": (8, 10),
}

# Momentum: 5 buckets, symmetric around neutral.
MOMENTUM_BUCKETS: Dict[str, Tuple[int, int]] = {
    "strong_bear": (1, 2),
    "weak_bear": (3, 4),
    "neutral": (5, 6),
    "weak_bull": (7, 8),
    "strong_bull": (9, 10),
}

# Feature-name keyword -> (domain_key, bucket_schema) lookup table.
# Order matters — first match wins.
_DOMAIN_MAP: List[Tuple[List[str], str, Dict[str, Tuple[int, int]]]] = [
    (["volatility", "atr"], "volatility", VOLATILITY_BUCKETS),
    (["regime"], "regime", REGIME_BUCKETS),
    (["momentum", "return", "rsi", "roc", "strength"], "momentum", MOMENTUM_BUCKETS),
]


@dataclass
class ConditionRecord:
    """A single condition produced by the bucketizer.

    Attributes
    ----------
    feature : str
        Name of the feature column this condition applies to.
    bucket : str
        Human-readable bucket label (e.g. ``"very_low"``, ``"d03"``).
    mask_ref : str
        Key used in the dict returned by ``transform()``, following the
        pattern ``<feature>__<bucket>``.
    support_count : int
        Number of samples that satisfy this condition in the transformed data.
    """

    feature: str
    bucket: str
    mask_ref: str
    support_count: int


# ---------------------------------------------------------------------------
# FeatureBucketizer
# ---------------------------------------------------------------------------


class FeatureBucketizer:
    """Bins continuous feature columns into decile-based boolean masks.

    During ``fit()``, computes decile thresholds for each feature column and
    detects domain-specific bucket schemas from feature names.

    During ``transform()``, produces boolean numpy arrays for every
    bucket × feature combination. Masks are designed for direct use as
    bitsets in the mining engine.

    Parameters
    ----------
    min_support : float, default ``0.0``
        Minimum support fraction (0 .. 1). Conditions whose support falls
        below this threshold are excluded from ``get_condition_registry()``.
    """

    def __init__(self, min_support: float = 0.0):
        self.min_support = min_support

        # ---- fitted state ----
        self.thresholds_: Dict[str, np.ndarray] = {}
        """Decile boundaries per feature (9 values: 10th .. 90th percentile)."""

        self.feature_domains_: Dict[str, str] = {}
        """Domain key per feature when its name matched a known pattern."""

        self._condition_registry_: List[ConditionRecord] = []
        self._fitted: bool = False

    # ------------------------------------------------------------------
    # fit
    # ------------------------------------------------------------------

    def fit(
        self,
        table: pa.Table,
        feature_columns: List[str],
    ) -> "FeatureBucketizer":
        """Compute decile thresholds and detect domain schemas.

        Parameters
        ----------
        table : pyarrow.Table
            Discovery (training) data used to determine decile boundaries.
        feature_columns : list of str
            Names of continuous feature columns to bucket.

        Returns
        -------
        FeatureBucketizer
            Fitted instance (self).
        """
        for col in feature_columns:
            if col not in table.column_names:
                raise ValueError(
                    f"Column '{col}' not found in table. "
                    f"Available: {table.column_names}"
                )

            arr = table.column(col).to_numpy().astype(np.float64)
            valid = arr[~np.isnan(arr)]

            if len(valid) == 0:
                logger.warning(
                    "Column '%s' has no non-NaN values; using zero thresholds", col
                )
                self.thresholds_[col] = np.zeros(9, dtype=np.float64)
            else:
                self.thresholds_[col] = np.nanpercentile(
                    valid, np.arange(10, 100, 10)
                )

            # Detect domain from feature name keywords.
            domain = _detect_domain(col)
            if domain is not None:
                self.feature_domains_[col] = domain

        self._fitted = True
        return self

    # ------------------------------------------------------------------
    # transform
    # ------------------------------------------------------------------

    def transform(self, table: pa.Table) -> Dict[str, np.ndarray]:
        """Generate boolean masks for all bucket × feature combinations.

        Parameters
        ----------
        table : pyarrow.Table
            Data to transform. Must contain all columns that were passed
            to ``fit()``.

        Returns
        -------
        dict of str -> np.ndarray
            Mapping of mask reference keys to boolean numpy arrays of shape
            ``(n_samples,)``. Keys follow the pattern ``<feature>__<bucket>``.
        """
        if not self._fitted:
            raise RuntimeError("Must call fit() before transform()")

        masks: Dict[str, np.ndarray] = {}
        n = table.num_rows

        for col, thresholds in self.thresholds_.items():
            if col not in table.column_names:
                raise ValueError(
                    f"Column '{col}' not found in transform table. "
                    f"Available: {table.column_names}"
                )

            raw = table.column(col).to_numpy().astype(np.float64)
            isnan = np.isnan(raw)

            # -- decile masks (always created) -----------------------
            decile_masks = _compute_decile_masks(raw, thresholds, isnan)

            for i, mask in enumerate(decile_masks):
                masks[f"{col}__d{i + 1:02d}"] = mask

            # -- domain-specific masks (when feature name matched) ---
            domain = self.feature_domains_.get(col)
            if domain is not None:
                schema = _get_schema(domain)
                for bucket_name, (lo, hi) in schema.items():
                    combined = np.zeros(n, dtype=bool)
                    for d in range(lo, hi + 1):
                        combined |= decile_masks[d - 1]
                    masks[f"{col}__{bucket_name}"] = combined

        # -- condition registry (filtered by min_support) ------------
        self._condition_registry_.clear()
        for key, mask in masks.items():
            support = int(mask.sum())
            support_frac = support / n if n > 0 else 0.0
            if support_frac >= self.min_support:
                feature, bucket = _split_mask_ref(key)
                self._condition_registry_.append(
                    ConditionRecord(
                        feature=feature,
                        bucket=bucket,
                        mask_ref=key,
                        support_count=support,
                    )
                )

        return masks

    # ------------------------------------------------------------------
    # condition registry
    # ------------------------------------------------------------------

    def get_condition_registry(self) -> List[Dict[str, Any]]:
        """Return the list of all conditions with support counts.

        Only conditions whose support fraction >= ``min_support`` are
        included. Each entry is a dict with keys:
        ``feature``, ``bucket``, ``mask_ref``, ``support_count``.

        Returns
        -------
        list of dict
        """
        return [
            {
                "feature": rec.feature,
                "bucket": rec.bucket,
                "mask_ref": rec.mask_ref,
                "support_count": rec.support_count,
            }
            for rec in self._condition_registry_
        ]


# ===================================================================
# Module-level helpers
# ===================================================================


def _detect_domain(feature_name: str) -> Optional[str]:
    """Detect domain from a feature name by keyword matching.

    Returns the domain key (``"volatility"``, ``"regime"``, ``"momentum"``)
    or ``None`` when no keywords match.
    """
    name_lower = feature_name.lower()
    for keywords, domain, _ in _DOMAIN_MAP:
        if any(kw in name_lower for kw in keywords):
            return domain
    return None


def _get_schema(domain: str) -> Dict[str, Tuple[int, int]]:
    """Return the decile-range schema dict for the given domain key."""
    for _, d, schema in _DOMAIN_MAP:
        if d == domain:
            return schema
    raise ValueError(f"Unknown domain: '{domain}'")


def _compute_decile_masks(
    raw: np.ndarray,
    thresholds: np.ndarray,
    isnan: np.ndarray,
) -> List[np.ndarray]:
    """Build the 10 decile boolean masks from raw values and thresholds.

    Parameters
    ----------
    raw : np.ndarray
        Float feature values, shape ``(n,)``.
    thresholds : np.ndarray
        9 decile boundary values (10th .. 90th percentile).
    isnan : np.ndarray
        Boolean mask of NaN positions.

    Returns
    -------
    list of np.ndarray
        Ten boolean arrays, each of shape ``(n,)``, indexed 0 = d01 … 9 = d10.
    """
    n = len(raw)
    decile_masks: List[np.ndarray] = []
    prev = -np.inf

    for i, thresh in enumerate(thresholds):
        mask = (raw > prev) & (raw <= thresh)
        if i == 0:
            # Include values exactly equal to -inf in the first decile.
            mask = mask | (raw == prev)
        mask[isnan] = False
        decile_masks.append(mask)
        prev = thresh

    # d10 (above the 90th percentile threshold)
    d10 = (raw > thresholds[-1]) & (~isnan)
    decile_masks.append(d10)

    return decile_masks


def _split_mask_ref(mask_ref: str) -> Tuple[str, str]:
    """Split ``<feature>__<bucket>`` into a (feature, bucket) pair.

    The feature name may contain ``__`` internally, so only the last
    ``__``-separated token is treated as the bucket.
    """
    *feature_parts, bucket = mask_ref.rsplit("__", 1)
    feature = "__".join(feature_parts)
    return feature, bucket
