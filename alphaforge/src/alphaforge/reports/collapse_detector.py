"""NO_TRADE Collapse Detector — Issue #117.

Diagnoses why the model predicts NO_TRADE excessively, providing:
  1. NO_TRADE percentage trend over time (sliding windows).
  2. Collapse detection when NO_TRADE exceeds a configurable threshold.
  3. Root cause tree: cost vs signal vs model vs threshold.
  4. Counterfactual analysis: what if NO_TRADE decisions were replaced with trades.
  5. saved_loss_r / missed_opportunity_r ratio.

All functions operate on label dicts (AlphaForgeLabel) and produce
DESCRIPTIVE-only output. No profitability claims. No model training.

Design decisions:
  - Window-based trend analysis to detect gradual NO_TRADE degradation.
  - Deterministic root cause categorisation based on label metadata.
  - Counterfactual uses net_r from NO_TRADE bars to estimate opportunity
    cost / saved loss.
  - Threshold is configurable with a documented default of 70%.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_COLLAPSE_THRESHOLD: float = 0.70
"""NO_TRADE proportion above which a collapse is declared."""

DEFAULT_WINDOW_SIZE: int = 100
"""Number of bars per sliding window for trend analysis."""

MIN_BARS_FOR_TREND: int = 50
"""Minimum total bars required for meaningful trend analysis."""

COLLAPSE_ROOT_CAUSE_ORDER: tuple[str, ...] = (
    "cost",
    "signal",
    "model",
    "threshold",
)
"""Priority order for root cause assignment (first matching wins as primary)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_best_action(label: dict) -> str:
    """Extract best_action_label from a label dict."""
    if not isinstance(label, dict):
        return "UNKNOWN"
    return label.get("best_action_label", "UNKNOWN")


def _parse_numeric(label: dict, key: str, default: float = 0.0) -> float:
    """Safely extract a numeric value from a label dict."""
    if not isinstance(label, dict):
        return default
    val = label.get(key, default)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _is_no_trade(action: str) -> bool:
    """Check if an action string indicates NO_TRADE."""
    upper = action.upper()
    return "NO_TRADE" in upper or "NO TRADE" in upper or upper == "NO_TRADE"


def _is_directional(action: str) -> bool:
    """Check if an action string indicates a directional trade (LONG/SHORT)."""
    upper = action.upper()
    return upper.startswith("LONG") or upper.startswith("SHORT")


