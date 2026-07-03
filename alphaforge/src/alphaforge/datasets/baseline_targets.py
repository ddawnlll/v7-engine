"""Baseline-normalized excess_net_R target computation.

Computes per-group baseline metrics and derives excess_net_R = net_R - baseline_mean.

Default grouping: mode + side + timeframe + atr_bucket + regime_bucket
Graceful degradation when grouping fields are missing.

Authority boundary:
  - simulation/ owns net_R truth
  - alphaforge/ owns baseline normalization for research purposes only
  - baseline normalization does NOT change simulation truth
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pyarrow as pa

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ATR bucket edges (percentile-based, computed from data)
# ---------------------------------------------------------------------------

_DEFAULT_ATR_BUCKET_EDGES = [25, 50, 75]  # percentiles → 4 buckets


def _compute_atr_buckets(
    atr_pct: np.ndarray, edges: List[float] = _DEFAULT_ATR_BUCKET_EDGES
) -> np.ndarray:
    """Map continuous atr_pct to bucket labels using percentile edges."""
    valid = atr_pct[~np.isnan(atr_pct)]
    if len(valid) < 10:
        return np.full(len(atr_pct), "mid", dtype="U10")

    percentiles = np.percentile(valid, edges)
    result = np.full(len(atr_pct), "mid", dtype="U10")
    result[atr_pct <= percentiles[0]] = "low"
    if len(percentiles) >= 2:
        result[(atr_pct > percentiles[0]) & (atr_pct <= percentiles[1])] = "mid_low"
        result[(atr_pct > percentiles[1]) & (atr_pct <= percentiles[2])] = "mid_high"
    result[atr_pct > percentiles[-1]] = "high"
    return result


# ---------------------------------------------------------------------------
# Regime bucket mapping
# ---------------------------------------------------------------------------

def _normalize_regime(regime: np.ndarray) -> np.ndarray:
    """Normalize regime labels to consistent buckets."""
    result = np.full(len(regime), "range", dtype="U10")
    for i, r in enumerate(regime):
        rs = str(r).lower().strip()
        if rs in ("up", "bullish", "trend_up"):
            result[i] = "up"
        elif rs in ("down", "bearish", "trend_down"):
            result[i] = "down"
        else:
            result[i] = "range"
    return result


# ---------------------------------------------------------------------------
# BaselineComputer
# ---------------------------------------------------------------------------

class BaselineComputer:
    """Computes baseline net_R per group and derives excess_net_R.

    Default grouping: mode + side + timeframe + atr_bucket + regime_bucket
    Gracefully degrades when fields are missing.

    Usage::

        computer = BaselineComputer()
        table = computer.compute(table)
        # table now has 'baseline_net_R_mean' and 'excess_net_R' columns
    """

    def __init__(
        self,
        grouping_fields: Optional[List[str]] = None,
        min_group_size: int = 10,
    ) -> None:
        self.grouping_fields = grouping_fields or [
            "mode", "side", "timeframe", "atr_bucket", "regime_bucket",
        ]
        self.min_group_size = min_group_size
        self._baseline_stats: Dict[str, Dict[str, float]] = {}

    def compute(self, table: pa.Table) -> pa.Table:
        """Add baseline_net_R_mean and excess_net_R columns to table.

        Args:
            table: CandidateOutcomeDataset v002 table with net_R column.

        Returns:
            Table with added baseline columns.
        """
        n = table.num_rows
        if n == 0:
            return table

        net_R = table.column("net_R").to_numpy().astype(float)

        # Ensure atr_bucket and regime_bucket exist
        table = self._ensure_buckets(table)

        # Compute group keys
        group_keys = self._compute_group_keys(table)

        # Compute baseline per group
        baseline_means = np.zeros(n, dtype=np.float64)
        self._baseline_stats.clear()

        unique_keys = set(group_keys)
        for key in unique_keys:
            mask = np.array([gk == key for gk in group_keys])
            group_net_R = net_R[mask]
            valid = group_net_R[~np.isnan(group_net_R)]

            if len(valid) >= self.min_group_size:
                mean_val = float(np.mean(valid))
            else:
                # Fallback to global mean for small groups
                valid_global = net_R[~np.isnan(net_R)]
                mean_val = float(np.mean(valid_global)) if len(valid_global) > 0 else 0.0

            baseline_means[mask] = mean_val
            self._baseline_stats[key] = {
                "baseline_mean_net_R": mean_val,
                "group_size": int(mask.sum()),
                "positive_rate": float(np.mean(valid > 0)) if len(valid) > 0 else 0.0,
            }

        # Compute excess_net_R
        excess_net_R = net_R - baseline_means

        # Add columns to table
        baseline_col = pa.array(baseline_means, type=pa.float64())
        excess_col = pa.array(excess_net_R, type=pa.float64())

        # Excess profit bucket
        excess_buckets = np.full(n, "at_baseline", dtype="U20")
        excess_buckets[excess_net_R <= -0.3] = "far_below_baseline"
        excess_buckets[(excess_net_R > -0.3) & (excess_net_R <= -0.05)] = "below_baseline"
        excess_buckets[(excess_net_R > -0.05) & (excess_net_R <= 0.05)] = "at_baseline"
        excess_buckets[(excess_net_R > 0.05) & (excess_net_R <= 0.3)] = "above_baseline"
        excess_buckets[excess_net_R > 0.3] = "far_above_baseline"
        excess_bucket_col = pa.array(excess_buckets, type=pa.string())

        # Add to table (replace if exists, otherwise add)
        if "baseline_net_R_mean" in table.column_names:
            table = table.drop(["baseline_net_R_mean"])
        if "excess_net_R" in table.column_names:
            table = table.drop(["excess_net_R"])
        if "excess_profit_bucket" in table.column_names:
            table = table.drop(["excess_profit_bucket"])

        table = table.append_column("baseline_net_R_mean", baseline_col)
        table = table.append_column("excess_net_R", excess_col)
        table = table.append_column("excess_profit_bucket", excess_bucket_col)

        logger.info(
            "Baseline computed: %d groups, global mean=%.4f",
            len(self._baseline_stats),
            float(np.mean(baseline_means)),
        )

        return table

    def _ensure_buckets(self, table: pa.Table) -> pa.Table:
        """Ensure atr_bucket and regime_bucket columns exist."""
        # ATR bucket
        if "atr_bucket" not in table.column_names:
            atr_pct = table.column("atr_pct").to_numpy().astype(float)
            atr_buckets = _compute_atr_buckets(atr_pct)
            table = table.append_column("atr_bucket", pa.array(atr_buckets, type=pa.string()))

        # Regime bucket
        if "regime_bucket" not in table.column_names:
            if "regime_trend" in table.column_names:
                regime = table.column("regime_trend").to_pylist()
                regime_arr = np.array(regime, dtype="U10")
                regime_buckets = _normalize_regime(regime_arr)
            else:
                regime_buckets = np.full(table.num_rows, "range", dtype="U10")
            table = table.append_column("regime_bucket", pa.array(regime_buckets, type=pa.string()))

        return table

    def _compute_group_keys(self, table: pa.Table) -> List[str]:
        """Compute group key strings for each row."""
        n = table.num_rows
        keys = []
        for i in range(n):
            parts = []
            for field_name in self.grouping_fields:
                if field_name in table.column_names:
                    val = str(table.column(field_name)[i].as_py())
                else:
                    val = "ANY"
                parts.append(f"{field_name}={val}")
            keys.append("|".join(parts))
        return keys

    def get_baseline_stats(self) -> Dict[str, Dict[str, float]]:
        """Return per-group baseline statistics."""
        return self._baseline_stats.copy()

    def get_missing_fields(self, table: pa.Table) -> List[str]:
        """Return grouping fields that are missing from the table."""
        return [f for f in self.grouping_fields if f not in table.column_names]
