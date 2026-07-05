"""Rule scoring engine — multi-dimensional evaluation of alpha candidates.

Computes a comprehensive scoring suite for rule-based strategies:

    Basic stats
        mean_net_R, median_net_R           NaN-safe central tendency
        positive_rate                       win rate
        lift_over_base                      mean_net_R / base_mean_net_R
        profit_factor                       sum(gain) / sum(|loss|)
        sharpe                              mean/std * sqrt(N)

    Stability
        symbol_stability                    per-symbol mean / std / cv
        regime_stability                    per-regime mean / std / cv

    Cost stress
        cost_stress                         fee 2x / 5x / 10x scenarios

Batch evaluation uses ``ThreadPoolExecutor`` for parallel scoring.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COST_STRESS_MULTIPLIERS: tuple = (2, 5, 10)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float:
    """Cast *value* to float, mapping NaN and inf to 0.0."""
    if isinstance(value, (float, int, np.floating, np.integer)):
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return 0.0
        return v
    return 0.0


def _safe_div(numerator: float, denominator: float) -> float:
    """Safe division returning 0.0 on zero denominator."""
    if abs(denominator) < 1e-12:
        return 0.0
    return numerator / denominator


def _resolve_mask(masks: Dict[str, np.ndarray]) -> np.ndarray:
    """Resolve the primary boolean mask from *masks*.

    Preference order: ``combined``, ``active``, ``long | short``,
    then the first boolean array found.
    """
    for key in ("combined", "active"):
        if key in masks:
            arr = masks[key]
            if arr.dtype == bool or arr.dtype == np.bool_:
                return arr

    # Union of long and short if both present
    long_mask = masks.get("long")
    short_mask = masks.get("short")
    if long_mask is not None and short_mask is not None:
        return long_mask | short_mask

    # Fallback: first boolean array
    for arr in masks.values():
        if isinstance(arr, np.ndarray) and (arr.dtype == bool or arr.dtype == np.bool_):
            return arr

    # Empty mask as last resort
    return np.zeros(0, dtype=bool)


def _resolve_masks_list(
    masks_list: List[Dict[str, np.ndarray]],
) -> List[np.ndarray]:
    """Resolve a list of mask dicts into a list of flat boolean arrays."""
    return [_resolve_mask(m) for m in masks_list]


# ---------------------------------------------------------------------------
# Per-symbol / per-regime helpers
# ---------------------------------------------------------------------------


def _clean_categorical(arr: np.ndarray) -> np.ndarray:
    """Convert a categorical array to string, replacing NaN/None with ``"NAN"``."""
    result = np.array(arr, dtype=str)
    nan_mask = np.array(
        [
            (isinstance(x, float) and np.isnan(x)) or x is None
            for x in arr
        ],
        dtype=bool,
    )
    if nan_mask.any():
        result = result.astype(str)
        result[nan_mask] = "NAN"
    return result


def _compute_symbol_metrics(
    net_R: np.ndarray, symbol_map: np.ndarray
) -> Dict[str, Any]:
    """Compute per-symbol mean, std, cv, and cross-symbol aggregation."""
    clean_map = _clean_categorical(symbol_map)
    unique_symbols = np.unique(clean_map)
    per_symbol: Dict[str, Dict[str, float]] = {}
    symbol_means: List[float] = []

    for sym in unique_symbols:
        sym_mask = symbol_map == sym
        sym_r = net_R[sym_mask]
        s_mean = float(np.nanmean(sym_r))
        s_std = float(np.nanstd(sym_r))
        s_cv = _safe_div(s_std, abs(s_mean)) if abs(s_mean) > 1e-12 else float("inf")
        per_symbol[str(sym)] = {
            "mean_net_R": _safe_float(s_mean),
            "std_net_R": _safe_float(s_std),
            "cv": _safe_float(s_cv),
            "count": int(np.sum(sym_mask)),
        }
        symbol_means.append(s_mean)

    mean_arr = np.array(symbol_means)
    cross_mean = float(np.nanmean(mean_arr)) if len(mean_arr) > 0 else 0.0
    cross_std = float(np.nanstd(mean_arr)) if len(mean_arr) > 1 else 0.0
    cross_cv = _safe_div(cross_std, abs(cross_mean)) if abs(cross_mean) > 1e-12 else float("inf")

    return {
        "per_symbol": per_symbol,
        "cross_symbol_mean": _safe_float(cross_mean),
        "cross_symbol_std": _safe_float(cross_std),
        "cross_symbol_cv": _safe_float(cross_cv),
    }


def _compute_regime_metrics(
    net_R: np.ndarray, regime_map: np.ndarray
) -> Dict[str, Any]:
    """Compute per-regime mean, std, cv, and cross-regime aggregation."""
    clean_map = _clean_categorical(regime_map)
    unique_regimes = np.unique(clean_map)
    per_regime: Dict[str, Dict[str, float]] = {}
    regime_means: List[float] = []

    for regime in unique_regimes:
        r_mask = clean_map == regime
        r_r = net_R[r_mask]
        r_mean = float(np.nanmean(r_r))
        r_std = float(np.nanstd(r_r))
        r_cv = _safe_div(r_std, abs(r_mean)) if abs(r_mean) > 1e-12 else float("inf")
        per_regime[str(regime)] = {
            "mean_net_R": _safe_float(r_mean),
            "std_net_R": _safe_float(r_std),
            "cv": _safe_float(r_cv),
            "count": int(np.sum(r_mask)),
        }
        regime_means.append(r_mean)

    mean_arr = np.array(regime_means)
    cross_mean = float(np.nanmean(mean_arr)) if len(mean_arr) > 0 else 0.0
    cross_std = float(np.nanstd(mean_arr)) if len(mean_arr) > 1 else 0.0
    cross_cv = _safe_div(cross_std, abs(cross_mean)) if abs(cross_mean) > 1e-12 else float("inf")

    return {
        "per_regime": per_regime,
        "cross_regime_mean": _safe_float(cross_mean),
        "cross_regime_std": _safe_float(cross_std),
        "cross_regime_cv": _safe_float(cross_cv),
    }


def _compute_cost_stress(
    net_R: np.ndarray,
    fee_r: float,
    multipliers: tuple = _COST_STRESS_MULTIPLIERS,
) -> Dict[str, Any]:
    """Apply fee multipliers and recompute mean net R.

    Each stressed scenario subtracts additional fee from every observation:

        stressed_r = net_R - fee_r * (mult - 1)

    Returns the baseline mean, stressed means, and survival flags.
    """
    baseline_mean = float(np.nanmean(net_R))
    scenarios: Dict[str, Dict[str, float | bool]] = {}

    for mult in multipliers:
        extra_fee = fee_r * (mult - 1)
        stressed_r = net_R - extra_fee
        stressed_mean = float(np.nanmean(stressed_r))
        scenarios[f"fee_{mult}x"] = {
            "mean_net_R": _safe_float(stressed_mean),
            "mean_change": _safe_float(stressed_mean - baseline_mean),
            "edge_survives": bool(stressed_mean > 0),
        }

    return {
        "baseline_mean_net_R": _safe_float(baseline_mean),
        "fee_r": fee_r,
        "scenarios": scenarios,
    }


def _empty_score_dict(rule: Optional[Dict] = None) -> Dict[str, Any]:
    """Return a zero-filled score dict for empty/inactive rules."""
    result: Dict[str, Any] = {
        "mean_net_R": 0.0,
        "median_net_R": 0.0,
        "positive_rate": 0.0,
        "lift_over_base": 0.0,
        "profit_factor": 0.0,
        "sharpe": 0.0,
        "symbol_stability": {
            "per_symbol": {},
            "cross_symbol_mean": 0.0,
            "cross_symbol_std": 0.0,
            "cross_symbol_cv": 0.0,
        },
        "regime_stability": {
            "per_regime": {},
            "cross_regime_mean": 0.0,
            "cross_regime_std": 0.0,
            "cross_regime_cv": 0.0,
        },
        "cost_stress": {
            "baseline_mean_net_R": 0.0,
            "fee_r": 0.0,
            "scenarios": {
                f"fee_{m}x": {
                    "mean_net_R": 0.0,
                    "mean_change": 0.0,
                    "edge_survives": False,
                }
                for m in _COST_STRESS_MULTIPLIERS
            },
        },
        "n_observations": 0,
    }
    if rule is not None:
        result["rule_id"] = rule.get("id", rule.get("name", ""))
    return result


# ===========================================================================
# RuleScorer
# ===========================================================================


class RuleScorer:
    """Multi-dimensional rule scoring engine.

    Usage::

        scorer = RuleScorer()
        result = scorer.score(
            rule={"id": "r1", "feature": "rsi", "operator": ">", "threshold": 70},
            masks={"active": boolean_mask},
            target=r_multiple_array,
            symbol_map=symbol_id_array,
            regime_map=regime_label_array,
        )
    """

    # ------------------------------------------------------------------
    # Single rule scoring
    # ------------------------------------------------------------------

    def score(
        self,
        rule: Dict[str, Any],
        masks: Dict[str, np.ndarray],
        target: np.ndarray,
        symbol_map: np.ndarray,
        regime_map: np.ndarray,
        base_mean_net_R: Optional[float] = None,
        fee_r: float = 0.0,
    ) -> Dict[str, Any]:
        """Compute the full scoring suite for a single rule.

        Args:
            rule:
                Rule metadata dict (``id`` or ``name`` used for identification).
            masks:
                Dict of boolean arrays. ``combined``, ``active``, or the union
                of ``long`` + ``short`` is used as the primary mask.
            target:
                1-D array of R-multiple values for every observation.
            symbol_map:
                1-D array of symbol identifiers per observation (ints or strings).
            regime_map:
                1-D array of regime labels per observation (ints or strings).
            base_mean_net_R:
                Baseline mean net R (all observations, unfiltered).  When
                ``None``, computed from the full *target* array.
            fee_r:
                Per-trade baseline fee in R-units for cost stress scenarios.

        Returns:
            Dict with keys:
                mean_net_R, median_net_R, positive_rate, lift_over_base,
                profit_factor, sharpe, symbol_stability, regime_stability,
                cost_stress, n_observations, rule_id.
        """
        mask = _resolve_mask(masks)
        n_active = int(np.sum(mask))

        if n_active == 0:
            return _empty_score_dict(rule)

        net_R = target[mask]

        # --- Central tendency (NaN-safe) ---
        mean_r = float(np.nanmean(net_R))
        median_r = float(np.nanmedian(net_R))

        # --- Positive rate ---
        positive_rate = float(np.mean(net_R > 0))

        # --- Lift over base ---
        if base_mean_net_R is None:
            base_mean_net_R = float(np.nanmean(target))
        lift = _safe_div(mean_r, base_mean_net_R)

        # --- Profit factor ---
        gains = net_R[net_R > 0]
        losses = net_R[net_R < 0]
        sum_gains = float(np.sum(gains))
        sum_losses = abs(float(np.sum(losses)))
        profit_factor = _safe_div(sum_gains, sum_losses)

        # --- Sharpe (observation-level) ---
        std_r = float(np.nanstd(net_R))
        n_obs = len(net_R)
        sharpe = _safe_div(mean_r, std_r) * math.sqrt(n_obs) if std_r > 0 else 0.0

        # --- Symbol stability ---
        sym_mask = np.array([i < len(symbol_map) for i in range(len(target))])
        symbol_stability = _compute_symbol_metrics(net_R, symbol_map[mask])

        # --- Regime stability ---
        regime_stability = _compute_regime_metrics(net_R, regime_map[mask])

        # --- Cost stress ---
        cost_stress = _compute_cost_stress(net_R, fee_r)

        return {
            "mean_net_R": _safe_float(mean_r),
            "median_net_R": _safe_float(median_r),
            "positive_rate": _safe_float(positive_rate),
            "lift_over_base": _safe_float(lift),
            "profit_factor": _safe_float(profit_factor),
            "sharpe": _safe_float(sharpe),
            "symbol_stability": symbol_stability,
            "regime_stability": regime_stability,
            "cost_stress": cost_stress,
            "n_observations": n_active,
            "rule_id": rule.get("id", rule.get("name", "")),
        }

    # ------------------------------------------------------------------
    # Batch scoring (parallel)
    # ------------------------------------------------------------------

    def score_batch(
        self,
        rules: List[Dict[str, Any]],
        masks_list: List[Dict[str, np.ndarray]],
        target: np.ndarray,
        symbol_map: np.ndarray,
        regime_map: np.ndarray,
        base_mean_net_R: Optional[float] = None,
        fee_r: float = 0.0,
        max_workers: int = 8,
    ) -> List[Dict[str, Any]]:
        """Score multiple rules in parallel with ``ThreadPoolExecutor``.

        Args:
            rules:
                List of rule metadata dicts, one per candidate.
            masks_list:
                List of mask dicts, one per rule (same length as *rules*).
            target:
                1-D array of R-multiple values.
            symbol_map:
                1-D array of symbol identifiers.
            regime_map:
                1-D array of regime labels.
            base_mean_net_R:
                Baseline mean net R (shared across all rules).
            fee_r:
                Per-trade baseline fee in R-units.
            max_workers:
                Maximum parallel workers (default 8).

        Returns:
            List of score dicts in the same order as *rules*.
        """
        if len(rules) != len(masks_list):
            raise ValueError(
                f"Length mismatch: {len(rules)} rules vs {len(masks_list)} masks"
            )

        # Pre-resolve all masks on the main thread to avoid GIL contention
        # on the dict-resolve logic (which is cheap but involves Python objects).
        resolved_masks = _resolve_masks_list(masks_list)

        n_candidates = len(rules)
        workers = min(max_workers, n_candidates, 32)  # cap at 32

        if workers <= 1:
            return [
                self._score_single(
                    rule, resolved_masks[i], target, symbol_map, regime_map,
                    base_mean_net_R, fee_r,
                )
                for i, rule in enumerate(rules)
            ]

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    self._score_single,
                    rule,
                    resolved_masks[i],
                    target,
                    symbol_map,
                    regime_map,
                    base_mean_net_R,
                    fee_r,
                )
                for i, rule in enumerate(rules)
            ]
            return [f.result() for f in futures]

    # ------------------------------------------------------------------
    # Internal: single rule with pre-resolved flat mask
    # ------------------------------------------------------------------

    @staticmethod
    def _score_single(
        rule: Dict[str, Any],
        mask: np.ndarray,
        target: np.ndarray,
        symbol_map: np.ndarray,
        regime_map: np.ndarray,
        base_mean_net_R: Optional[float],
        fee_r: float,
    ) -> Dict[str, Any]:
        """Score a single rule given a pre-resolved flat boolean mask.

        This is the inner compute kernel shared by ``score`` and
        ``score_batch``.
        """
        n_active = int(np.sum(mask))

        if n_active == 0:
            return _empty_score_dict(rule)

        net_R = target[mask]

        # Central tendency
        mean_r = float(np.nanmean(net_R))
        median_r = float(np.nanmedian(net_R))

        # Positive rate
        positive_rate = float(np.mean(net_R > 0))

        # Lift
        if base_mean_net_R is None:
            base_mean_net_R = float(np.nanmean(target))
        lift = _safe_div(mean_r, base_mean_net_R)

        # Profit factor
        gains = net_R[net_R > 0]
        losses = net_R[net_R < 0]
        sum_gains = float(np.sum(gains))
        sum_losses = abs(float(np.sum(losses)))
        profit_factor = _safe_div(sum_gains, sum_losses)

        # Sharpe
        std_r = float(np.nanstd(net_R))
        n_obs = len(net_R)
        sharpe = _safe_div(mean_r, std_r) * math.sqrt(n_obs) if std_r > 0 else 0.0

        # Stability
        symbol_stability = _compute_symbol_metrics(net_R, symbol_map[mask])
        regime_stability = _compute_regime_metrics(net_R, regime_map[mask])

        # Cost stress
        cost_stress = _compute_cost_stress(net_R, fee_r)

        return {
            "mean_net_R": _safe_float(mean_r),
            "median_net_R": _safe_float(median_r),
            "positive_rate": _safe_float(positive_rate),
            "lift_over_base": _safe_float(lift),
            "profit_factor": _safe_float(profit_factor),
            "sharpe": _safe_float(sharpe),
            "symbol_stability": symbol_stability,
            "regime_stability": regime_stability,
            "cost_stress": cost_stress,
            "n_observations": n_active,
            "rule_id": rule.get("id", rule.get("name", "")),
        }
