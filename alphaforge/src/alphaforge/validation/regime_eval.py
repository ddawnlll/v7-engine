"""RegimeEvaluator — per-regime performance breakdown for WFV fold results.

Groups walk-forward validation fold results by market regime label,
computes per-regime aggregate metrics (expectancy_r, win_rate, trade_count),
and flags dangerous patterns like catastrophic loss concentrated in a single
regime or edge that exists only in rare regimes.

Depends on: #78 (regime detection via alphaforge.features.regime).
Interface contract: accepts a Dict[int, RegimeLabel] mapping fold indices to
their regime labels. The caller owns regime detection; this module owns
aggregation and flag logic.

This module imports ZERO ML libraries.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from alphaforge.validation.contracts import RegimeLabel


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# expectancy_r below this in a regime that is not shared by other regimes
# is flagged as "catastrophic loss in single regime"
CATASTROPHIC_LOSS_EXPECTANCY_R_THRESHOLD: float = -0.5

# A regime present in fewer than this fraction of total folds is "rare"
RARE_REGIME_FOLD_FRACTION: float = 0.15

# Minimum number of folds across ALL regimes before any flag fires
MIN_TOTAL_FOLDS_FOR_FLAGS: int = 4


# ---------------------------------------------------------------------------
# RegimeEvaluator
# ---------------------------------------------------------------------------


class RegimeEvaluator:
    """Groups WFV fold results by regime and computes per-regime performance.

    Constructor:
        fold_regime_map: Dict mapping fold_index (int) to its RegimeLabel.

    evaluate():
        Takes parallel dicts of per-fold metrics (expectancy_r, win_rate,
        trade_count) and returns a regime_breakdown dict suitable for
        ModeResearchReport.

    Catastrophic loss detection:
        If any single regime has mean expectancy_r below
        CATASTROPHIC_LOSS_EXPECTANCY_R_THRESHOLD while all other regimes are
        above that threshold, the "catastrophic_loss_in_single_regime" flag
        fires.

    Edge-only-in-rare-regime detection:
        If positive edge (expectancy_r > 0) exists ONLY in regime(s) that
        each account for less than RARE_REGIME_FOLD_FRACTION of total folds,
        the "edge_only_in_rare_regime" flag fires.
    """

    def __init__(self, fold_regime_map: Dict[int, RegimeLabel]) -> None:
        """Initialize with fold-to-regime mapping.

        Args:
            fold_regime_map: Dict[int, RegimeLabel] mapping each fold index
                             to its market regime classification.  Missing
                             folds are silently skipped during evaluation.
        """
        if not isinstance(fold_regime_map, dict):
            raise TypeError(
                f"fold_regime_map must be a dict, got {type(fold_regime_map).__name__}"
            )
        self._fold_regime_map: Dict[int, RegimeLabel] = dict(fold_regime_map)

    @property
    def fold_regime_map(self) -> Dict[int, RegimeLabel]:
        """Return a copy of the fold -> regime mapping."""
        return dict(self._fold_regime_map)

    # ------------------------------------------------------------------
    # evaluate()
    # ------------------------------------------------------------------

    def evaluate(
        self,
        fold_expectancy_r: Dict[int, float],
        fold_win_rate: Dict[int, float],
        fold_trade_count: Dict[int, int],
    ) -> Dict[str, Any]:
        """Compute per-regime aggregate metrics and flags.

        Args:
            fold_expectancy_r: Dict[fold_index, expectancy_r (float)].
            fold_win_rate: Dict[fold_index, win_rate (float)].
            fold_trade_count: Dict[fold_index, trade_count (int)].

        Returns:
            Dict with keys:
                regimes: Dict[RegimeLabel, per-regime metrics dict].
                edge_only_in_rare_regime: bool.
                rare_regime_untradeable: bool.
                catastrophic_loss_in_single_regime: bool.
                catastrophic_loss_regime: Optional[str] — which regime.
                total_folds_evaluated: int.
                folds_per_regime: Dict[str, int].
        """
        # Collect the intersection of fold indices present in all inputs
        fold_ids = (
            set(self._fold_regime_map.keys())
            & set(fold_expectancy_r.keys())
            & set(fold_win_rate.keys())
            & set(fold_trade_count.keys())
        )

        if not fold_ids:
            return _empty_breakdown()

        # Group metric values by regime
        groups: Dict[RegimeLabel, List[Dict[str, float]]] = {
            r: [] for r in RegimeLabel
        }

        for fid in sorted(fold_ids):
            rlabel = self._fold_regime_map[fid]
            groups[rlabel].append({
                "expectancy_r": float(fold_expectancy_r[fid]),
                "win_rate": float(fold_win_rate[fid]),
                "trade_count": int(fold_trade_count[fid]),
            })

        # Compute per-regime aggregates
        regimes: Dict[str, Dict[str, Any]] = {}
        folds_per_regime: Dict[str, int] = {}

        for rlabel in RegimeLabel:
            entries = groups[rlabel]
            folds_per_regime[rlabel.value] = len(entries)

            if not entries:
                regimes[rlabel.value] = {
                    "expectancy_r": None,
                    "win_rate": None,
                    "trade_count": 0,
                    "fold_count": 0,
                }
                continue

            n = len(entries)
            exp_values = [e["expectancy_r"] for e in entries]
            wr_values = [e["win_rate"] for e in entries]
            tc_values = [e["trade_count"] for e in entries]

            mean_exp = _safe_mean(exp_values)
            mean_wr = _safe_mean(wr_values)
            total_tc = sum(tc_values)

            regimes[rlabel.value] = {
                "expectancy_r": mean_exp,
                "win_rate": mean_wr,
                "trade_count": total_tc,
                "fold_count": n,
            }

        total_folds = len(fold_ids)

        # Detect catastrophic loss in a single regime
        cat_loss_flag, cat_loss_regime = _detect_catastrophic_loss(
            regimes, total_folds
        )

        # Detect edge only in rare regime
        edge_rare, rare_untradeable = _detect_edge_in_rare_regime(
            regimes, total_folds
        )

        return {
            "regimes": regimes,
            "edge_only_in_rare_regime": edge_rare,
            "rare_regime_untradeable": rare_untradeable,
            "catastrophic_loss_in_single_regime": cat_loss_flag,
            "catastrophic_loss_regime": cat_loss_regime,
            "total_folds_evaluated": total_folds,
            "folds_per_regime": folds_per_regime,
        }


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def _detect_catastrophic_loss(
    regimes: Dict[str, Dict[str, Any]],
    total_folds: int,
) -> tuple:
    """Detect if one regime has catastrophic loss while others are fine.

    A regime is "catastrophic" if its mean expectancy_r is below
    CATASTROPHIC_LOSS_EXPECTANCY_R_THRESHOLD while every other regime
    with data has expectancy_r above that threshold.

    Returns (flag: bool, regime_name: Optional[str]).
    """
    if total_folds < MIN_TOTAL_FOLDS_FOR_FLAGS:
        return False, None

    regimes_with_data = {
        name: data
        for name, data in regimes.items()
        if data["expectancy_r"] is not None
    }

    if len(regimes_with_data) < 2:
        # Need at least 2 regimes to compare
        return False, None

    below_threshold: List[str] = []
    above_threshold: List[str] = []

    for name, data in regimes_with_data.items():
        exp = data["expectancy_r"]
        if exp is None:
            continue
        if exp < CATASTROPHIC_LOSS_EXPECTANCY_R_THRESHOLD:
            below_threshold.append(name)
        else:
            above_threshold.append(name)

    # Catastrophic: exactly one regime below threshold, all others above
    if len(below_threshold) == 1 and len(above_threshold) >= 1:
        return True, below_threshold[0]

    return False, None


def _detect_edge_in_rare_regime(
    regimes: Dict[str, Dict[str, Any]],
    total_folds: int,
) -> tuple:
    """Detect if positive edge exists only in rare regime(s).

    A regime is "rare" if it accounts for less than RARE_REGIME_FOLD_FRACTION
    of total folds.  "Positive edge" means expectancy_r > 0.

    Returns (edge_only_in_rare_regime: bool, rare_regime_untradeable: bool).
    """
    if total_folds < MIN_TOTAL_FOLDS_FOR_FLAGS:
        return False, False

    regimes_with_data = {
        name: data
        for name, data in regimes.items()
        if data["expectancy_r"] is not None
    }

    if len(regimes_with_data) < 2:
        return False, False

    positive_regimes: List[str] = []
    non_positive_regimes: List[str] = []
    rare_regimes: List[str] = []

    rare_threshold_folds = int(total_folds * RARE_REGIME_FOLD_FRACTION)

    for name, data in regimes_with_data.items():
        fold_count = data.get("fold_count", 0)
        exp = data["expectancy_r"]

        if fold_count <= rare_threshold_folds and fold_count > 0:
            rare_regimes.append(name)

        if exp is not None and exp > 0:
            positive_regimes.append(name)
        else:
            non_positive_regimes.append(name)

    # Edge only in rare regime: ALL positive regimes are rare
    edge_only_in_rare = False
    if positive_regimes and non_positive_regimes:
        # There is at least one regime with edge and one without
        all_positive_are_rare = all(r in rare_regimes for r in positive_regimes)
        edge_only_in_rare = all_positive_are_rare

    # Rare regime untradeable: at least one rare regime has negative edge
    rare_untradeable = any(
        data["expectancy_r"] is not None and data["expectancy_r"] <= 0
        for name, data in regimes_with_data.items()
        if name in rare_regimes
    )

    return edge_only_in_rare, rare_untradeable


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _safe_mean(values: List[float]) -> Optional[float]:
    """Compute mean of a list of floats, returning None for empty lists.

    Filters out NaN and Inf values.
    """
    clean = [v for v in values if not math.isnan(v) and not math.isinf(v)]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _empty_breakdown() -> Dict[str, Any]:
    """Return an empty breakdown dict when no fold data is available."""
    regimes = {
        r.value: {
            "expectancy_r": None,
            "win_rate": None,
            "trade_count": 0,
            "fold_count": 0,
        }
        for r in RegimeLabel
    }
    return {
        "regimes": regimes,
        "edge_only_in_rare_regime": False,
        "rare_regime_untradeable": False,
        "catastrophic_loss_in_single_regime": False,
        "catastrophic_loss_regime": None,
        "total_folds_evaluated": 0,
        "folds_per_regime": {r.value: 0 for r in RegimeLabel},
    }


# ---------------------------------------------------------------------------
# Symbol x Regime stability matrix
# ---------------------------------------------------------------------------

STABILITY_REGIME_LABELS: List[str] = [
    "TREND_UP",
    "TREND_DOWN",
    "RANGE",
    "TRANSITION",
]


def compute_symbol_regime_matrix(
    per_symbol_labels: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Compute symbol x regime distribution matrix and cross-symbol stability.

    For each symbol, computes the fraction of bars that fall into each regime.
    Also computes a stability score per symbol (1 - transition_rate) and
    cross-symbol correlation of regime distributions.

    Args:
        per_symbol_labels: Dict mapping symbol name -> list of regime label
            strings (e.g. "TREND_UP", "TREND_DOWN").  Each list must have at
            least one element.  Regime labels not in STABILITY_REGIME_LABELS
            are aggregated under "OTHER".

    Returns:
        Dict with keys:
            matrix: Dict[symbol, Dict[regime, fraction]] — fractions sum to 1.0
                per symbol (or 0.0 for empty series).  All four canonical
                regimes plus "OTHER" appear as columns.
            stability_scores: Dict[symbol, float] — 1.0 means no regime
                transitions (perfect stability), 0.0 means every bar is a
                different regime from the previous.
            dominant_regime: Dict[symbol, str] — most frequent regime per
                symbol, or "NONE" for empty input.
            num_symbols: int
            avg_stability: float — mean stability score across symbols.
            cross_symbol_consistency: Dict[regime, float] — coefficient of
                variation (std/mean) of regime fractions across symbols.
                Lower values mean more consistent regime distribution across
                symbols.
    """
    if not per_symbol_labels:
        return {
            "matrix": {},
            "stability_scores": {},
            "dominant_regime": {},
            "num_symbols": 0,
            "avg_stability": 0.0,
            "cross_symbol_consistency": {r: 0.0 for r in STABILITY_REGIME_LABELS},
        }

    # Allowed regime labels + OTHER catch-all
    allowed = set(STABILITY_REGIME_LABELS)

    matrix: Dict[str, Dict[str, float]] = {}
    stability_scores: Dict[str, float] = {}
    dominant_regime: Dict[str, str] = {}

    for symbol, labels in per_symbol_labels.items():
        n = len(labels)
        if n == 0:
            matrix[symbol] = {r: 0.0 for r in STABILITY_REGIME_LABELS}
            matrix[symbol]["OTHER"] = 0.0
            stability_scores[symbol] = 1.0
            dominant_regime[symbol] = "NONE"
            continue

        # Count regime occurrences
        counts: Dict[str, int] = {r: 0 for r in STABILITY_REGIME_LABELS}
        counts["OTHER"] = 0
        for lbl in labels:
            if lbl in allowed:
                counts[lbl] += 1
            else:
                counts["OTHER"] += 1

        # Convert to fractions
        matrix[symbol] = {r: c / n for r, c in counts.items()}

        # Dominant regime
        dominant = max(counts, key=lambda k: counts[k])  # type: ignore[arg-type]
        dominant_regime[symbol] = dominant

        # Stability: 1 - (transitions / max_possible_transitions)
        transitions = sum(
            1 for i in range(1, n) if labels[i] != labels[i - 1]
        )
        max_transitions = n - 1
        stability_scores[symbol] = (
            1.0 - (transitions / max_transitions) if max_transitions > 0 else 1.0
        )

    # Average stability
    stability_vals = list(stability_scores.values())
    avg_stability = sum(stability_vals) / len(stability_vals) if stability_vals else 0.0

    # Cross-symbol consistency: coefficient of variation per regime
    cross_symbol_consistency: Dict[str, float] = {}
    for regime in STABILITY_REGIME_LABELS:
        fractions = [matrix[s].get(regime, 0.0) for s in per_symbol_labels]
        mean_frac = sum(fractions) / len(fractions) if fractions else 0.0
        if mean_frac > 0:
            variance = sum((f - mean_frac) ** 2 for f in fractions) / len(fractions)
            std_dev = math.sqrt(variance)
            cross_symbol_consistency[regime] = std_dev / mean_frac  # CV
        else:
            cross_symbol_consistency[regime] = 0.0  # No variance when all zero

    return {
        "matrix": matrix,
        "stability_scores": stability_scores,
        "dominant_regime": dominant_regime,
        "num_symbols": len(per_symbol_labels),
        "avg_stability": avg_stability,
        "cross_symbol_consistency": cross_symbol_consistency,
    }