def _sliding_window_pcts(
    actions: list[str], window_size: int,
) -> list[dict]:
    """Compute NO_TRADE percentage over sliding windows.

    Args:
        actions: List of best_action_label strings in chronological order.
        window_size: Number of bars per window.

    Returns:
        List of dicts with keys: window_start, window_end, no_trade_count,
        total_count, no_trade_pct. Empty when actions are too few.
    """
    total = len(actions)
    if total < window_size:
        return []

    results: list[dict] = []
    for start in range(0, total - window_size + 1, window_size // 2):
        end = min(start + window_size, total)
        window = actions[start:end]
        nt_count = sum(1 for a in window if _is_no_trade(a))
        results.append({
            "window_start": start,
            "window_end": end,
            "no_trade_count": nt_count,
            "total_count": len(window),
            "no_trade_pct": round((nt_count / len(window)) * 100.0, 1),
        })
        if end == total:
            break

    return results


def _classify_no_trade_quality(label: dict) -> str:
    """Classify a NO_TRADE label into cost/signal/model/threshold.

    Args:
        label: A label dict with best_action_label == NO_TRADE.

    Returns:
        One of 'cost', 'signal', 'model', 'threshold', or 'unknown'.
    """
    quality = label.get("no_trade_quality", "")
    if not quality:
        return "unknown"

    q_upper = quality.upper()

    # Cost dominated: fees, slippage, spread consume the edge
    if "COST" in q_upper or "FEE" in q_upper or "SLIPPAGE" in q_upper or "SPREAD" in q_upper:
        return "cost"

    # Signal: no directional edge detected, noise-dominated
    if "EDGE" in q_upper or "NOISE" in q_upper or "SIGNAL" in q_upper:
        return "signal"

    # Model: ambiguous, uncertain, low confidence
    if "AMBIGUOUS" in q_upper or "UNCERTAIN" in q_upper or "CONFIDENCE" in q_upper:
        return "model"

    # Threshold: label threshold filtered it out
    if "THRESHOLD" in q_upper or "FILTER" in q_upper or "EXCLUDE" in q_upper or "SCOPE" in q_upper:
        return "threshold"

    # Saved loss / correct no-trade -> signal (correctly avoided bad trade)
    if "SAVED" in q_upper or "CORRECT" in q_upper:
        return "signal"

    # Missed opportunity -> model (could be model uncertainty)
    if "MISSED" in q_upper:
        return "model"

    return "unknown"


# ---------------------------------------------------------------------------
# 1. NO_TRADE Trend Analysis
# ---------------------------------------------------------------------------


def compute_no_trade_trend(
    labels: list[dict],
    window_size: int = DEFAULT_WINDOW_SIZE,
) -> dict:
    """Compute NO_TRADE percentage trend over time using sliding windows.

    Args:
        labels: List of AlphaForgeLabel dicts in chronological order.
        window_size: Number of bars per sliding window (default 100).

    Returns:
        Dict with:
            windows (list[dict]): Per-window NO_TRADE percentages.
            overall_no_trade_pct (float): Overall NO_TRADE percentage.
            trend_direction (str): 'increasing', 'decreasing', 'stable',
                or 'insufficient_data'.
            max_window_pct (float): Maximum NO_TRADE % across windows.
            min_window_pct (float): Minimum NO_TRADE % across windows.
            collapse_detected (bool): True if any window exceeds threshold.
            total_bars (int): Total number of labels analysed.
    """
    if not labels:
        return {
            "windows": [],
            "overall_no_trade_pct": 0.0,
            "trend_direction": "insufficient_data",
            "max_window_pct": 0.0,
            "min_window_pct": 0.0,
            "collapse_detected": False,
            "total_bars": 0,
        }

    total = len(labels)
    actions = [_parse_best_action(lbl) for lbl in labels]

    overall_nt = sum(1 for a in actions if _is_no_trade(a))
    overall_pct = round((overall_nt / total) * 100.0, 1) if total > 0 else 0.0

    windows = _sliding_window_pcts(actions, window_size)

    if len(windows) < 2:
        return {
            "windows": windows,
            "overall_no_trade_pct": overall_pct,
            "trend_direction": "insufficient_data",
            "max_window_pct": max((w["no_trade_pct"] for w in windows), default=overall_pct),
            "min_window_pct": min((w["no_trade_pct"] for w in windows), default=overall_pct),
            "collapse_detected": any(w["no_trade_pct"] >= DEFAULT_COLLAPSE_THRESHOLD * 100.0 for w in windows),
            "total_bars": total,
        }

    window_pcts = [w["no_trade_pct"] for w in windows]

    # Determine trend: compare first half vs second half
    mid = len(window_pcts) // 2
    first_half_avg = sum(window_pcts[:mid]) / mid
    second_half_avg = sum(window_pcts[mid:]) / (len(window_pcts) - mid)

    change = second_half_avg - first_half_avg
    # More than 5 percentage points change = meaningful
    if change > 5.0:
        trend = "increasing"
    elif change < -5.0:
        trend = "decreasing"
    else:
        trend = "stable"

    collapse_detected = any(p >= DEFAULT_COLLAPSE_THRESHOLD * 100.0 for p in window_pcts)

    return {
        "windows": windows,
        "overall_no_trade_pct": overall_pct,
        "trend_direction": trend,
        "max_window_pct": max(window_pcts),
        "min_window_pct": min(window_pcts),
        "collapse_detected": collapse_detected,
        "total_bars": total,
    }


# ---------------------------------------------------------------------------
# 2. Collapse Detection
# ---------------------------------------------------------------------------


def detect_no_trade_collapse(
    labels: list[dict],
    mode: str,
    collapse_threshold: float = DEFAULT_COLLAPSE_THRESHOLD,
    window_size: int = DEFAULT_WINDOW_SIZE,
) -> dict:
    """Detect whether the model has entered a NO_TRADE collapse state.

    A collapse is declared when the overall NO_TRADE percentage exceeds
    the threshold, OR any sliding window exceeds the threshold.

    Args:
        labels: List of AlphaForgeLabel dicts.
        mode: Mode identifier ('SCALP', 'AGGRESSIVE_SCALP', 'SWING').
        collapse_threshold: NO_TRADE proportion threshold (default 0.70 = 70%).
        window_size: Sliding window size for trend analysis.

    Returns:
        Dict with:
            collapse_detected (bool): True if NO_TRADE exceeds threshold.
            collapse_severity (str): 'NONE', 'WARNING', 'CRITICAL'.
            overall_no_trade_pct (float): Overall NO_TRADE percentage.
            collapse_threshold_used (float): Threshold used for detection.
            windows_above_threshold (int): Count of windows exceeding threshold.
            total_windows (int): Total sliding windows analysed.
            mode (str): Mode identifier.
            summary (str): Human-readable collapse status.
    """
    trend = compute_no_trade_trend(labels, window_size=window_size)
    overall_pct = trend["overall_no_trade_pct"]
    windows_above = sum(
        1 for w in trend["windows"]
        if w["no_trade_pct"] >= collapse_threshold * 100.0
    )

    collapse_detected = trend["collapse_detected"] or overall_pct >= collapse_threshold * 100.0

    if not collapse_detected:
        severity = "NONE"
        summary = (
            f"No collapse detected. NO_TRADE is {overall_pct}% "
            f"(threshold: {collapse_threshold * 100:.0f}%)."
        )
    elif overall_pct >= collapse_threshold * 100.0 + 15.0:
        severity = "CRITICAL"
        summary = (
            f"CRITICAL collapse: NO_TRADE at {overall_pct}% "
            f"(threshold: {collapse_threshold * 100:.0f}%). "
            f"Model is predominantly predicting NO_TRADE. "
            f"Root cause analysis recommended before proceeding."
        )
    else:
        severity = "WARNING"
        summary = (
            f"Collapse WARNING: NO_TRADE at {overall_pct}% "
            f"(threshold: {collapse_threshold * 100:.0f}%). "
            f"Monitor closely and diagnose root cause."
        )

    return {
        "collapse_detected": collapse_detected,
        "collapse_severity": severity,
        "overall_no_trade_pct": overall_pct,
        "collapse_threshold_used": collapse_threshold,
        "windows_above_threshold": windows_above,
        "total_windows": len(trend["windows"]),
        "mode": mode,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# 3. Root Cause Tree
# ---------------------------------------------------------------------------


def build_collapse_root_cause_tree(
    labels: list[dict],
    collapse_result: dict | None = None,
) -> dict:
    """Build a root cause tree for NO_TRADE collapse.

    Classifies NO_TRADE labels into four root cause categories:
      - cost: Gross edge exists but costs destroy it.
      - signal: No directional edge detected above noise.
      - model: Model/label uncertainty, ambiguous direction.
      - threshold: Label construction thresholds too conservative.

    The primary root cause is the category with the highest proportion
    among classified NO_TRADE labels.

    Args:
        labels: List of AlphaForgeLabel dicts.
        collapse_result: Optional result from detect_no_trade_collapse()
            for enriched context.

    Returns:
        Dict with:
            root_cause_breakdown (dict[str, float]): Proportion per cause
                among classified NO_TRADE labels.
            primary_cause (str): Dominant root cause category.
            secondary_causes (list[str]): Contributing causes.
            unclassified_count (int): NO_TRADE labels without quality info.
            total_no_trade (int): Total NO_TRADE labels.
            evidence (list[str]): Supporting evidence strings.
            summary (str): Human-readable root cause assessment.
    """
    if not labels:
        default = {c: 0.0 for c in COLLAPSE_ROOT_CAUSE_ORDER}
        default["unknown"] = 0.0
        return {
            "root_cause_breakdown": default,
            "primary_cause": "unknown",
            "secondary_causes": [],
            "unclassified_count": 0,
            "total_no_trade": 0,
            "evidence": ["No label data available for root cause analysis."],
            "summary": "No label data available.",
        }

    total_no_trade = 0
    cause_counts: dict[str, int] = {c: 0 for c in COLLAPSE_ROOT_CAUSE_ORDER}
    cause_counts["unknown"] = 0
    unclassified = 0

    for label in labels:
        action = _parse_best_action(label)
        if not _is_no_trade(action):
            continue
        total_no_trade += 1
        cause = _classify_no_trade_quality(label)
        if cause in cause_counts:
            cause_counts[cause] += 1
        else:
            cause_counts["unknown"] += 1

    if total_no_trade == 0:
        default = {c: 0.0 for c in COLLAPSE_ROOT_CAUSE_ORDER}
        default["unknown"] = 0.0
        return {
            "root_cause_breakdown": default,
            "primary_cause": "none",
            "secondary_causes": [],
            "unclassified_count": 0,
            "total_no_trade": 0,
            "evidence": ["No NO_TRADE labels found in dataset."],
            "summary": "No NO_TRADE labels — collapse root cause not applicable.",
        }

    # Compute proportions
    breakdown: dict[str, float] = {}
    for cause, count in cause_counts.items():
        breakdown[cause] = round((count / total_no_trade) * 100.0, 1)

    unclassified = cause_counts.get("unknown", 0)

    # Determine primary cause (highest proportion among cost/signal/model/threshold)
    ordered_causes = [c for c in COLLAPSE_ROOT_CAUSE_ORDER]
    sorted_causes = sorted(ordered_causes, key=lambda c: cause_counts.get(c, 0), reverse=True)
    primary = sorted_causes[0] if cause_counts.get(sorted_causes[0], 0) > 0 else "unknown"
    secondary = [c for c in sorted_causes[1:] if cause_counts.get(c, 0) > 0]

    evidence: list[str] = []
    for cause in COLLAPSE_ROOT_CAUSE_ORDER:
        pct = breakdown.get(cause, 0.0)
        count = cause_counts.get(cause, 0)
        if count > 0:
            evidence.append(f"{cause}: {count} labels ({pct}% of NO_TRADE)")

    if unclassified > 0:
        evidence.append(
            f"unclassified: {unclassified} labels lack no_trade_quality metadata"
        )

    collapse_context = ""
    if collapse_result and collapse_result.get("collapse_detected"):
        collapse_context = (
            f" Collapse severity: {collapse_result.get('collapse_severity', 'UNKNOWN')}, "
            f"overall NO_TRADE: {collapse_result.get('overall_no_trade_pct', 0.0)}%."
        )

    summary = (
        f"Root cause analysis over {total_no_trade} NO_TRADE labels: "
        f"primary cause is '{primary}' "
        f"({breakdown.get(primary, 0.0):.1f}% of NO_TRADE)."
        f" Secondary causes: {', '.join(secondary) if secondary else 'none'}.{collapse_context}"
    )

    return {
        "root_cause_breakdown": breakdown,
        "primary_cause": primary,
        "secondary_causes": secondary,
        "unclassified_count": unclassified,
        "total_no_trade": total_no_trade,
        "evidence": evidence,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# 4. Counterfactual Analysis
# ---------------------------------------------------------------------------


def counterfactual_analysis(
    labels: list[dict],
) -> dict:
    """Analyse what would have happened if NO_TRADE decisions were trades.

    For each NO_TRADE bar, checks what the net_r outcome would have been
    if a trade was placed:
      - If net_r > 0: missed opportunity (the trade would have been profitable).
      - If net_r < 0: saved loss (the NO_TRADE decision avoided a loss).
      - If net_r == 0: neutral (no effect).

    Computes saved_loss_r / missed_opportunity_r ratio. A ratio > 1.0
    means the model correctly avoided more losses than it missed opportunities.

    Args:
        labels: List of AlphaForgeLabel dicts with net_r values.

    Returns:
        Dict with:
            total_no_trade (int): Total NO_TRADE bars analysed.
            saved_loss_count (int): Count of correctly avoided losses.
            missed_opportunity_count (int): Count of missed profitable trades.
            saved_loss_r (float): Sum of net_r for saved loss bars (negative
                values, stored as positive magnitude).
            missed_opportunity_r (float): Sum of net_r for missed opportunity
                bars (positive values).
            total_counterfactual_r (float): Net counterfactual R
                (positive means saved losses > missed opportunities).
            saved_missed_ratio (float): Ratio of saved_loss_r to
                missed_opportunity_r. Inf if no missed opportunities.
                None if both are zero.
            neutral_count (int): NO_TRADE bars with net_r ~= 0.
            summary (str): Human-readable counterfactual assessment.
    """
    if not labels:
        return {
            "total_no_trade": 0,
            "saved_loss_count": 0,
            "missed_opportunity_count": 0,
            "saved_loss_r": 0.0,
            "missed_opportunity_r": 0.0,
            "total_counterfactual_r": 0.0,
            "saved_missed_ratio": None,
            "neutral_count": 0,
            "summary": "No label data available for counterfactual analysis.",
        }

    saved_count = 0
    missed_count = 0
    neutral_count = 0
    saved_r = 0.0
    missed_r = 0.0

    for label in labels:
        action = _parse_best_action(label)
        if not _is_no_trade(action):
            continue
        net_r = _parse_numeric(label, "net_r", 0.0)

        if net_r < -1e-10:
            # Trade would have lost money -> correctly avoided
            saved_count += 1
            saved_r += abs(net_r)
        elif net_r > 1e-10:
            # Trade would have made money -> missed opportunity
            missed_count += 1
            missed_r += net_r
        else:
            neutral_count += 1

    total = saved_count + missed_count + neutral_count

    # Compute ratio
    ratio: float | None = None
    if missed_r > 1e-10:
        ratio = round(saved_r / missed_r, 4)
    elif saved_r > 1e-10:
        ratio = float("inf")
    else:
        ratio = None

    total_counterfactual = round(saved_r - missed_r, 4)

    if total == 0:
        summary = "No NO_TRADE bars with net_r data for counterfactual analysis."
    elif ratio is None:
        summary = (
            f"Counterfactual analysis over {total} NO_TRADE bars: "
            f"all net_r are zero. No saved losses or missed opportunities."
        )
    elif ratio == float("inf"):
        summary = (
            f"Counterfactual analysis: saved_loss_r={saved_r:.4f}, "
            f"no missed opportunities (ratio = inf). "
            f"Model correctly avoided {saved_count} losing trades."
        )
    elif ratio >= 1.0:
        summary = (
            f"Counterfactual analysis: saved_loss_r={saved_r:.4f} > "
            f"missed_opportunity_r={missed_r:.4f} (ratio={ratio}). "
            f"Model correctly avoids more loss than it misses opportunity. "
            f"{saved_count} losses avoided, {missed_count} opportunities missed."
        )
    else:
        summary = (
            f"Counterfactual analysis: saved_loss_r={saved_r:.4f} < "
            f"missed_opportunity_r={missed_r:.4f} (ratio={ratio}). "
            f"Model misses more opportunity than it avoids loss. "
            f"{saved_count} losses avoided, {missed_count} opportunities missed. "
            f"Consider reducing NO_TRADE threshold."
        )

    return {
        "total_no_trade": total,
        "saved_loss_count": saved_count,
        "missed_opportunity_count": missed_count,
        "saved_loss_r": round(saved_r, 4),
        "missed_opportunity_r": round(missed_r, 4),
        "total_counterfactual_r": total_counterfactual,
        "saved_missed_ratio": ratio,
        "neutral_count": neutral_count,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# 5. Comprehensive Collapse Report
# ---------------------------------------------------------------------------


def build_collapse_report(
    labels: list[dict],
    mode: str,
    collapse_threshold: float = DEFAULT_COLLAPSE_THRESHOLD,
    window_size: int = DEFAULT_WINDOW_SIZE,
) -> dict:
    """Build a comprehensive NO_TRADE collapse diagnostic report.

    Combines trend analysis, collapse detection, root cause tree,
    and counterfactual analysis into a single report dict.

    This is the main entry point for Issue #117.

    Args:
        labels: List of AlphaForgeLabel dicts in chronological order.
        mode: Mode identifier ('SCALP', 'AGGRESSIVE_SCALP', 'SWING').
        collapse_threshold: NO_TRADE proportion threshold (default 0.70).
        window_size: Sliding window size for trend analysis (default 100).

    Returns:
        Dict with:
            collapse_detected (bool)
            collapse_severity (str)
            trend (dict): Output from compute_no_trade_trend().
            detection (dict): Output from detect_no_trade_collapse().
            root_cause (dict): Output from build_collapse_root_cause_tree().
            counterfactual (dict): Output from counterfactual_analysis().
            mode (str)
            summary (str): Condensed overall assessment.
    """
    trend = compute_no_trade_trend(labels, window_size=window_size)
    detection = detect_no_trade_collapse(
        labels, mode,
        collapse_threshold=collapse_threshold,
        window_size=window_size,
    )
    root_cause = build_collapse_root_cause_tree(labels, collapse_result=detection)
    counter = counterfactual_analysis(labels)

    # Build condensed summary
    parts: list[str] = []
    if detection["collapse_detected"]:
        parts.append(
            f"COLLAPSE ({detection['collapse_severity']}): "
            f"NO_TRADE at {trend['overall_no_trade_pct']}% "
            f"(threshold {collapse_threshold * 100:.0f}%)"
        )
    else:
        parts.append(
            f"No collapse: NO_TRADE at {trend['overall_no_trade_pct']}% "
            f"(threshold {collapse_threshold * 100:.0f}%)"
        )

    parts.append(f"trend: {trend['trend_direction']}")
    parts.append(f"primary root cause: {root_cause['primary_cause']}")

    cr = counter
    if cr["saved_missed_ratio"] is not None:
        ratio_str = f"{cr['saved_missed_ratio']:.2f}" if isinstance(cr["saved_missed_ratio"], float) else "inf"
        parts.append(f"saved/missed ratio: {ratio_str}")
    else:
        parts.append("saved/missed ratio: N/A")

    summary = " | ".join(parts)

    return {
        "collapse_detected": detection["collapse_detected"],
        "collapse_severity": detection["collapse_severity"],
        "trend": trend,
        "detection": detection,
        "root_cause": root_cause,
        "counterfactual": counter,
        "mode": mode,
        "summary": summary,
    }
