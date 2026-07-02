"""Bitset-based exhaustive condition mining engine.

Evaluates boolean mask bitsets at three levels of combination
complexity to discover profitable trading conditions:

Level 1 — Atomic conditions: evaluate each mask independently.
Level 2 — Pairwise AND combinations accelerated with Numba JIT.
Level 3 — Beam search: extend best pairs with a third condition.

Usage
-----
    engine = BitsetEngine(min_support=0.02)
    l1 = engine.level1_scan(masks, target)
    l2 = engine.level2_scan(masks, target, top_n=5000)
    l3 = engine.level3_scan(l2, masks, target, beam_width=100)
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Numba JIT — optional acceleration for Level 2 pairwise scan
# ---------------------------------------------------------------------------

_HAS_NUMBA = False
try:
    from numba import njit, prange

    _HAS_NUMBA = True
except ImportError:

    def njit(*args, **kwargs):  # type: ignore[misc]
        """No-op decorator when Numba is not installed."""
        if args and callable(args[0]):
            return args[0]
        return lambda f: f

    prange = range  # type: ignore[assignment]


if _HAS_NUMBA:

    @njit(parallel=True)
    def _level2_compute_numba(
        masks_arr: np.ndarray,
        target: np.ndarray,
        pairs: np.ndarray,
        out_support: np.ndarray,
        out_mean_r: np.ndarray,
        out_win_rate: np.ndarray,
        out_ic: np.ndarray,
    ) -> None:
        """Numba-accelerated parallel computation of pair metrics.

        Parameters
        ----------
        masks_arr : np.ndarray
            Boolean array of shape ``(n_masks, n_samples)``.
        target : np.ndarray
            Float array of shape ``(n_samples,)``; may contain NaN.
        pairs : np.ndarray
            Int64 array of shape ``(n_pairs, 2)`` with mask indices.
        out_support : np.ndarray
            Output — integer support counts per pair, shape ``(n_pairs,)``.
        out_mean_r : np.ndarray
            Output — mean target value per pair, shape ``(n_pairs,)``.
        out_win_rate : np.ndarray
            Output — win fraction per pair, shape ``(n_pairs,)``.
        out_ic : np.ndarray
            Output — Pearson IC per pair, shape ``(n_pairs,)``.
        """
        n_pairs = pairs.shape[0]
        n_samples = target.shape[0]

        for p in prange(n_pairs):
            i = pairs[p, 0]
            j = pairs[p, 1]

            support = 0
            r_sum = 0.0
            r_count = 0
            win_count = 0

            # Pearson correlation accumulators (mask indicator vs target)
            sx = 0.0
            sy = 0.0
            sxy = 0.0
            sxx = 0.0
            syy = 0.0
            ic_n = 0

            for k in range(n_samples):
                in_mask = masks_arr[i, k] and masks_arr[j, k]
                t = target[k]
                valid = not np.isnan(t)

                if in_mask:
                    support += 1
                    if valid:
                        r_sum += t
                        r_count += 1
                        if t > 0.0:
                            win_count += 1

                if valid:
                    xv = 1.0 if in_mask else 0.0
                    sx += xv
                    sy += t
                    sxy += xv * t
                    sxx += xv * xv
                    syy += t * t
                    ic_n += 1

            out_support[p] = support

            if r_count > 0:
                out_mean_r[p] = r_sum / r_count
                out_win_rate[p] = win_count / r_count

            if ic_n > 2:
                mx = sx / ic_n
                my = sy / ic_n
                cov = sxy / ic_n - mx * my
                vx = sxx / ic_n - mx * mx
                vy = syy / ic_n - my * my
                d1 = math.sqrt(vx) if vx > 0.0 else 0.0
                d2 = math.sqrt(vy) if vy > 0.0 else 0.0
                denom = d1 * d2
                if denom > 0.0:
                    out_ic[p] = cov / denom


def _level2_compute_fallback(
    masks_arr: np.ndarray,
    target: np.ndarray,
    pairs: np.ndarray,
    out_support: np.ndarray,
    out_mean_r: np.ndarray,
    out_win_rate: np.ndarray,
    out_ic: np.ndarray,
) -> None:
    """Pure-NumPy fallback for Level 2 scan (Numba unavailable)."""
    n_pairs = pairs.shape[0]
    for p in range(n_pairs):
        i = pairs[p, 0]
        j = pairs[p, 1]

        combined = masks_arr[i] & masks_arr[j]
        support = int(combined.sum())
        out_support[p] = support

        if support > 0:
            mt = target[combined]
            valid = mt[~np.isnan(mt)]
            if len(valid) > 0:
                out_mean_r[p] = float(np.mean(valid))
                out_win_rate[p] = float(np.mean(valid > 0.0))

        # IC: Pearson correlation between binary mask and target
        mask_01 = combined.astype(np.float64)
        valid_mask = ~np.isnan(target)
        if valid_mask.sum() > 2:
            x = mask_01[valid_mask]
            y = target[valid_mask]
            c = np.corrcoef(x, y)
            out_ic[p] = float(c[0, 1])


# ---------------------------------------------------------------------------
# BitsetEngine
# ---------------------------------------------------------------------------


class BitsetEngine:
    """Exhaustive condition mining over boolean mask bitsets.

    Parameters
    ----------
    min_support : float, default ``0.01``
        Minimum support fraction (0 .. 1). Conditions or combinations
        whose support falls below this threshold are excluded from results.
    """

    def __init__(self, min_support: float = 0.01) -> None:
        if not 0.0 <= min_support <= 1.0:
            raise ValueError(
                f"min_support must be in [0, 1], got {min_support}"
            )
        self.min_support = min_support

    # ------------------------------------------------------------------
    # Level 1 — atomic conditions
    # ------------------------------------------------------------------

    def level1_scan(
        self,
        masks: Dict[str, np.ndarray],
        target: np.ndarray,
    ) -> List[Dict[str, Any]]:
        """Evaluate each atomic condition independently.

        For every mask in ``masks``, computes:

        - **support** — number of samples where mask is True.
        - **mean_net_R** — mean target value over the masked region
          (NaN-safe).
        - **win_rate** — fraction of masked values > 0 (NaN-safe).
        - **lift** — ``mean_net_R / target.mean()``.

        Results are filtered by ``min_support`` and sorted by
        ``mean_net_R`` descending.

        Parameters
        ----------
        masks : dict of str -> np.ndarray
            Boolean arrays of shape ``(n_samples,)``.
        target : np.ndarray
            Float array of shape ``(n_samples,)``; may contain NaN.

        Returns
        -------
        list of dict
            Each entry has keys ``conditions``, ``support``,
            ``support_frac``, ``mean_net_R``, ``win_rate``, ``lift``.
        """
        _validate_input(masks, target)

        n = len(target)
        target_mean = _safe_mean(target)
        min_support_abs = _min_count(n, self.min_support)

        if np.isnan(target_mean):
            return []

        results: List[Dict[str, Any]] = []
        for name, mask in masks.items():
            support = int(mask.sum())
            if support < min_support_abs:
                continue

            valid = _extract_valid(target, mask)
            if len(valid) == 0:
                continue

            mean_r = float(np.mean(valid))
            wr = float(np.mean(valid > 0.0))
            lift = mean_r / target_mean if target_mean != 0.0 else 0.0

            results.append(
                {
                    "conditions": [name],
                    "support": support,
                    "support_frac": support / n,
                    "mean_net_R": mean_r,
                    "win_rate": wr,
                    "lift": lift,
                }
            )

        results.sort(key=lambda r: r["mean_net_R"], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Level 2 — pairwise AND combinations
    # ------------------------------------------------------------------

    def level2_scan(
        self,
        masks: Dict[str, np.ndarray],
        target: np.ndarray,
        top_n: int = 5000,
    ) -> List[Dict[str, Any]]:
        """Evaluate all pairwise AND combinations.

        Computes the same metrics as Level 1 plus **IC** (Pearson
        correlation between the binary combination indicator and the
        target). Uses Numba JIT with a ``prange`` parallel loop when
        available; falls back to pure NumPy otherwise.

        Parameters
        ----------
        masks : dict of str -> np.ndarray
            Boolean arrays of shape ``(n_samples,)``.
        target : np.ndarray
            Float array of shape ``(n_samples,)``; may contain NaN.
        top_n : int, default ``5000``
            Maximum number of top-scoring pairs to return.

        Returns
        -------
        list of dict
            Each entry adds key ``ic`` to the Level 1 schema.
        """
        _validate_input(masks, target)

        n = len(target)
        target_mean = _safe_mean(target)
        min_support_abs = _min_count(n, self.min_support)

        mask_names = list(masks.keys())
        n_masks = len(mask_names)

        if n_masks < 2 or np.isnan(target_mean):
            return []

        # -- Build 2D mask array and pair index array ------------------
        n_pairs = n_masks * (n_masks - 1) // 2
        masks_arr = np.stack([masks[name] for name in mask_names], axis=0)

        pairs = np.zeros((n_pairs, 2), dtype=np.int64)
        idx = 0
        for i in range(n_masks):
            for j in range(i + 1, n_masks):
                pairs[idx, 0] = i
                pairs[idx, 1] = j
                idx += 1

        # -- Output arrays ---------------------------------------------
        out_support = np.zeros(n_pairs, dtype=np.int64)
        out_mean_r = np.full(n_pairs, np.nan, dtype=np.float64)
        out_win_rate = np.full(n_pairs, np.nan, dtype=np.float64)
        out_ic = np.full(n_pairs, np.nan, dtype=np.float64)

        compute_fn = (
            _level2_compute_numba if _HAS_NUMBA else _level2_compute_fallback
        )
        compute_fn(
            masks_arr, target, pairs,
            out_support, out_mean_r, out_win_rate, out_ic,
        )

        # -- Assemble results -------------------------------------------
        results: List[Dict[str, Any]] = []
        for p in range(n_pairs):
            sup = out_support[p]
            if sup < min_support_abs:
                continue
            mr = out_mean_r[p]
            if np.isnan(mr):
                continue

            i, j = int(pairs[p, 0]), int(pairs[p, 1])
            lift = mr / target_mean if target_mean != 0.0 else 0.0
            ic_val = float(out_ic[p]) if not np.isnan(out_ic[p]) else 0.0

            results.append(
                {
                    "conditions": [mask_names[i], mask_names[j]],
                    "support": int(sup),
                    "support_frac": sup / n,
                    "mean_net_R": float(mr),
                    "win_rate": float(out_win_rate[p]),
                    "lift": lift,
                    "ic": ic_val,
                }
            )

        results.sort(key=lambda r: r["mean_net_R"], reverse=True)
        return results[:top_n]

    # ------------------------------------------------------------------
    # Level 3 — beam search for triple combinations
    # ------------------------------------------------------------------

    def level3_scan(
        self,
        level2_results: List[Dict[str, Any]],
        masks: Dict[str, np.ndarray],
        target: np.ndarray,
        beam_width: int = 100,
    ) -> List[Dict[str, Any]]:
        """Beam search: extend best Level-2 pairs with a third condition.

        For each of the top ``beam_width`` pairs from ``level2_results``,
        enumerates every remaining condition (not already in the pair).
        A triple is kept **only** when its ``mean_net_R`` strictly
        exceeds the pair's ``mean_net_R``.

        Parameters
        ----------
        level2_results : list of dict
            Results from ``level2_scan()``; used as the beam seed set.
        masks : dict of str -> np.ndarray
            Boolean arrays of shape ``(n_samples,)``.
        target : np.ndarray
            Float array of shape ``(n_samples,)``; may contain NaN.
        beam_width : int, default ``100``
            Number of top pairs to extend.

        Returns
        -------
        list of dict
            Each entry adds key ``improvement`` (delta mean_net_R over
            the source pair) to the Level 2 schema.
        """
        _validate_input(masks, target)

        if not level2_results:
            return []

        n = len(target)
        target_mean = _safe_mean(target)
        min_support_abs = _min_count(n, self.min_support)

        if np.isnan(target_mean):
            return []

        candidates = level2_results[:beam_width]
        mask_names = list(masks.keys())

        results: List[Dict[str, Any]] = []
        for candidate in candidates:
            base_conds = candidate["conditions"]
            base_mean_r = candidate["mean_net_R"]

            base_mask = masks[base_conds[0]] & masks[base_conds[1]]

            for name in mask_names:
                if name in base_conds:
                    continue

                combined = base_mask & masks[name]
                support = int(combined.sum())
                if support < min_support_abs:
                    continue

                valid = _extract_valid(target, combined)
                if len(valid) == 0:
                    continue

                mean_r = float(np.mean(valid))
                if mean_r <= base_mean_r:
                    continue

                wr = float(np.mean(valid > 0.0))
                lift = mean_r / target_mean if target_mean != 0.0 else 0.0

                results.append(
                    {
                        "conditions": base_conds + [name],
                        "support": support,
                        "support_frac": support / n,
                        "mean_net_R": mean_r,
                        "win_rate": wr,
                        "lift": lift,
                        "improvement": mean_r - base_mean_r,
                    }
                )

        results.sort(key=lambda r: r["mean_net_R"], reverse=True)
        return results


# ===================================================================
# Module-level helpers
# ===================================================================


def _validate_input(
    masks: Dict[str, np.ndarray],
    target: np.ndarray,
) -> None:
    """Validate mask shapes and dtypes; does nothing on empty masks."""
    if not masks:
        return
    n = len(target)
    if n == 0:
        return
    for name, mask in masks.items():
        if mask.shape != (n,):
            raise ValueError(
                f"Mask '{name}' has shape {mask.shape}, expected ({n},)"
            )
        if mask.dtype != bool:
            raise ValueError(
                f"Mask '{name}' has dtype {mask.dtype}, expected bool"
            )


def _safe_mean(arr: np.ndarray) -> float:
    """NaN-safe mean returning NaN when no valid values exist."""
    if len(arr) == 0:
        return float("nan")
    return float(np.nanmean(arr))


def _min_count(n: int, min_support: float) -> int:
    """Convert fractional min_support to absolute count (ceil)."""
    if min_support <= 0.0:
        return 0
    return max(1, int(np.ceil(min_support * n)))


def _extract_valid(target: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return target values at mask positions that are not NaN."""
    selected = target[mask]
    return selected[~np.isnan(selected)]
