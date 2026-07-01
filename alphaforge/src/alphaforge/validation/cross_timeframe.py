"""Cross-timeframe edge comparison for Multi-Timeframe Alpha Tuning (Issue #143).

Compares alpha edges across the three canonical timeframes:
  - SWING (4h primary, widest windows)
  - SCALP (1h primary, narrower windows)
  - AGGRESSIVE_SCALP (15m primary, microstructure-aware windows)

Detection criteria:
  1. Edge consistency: Is the edge direction (long/short) consistent across
     timeframes, or do timeframes conflict?
  2. Edge strength ranking: Which timeframe shows the strongest risk-adjusted
     edge (highest Sharpe)?
  3. Edge uniqueness: Does edge exist only in one timeframe (specialization)
     or across all (multi-timeframe confirmation)?
  4. Cross-timeframe correlation: How correlated are per-bar predictions
     across timeframes?

All functions are deterministic (numpy-only, no ML imports). Returns
descriptive assessments, NOT profitability claims. Verdicts are capped at
CONTINUE_RESEARCH — only V7 gates can promote to CANDIDATE_FOR_V7_GATES.

Usage:
    from alphaforge.validation.cross_timeframe import (
        compare_timeframes,
        compute_cross_timeframe_correlation,
    )
    comparison = compare_timeframes(swing_result, scalp_result, agg_result)
    correlation = compute_cross_timeframe_correlation(predictions_dict)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Supported modes for cross-timeframe comparison
ALL_MODES: Tuple[str, ...] = ("SWING", "SCALP", "AGGRESSIVE_SCALP")

# Thresholds for edge detection
EDGE_PRESENT_SHARPE: float = 0.3        # Minimum Sharpe to consider edge present
EDGE_PRESENT_EXPECTANCY_R: float = 0.05  # Minimum expectancy_r to consider edge present
STRONG_EDGE_SHARPE: float = 0.8          # Sharpe above this is a strong edge
WEAK_EDGE_SHARPE: float = 0.15           # Sharpe below this is a weak/no edge

# Correlation thresholds
HIGH_CORRELATION: float = 0.7           # Above this: timeframes agree strongly
LOW_CORRELATION: float = 0.3            # Below this: timeframes diverge

# Consistency thresholds
CONSISTENCY_HIGH: float = 0.7           # Fraction of timeframes agreeing on direction
CONSISTENCY_MODERATE: float = 0.5       # Minimum for moderate consistency


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TimeframeEdge:
    """Edge assessment for a single timeframe."""

    mode: str
    sharpe: float
    expectancy_r: float
    win_rate: float
    trade_count: int
    fold_count: int
    edge_present: bool
    edge_strength: str  # "NONE", "WEAK", "MODERATE", "STRONG"
    direction: str       # "LONG_BIAS", "SHORT_BIAS", "NEUTRAL", "INCONCLUSIVE"


@dataclass
class CrossTimeframeComparison:
    """Complete cross-timeframe edge comparison."""

    timeframes: Dict[str, TimeframeEdge] = field(default_factory=dict)
    dominant_timeframe: str = ""           # Mode with strongest edge
    consistency_score: float = 0.0         # 0-1: how consistent are edges
    pairwise_correlations: Dict[str, float] = field(default_factory=dict)
    multi_tf_confirmation: bool = False    # Edge present across >= 2 timeframes
    tf_specialization: bool = False        # Edge only in one timeframe
    has_conflict: bool = False             # Timeframes disagree on direction
    summary: str = ""
    verdict: str = "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_edge_strength(sharpe: float, expectancy_r: float) -> str:
    """Classify edge strength from Sharpe and expectancy_r.

    Returns one of: NONE, WEAK, MODERATE, STRONG.
    """
    if sharpe <= 0 and expectancy_r <= 0:
        return "NONE"
    if sharpe >= STRONG_EDGE_SHARPE and expectancy_r >= EDGE_PRESENT_EXPECTANCY_R:
        return "STRONG"
    if sharpe >= EDGE_PRESENT_SHARPE and expectancy_r >= EDGE_PRESENT_EXPECTANCY_R:
        return "MODERATE"
    if sharpe > 0 or expectancy_r > 0:
        return "WEAK"
    return "NONE"


def _infer_direction(sharpe: float, expectancy_r: float) -> str:
    """Infer edge direction from metrics.

    Positive expectancy_r with positive Sharpe → LONG_BIAS
    Positive expectancy_r with negative Sharpe → SHORT_BIAS (or volatile)
    Near-zero → NEUTRAL
    """
    if expectancy_r > EDGE_PRESENT_EXPECTANCY_R and sharpe > 0:
        return "LONG_BIAS"
    if expectancy_r > EDGE_PRESENT_EXPECTANCY_R and sharpe < -EDGE_PRESENT_SHARPE:
        return "SHORT_BIAS"
    if abs(expectancy_r) < 0.01 and abs(sharpe) < 0.1:
        return "NEUTRAL"
    return "INCONCLUSIVE"


def _direction_score(direction: str) -> int:
    """Map direction to numeric score for consistency computation.

    LONG_BIAS = 1, SHORT_BIAS = -1, NEUTRAL = 0, INCONCLUSIVE = 0
    """
    mapping = {
        "LONG_BIAS": 1,
        "SHORT_BIAS": -1,
        "NEUTRAL": 0,
        "INCONCLUSIVE": 0,
    }
    return mapping.get(direction, 0)


# ---------------------------------------------------------------------------
# Cross-timeframe edge comparison
# ---------------------------------------------------------------------------


def build_timeframe_edge(
    mode: str,
    wfv_results: Dict[str, Any],
) -> TimeframeEdge:
    """Build a single TimeframeEdge assessment from WFV results.

    Args:
        mode: Mode name (SWING, SCALP, AGGRESSIVE_SCALP).
        wfv_results: WalkForwardResult-like dict or object with aggregate_metrics.

    Returns:
        TimeframeEdge with edge assessment.
    """
    # Extract aggregate metrics
    agg = {}
    if isinstance(wfv_results, dict):
        agg = wfv_results.get("aggregate_metrics", wfv_results)
    else:
        agg = getattr(wfv_results, "aggregate_metrics", {})

    sharpe = float(agg.get("avg_sharpe", agg.get("sharpe", 0.0)))
    expectancy_r = float(agg.get("avg_expectancy_r", agg.get("oos_expectancy_r", 0.0)))
    win_rate = float(agg.get("avg_win_rate", agg.get("win_rate", 0.5)))
    trade_count = int(agg.get("total_oos_trades", agg.get("oos_trade_count", 0)))
    fold_count = int(agg.get("n_folds", 6))

    edge_present = (
        sharpe >= EDGE_PRESENT_SHARPE
        and expectancy_r >= EDGE_PRESENT_EXPECTANCY_R
    )
    edge_strength = _classify_edge_strength(sharpe, expectancy_r)
    direction = _infer_direction(sharpe, expectancy_r)

    return TimeframeEdge(
        mode=mode,
        sharpe=sharpe,
        expectancy_r=expectancy_r,
        win_rate=win_rate,
        trade_count=trade_count,
        fold_count=fold_count,
        edge_present=edge_present,
        edge_strength=edge_strength,
        direction=direction,
    )


def compute_pairwise_correlation(
    predictions_per_mode: Dict[str, np.ndarray],
) -> Dict[str, float]:
    """Compute pairwise prediction correlation across timeframes.

    Args:
        predictions_per_mode: Dict mapping mode -> numpy array of predictions
            (0=LONG_NOW, 1=SHORT_NOW, 2=NO_TRADE). Arrays should be aligned
            by bar index for the same symbols/timestamps.

    Returns:
        Dict mapping pair key (e.g. "SWING_vs_SCALP") to Pearson correlation
        coefficient. Returns 0.0 for pairs with insufficient overlap.
    """
    correlations: Dict[str, float] = {}
    modes_list = sorted(predictions_per_mode.keys())

    for i in range(len(modes_list)):
        for j in range(i + 1, len(modes_list)):
            m1 = modes_list[i]
            m2 = modes_list[j]
            key = f"{m1}_vs_{m2}"

            arr1 = predictions_per_mode[m1]
            arr2 = predictions_per_mode[m2]

            if len(arr1) == 0 or len(arr2) == 0:
                correlations[key] = 0.0
                continue

            # Align to shorter array
            min_len = min(len(arr1), len(arr2))
            a1 = arr1[:min_len]
            a2 = arr2[:min_len]

            # Compute Pearson correlation
            a1_float = a1.astype(np.float64)
            a2_float = a2.astype(np.float64)

            mask = ~(np.isnan(a1_float) | np.isnan(a2_float))
            if np.sum(mask) < 5:
                correlations[key] = 0.0
                continue

            a1_clean = a1_float[mask]
            a2_clean = a2_float[mask]

            if np.std(a1_clean) < 1e-12 or np.std(a2_clean) < 1e-12:
                correlations[key] = 0.0
                continue

            corr = float(np.corrcoef(a1_clean, a2_clean)[0, 1])
            correlations[key] = round(corr, 4)

    return correlations


def compare_timeframes(
    wfv_results: Dict[str, Any],
    predictions_per_mode: Optional[Dict[str, np.ndarray]] = None,
) -> CrossTimeframeComparison:
    """Compare alpha edges across all three canonical timeframes.

    Args:
        wfv_results: Dict mapping mode -> WFV results dict or WalkForwardResult.
            Expected keys: 'SWING', 'SCALP', 'AGGRESSIVE_SCALP'.
        predictions_per_mode: Optional dict mapping mode -> aligned prediction
            arrays for pairwise correlation computation.

    Returns:
        CrossTimeframeComparison with per-timeframe edges, consistency score,
        dominant timeframe, and summary.
    """
    # Build per-timeframe edge assessments
    timeframes: Dict[str, TimeframeEdge] = {}
    for mode in ALL_MODES:
        if mode not in wfv_results:
            continue
        edge = build_timeframe_edge(mode, wfv_results[mode])
        timeframes[mode] = edge

    if not timeframes:
        return CrossTimeframeComparison(
            verdict="INCONCLUSIVE",
            summary="No timeframe results available for comparison.",
        )

    # Determine dominant timeframe (strongest edge)
    dominant = ""
    highest_sharpe = -999.0
    for mode, edge in timeframes.items():
        if edge.edge_present and edge.sharpe > highest_sharpe:
            highest_sharpe = edge.sharpe
            dominant = mode

    # Compute consistency score: fraction of timeframes agreeing on direction
    direction_scores = [_direction_score(edge.direction) for edge in timeframes.values()]
    if direction_scores:
        # Count pairs that agree
        agreements = 0
        pairs = 0
        for i in range(len(direction_scores)):
            for j in range(i + 1, len(direction_scores)):
                pairs += 1
                if direction_scores[i] == direction_scores[j] and direction_scores[i] != 0:
                    agreements += 1
        consistency_score = agreements / pairs if pairs > 0 else 0.0
    else:
        consistency_score = 0.0

    # Count edges present
    edges_present = sum(1 for e in timeframes.values() if e.edge_present)

    # Multi-timeframe confirmation
    multi_tf_confirmation = edges_present >= 2

    # Timeframe specialization
    tf_specialization = edges_present == 1 and len(timeframes) >= 2

    # Conflict detection
    has_conflict = consistency_score < CONSISTENCY_MODERATE and edges_present >= 2

    # Pairwise correlations
    pairwise_correlations: Dict[str, float] = {}
    if predictions_per_mode is not None:
        pairwise_correlations = compute_pairwise_correlation(predictions_per_mode)

    # Build summary
    summary_parts: List[str] = []
    for mode in ALL_MODES:
        if mode in timeframes:
            e = timeframes[mode]
            summary_parts.append(
                f"{mode}: sharpe={e.sharpe:.4f}, edge={e.edge_strength}, "
                f"direction={e.direction}"
            )

    if dominant:
        summary_parts.append(
            f"Dominant timeframe: {dominant} (sharpe={highest_sharpe:.4f})"
        )

    if multi_tf_confirmation:
        summary_parts.append("Multi-timeframe confirmation: edge present across >= 2 timeframes")
    elif tf_specialization:
        summary_parts.append("Timeframe specialization: edge in single timeframe only")

    if has_conflict:
        summary_parts.append("WARNING: Timeframes disagree on direction — high uncertainty")

    # Pairwise correlations summary
    if pairwise_correlations:
        for pair, corr in pairwise_correlations.items():
            summary_parts.append(
                f"{pair}: correlation={corr:.4f} "
                f"({'HIGH' if abs(corr) >= HIGH_CORRELATION else 'MODERATE' if abs(corr) >= LOW_CORRELATION else 'LOW'})"
            )

    # Determine verdict
    if multi_tf_confirmation and not has_conflict:
        verdict = "CONTINUE_RESEARCH"
    elif edges_present >= 1:
        verdict = "CONTINUE_RESEARCH"
    else:
        verdict = "INCONCLUSIVE"

    summary = " | ".join(summary_parts)

    return CrossTimeframeComparison(
        timeframes=timeframes,
        dominant_timeframe=dominant,
        consistency_score=round(consistency_score, 4),
        pairwise_correlations=pairwise_correlations,
        multi_tf_confirmation=multi_tf_confirmation,
        tf_specialization=tf_specialization,
        has_conflict=has_conflict,
        summary=summary,
        verdict=verdict,
    )


def compare_timeframes_to_dict(result: CrossTimeframeComparison) -> Dict[str, Any]:
    """Convert CrossTimeframeComparison to a JSON-serializable dict.

    Args:
        result: CrossTimeframeComparison from compare_timeframes().

    Returns:
        Dict suitable for JSON serialization.
    """
    return {
        "dominant_timeframe": result.dominant_timeframe,
        "consistency_score": result.consistency_score,
        "multi_tf_confirmation": result.multi_tf_confirmation,
        "tf_specialization": result.tf_specialization,
        "has_conflict": result.has_conflict,
        "pairwise_correlations": result.pairwise_correlations,
        "timeframes": {
            mode: {
                "sharpe": edge.sharpe,
                "expectancy_r": edge.expectancy_r,
                "win_rate": edge.win_rate,
                "trade_count": edge.trade_count,
                "fold_count": edge.fold_count,
                "edge_present": edge.edge_present,
                "edge_strength": edge.edge_strength,
                "direction": edge.direction,
            }
            for mode, edge in result.timeframes.items()
        },
        "summary": result.summary,
        "verdict": result.verdict,
    }
