"""
Calibration drift monitoring — detect calibration degradation over time.

Measures drift between current and baseline calibration metrics,
and detects decay patterns across historical calibration snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class CalibrationDriftReport:
    """Report of calibration drift between current and baseline.

    Attributes:
        timestamp: When the drift analysis was performed.
        ece_drift: Drift in Expected Calibration Error (positive = worse).
        mce_drift: Drift in Maximum Calibration Error (positive = worse).
        reliability_drift: Drift in reliability score (negative = worse).
        bucket_drifts: Dict of bucket_name -> drift value.
        significant: True if any drift exceeds the threshold.
        detail: Human-readable summary of drift findings.
    """

    timestamp: str = ""
    ece_drift: float = 0.0
    mce_drift: float = 0.0
    reliability_drift: float = 0.0
    bucket_drifts: dict[str, float] = field(default_factory=dict)
    significant: bool = False
    detail: str = ""


@dataclass(frozen=True)
class CalibrationDecayTrend:
    """Trend analysis of calibration metrics over time.

    Attributes:
        periods_analyzed: Number of time periods in the analysis.
        ece_trend: Slope of ECE over time (positive = worsening).
        mce_trend: Slope of MCE over time (positive = worsening).
        reliability_trend: Slope of reliability over time (negative = worsening).
        accelerating: True if decay is accelerating (increasing slope magnitude).
        detail: Human-readable summary of decay findings.
    """

    periods_analyzed: int = 0
    ece_trend: float = 0.0
    mce_trend: float = 0.0
    reliability_trend: float = 0.0
    accelerating: bool = False
    detail: str = ""


def _default_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_drift(
    current: dict[str, Any],
    baseline: dict[str, Any],
    threshold: float = 0.05,
) -> CalibrationDriftReport:
    """Compute calibration drift between current and baseline metrics.

    Args:
        current: Current calibration metrics dict. Expected keys:
                 - ece: Expected Calibration Error (float)
                 - mce: Maximum Calibration Error (float, optional)
                 - reliability: Reliability score (float, optional)
                 - buckets: Dict of bucket_name -> dict with 'accuracy' and 'confidence'
        baseline: Baseline calibration metrics dict (same schema).
        threshold: ECE drift threshold for significance flag (default 0.05).

    Returns:
        A CalibrationDriftReport with drift values and significance.
    """
    current_ece = current.get("ece", 0.0)
    baseline_ece = baseline.get("ece", 0.0)
    ece_drift = current_ece - baseline_ece

    current_mce = current.get("mce", 0.0)
    baseline_mce = baseline.get("mce", 0.0)
    mce_drift = current_mce - baseline_mce

    current_reliability = current.get("reliability", 1.0)
    baseline_reliability = baseline.get("reliability", 1.0)
    reliability_drift = current_reliability - baseline_reliability

    # Per-bucket drift analysis
    current_buckets = current.get("buckets", {})
    baseline_buckets = baseline.get("buckets", {})
    bucket_drifts: dict[str, float] = {}

    all_buckets = set(current_buckets.keys()) | set(baseline_buckets.keys())
    for bucket in sorted(all_buckets):
        cb = current_buckets.get(bucket, {})
        bb = baseline_buckets.get(bucket, {})
        if isinstance(cb, dict) and isinstance(bb, dict):
            acc_drift = cb.get("accuracy", 0.0) - bb.get("accuracy", 0.0)
            conf_drift = cb.get("confidence", 0.0) - bb.get("confidence", 0.0)
            if abs(acc_drift) > 0.01 or abs(conf_drift) > 0.01:
                bucket_drifts[bucket] = round(acc_drift - conf_drift, 4)

    significant = abs(ece_drift) > threshold

    # Build detail
    detail_parts: list[str] = [
        f"ECE drift={ece_drift:+.4f}",
        f"MCE drift={mce_drift:+.4f}",
        f"reliability drift={reliability_drift:+.4f}",
    ]
    if bucket_drifts:
        drift_summary = "; ".join(f"{b}={v:+.4f}" for b, v in bucket_drifts.items())
        detail_parts.append(f"bucket drifts: {drift_summary}")
    if significant:
        detail_parts.append("SIGNIFICANT — exceeds threshold")

    return CalibrationDriftReport(
        timestamp=_default_ts(),
        ece_drift=round(ece_drift, 4),
        mce_drift=round(mce_drift, 4),
        reliability_drift=round(reliability_drift, 4),
        bucket_drifts=bucket_drifts,
        significant=significant,
        detail=" | ".join(detail_parts),
    )


def detect_calibration_decay(
    metric_history: list[dict[str, Any]],
) -> CalibrationDecayTrend:
    """Detect calibration decay patterns from historical metric snapshots.

    Each entry in metric_history should be a dict with:
      - timestamp: str (ISO format)
      - ece: float
      - mce: float (optional)
      - reliability: float (optional)

    Uses linear regression (least squares) to estimate trend slopes.

    Args:
        metric_history: Chronological list of calibration metric snapshots.

    Returns:
        A CalibrationDecayTrend with trend slopes and acceleration detection.
    """
    if len(metric_history) < 2:
        return CalibrationDecayTrend(
            periods_analyzed=len(metric_history),
            detail="Insufficient data for trend detection (need >= 2 periods)",
        )

    periods = len(metric_history)

    # Extract metric sequences
    ece_values = [m.get("ece", 0.0) for m in metric_history]
    mce_values = [m.get("mce", 0.0) for m in metric_history]
    reliability_values = [m.get("reliability", 1.0) for m in metric_history]

    def _slope(y: list[float]) -> float:
        """Compute least-squares slope of y over x=[0, 1, ..., n-1]."""
        n = len(y)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2.0
        y_mean = sum(y) / n
        num = sum((i - x_mean) * (y[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        return num / den if den != 0 else 0.0

    ece_trend = _slope(ece_values)
    mce_trend = _slope(mce_values) if any(m.get("mce") is not None for m in metric_history) else 0.0
    reliability_trend = _slope(reliability_values)

    # Detect acceleration: compare first-half slope vs second-half slope
    mid = periods // 2
    ece_first = _slope(ece_values[:mid])
    ece_second = _slope(ece_values[mid:])
    accelerating = abs(ece_second) > abs(ece_first) and ece_second > ece_first

    detail_parts = [
        f"ECE trend={ece_trend:+.4f}/period across {periods} periods",
    ]
    if mce_trend != 0.0:
        detail_parts.append(f"MCE trend={mce_trend:+.4f}/period")
    detail_parts.append(f"reliability trend={reliability_trend:+.4f}/period")
    if accelerating:
        detail_parts.append("Decay is accelerating")

    return CalibrationDecayTrend(
        periods_analyzed=periods,
        ece_trend=round(ece_trend, 4),
        mce_trend=round(mce_trend, 4),
        reliability_trend=round(reliability_trend, 4),
        accelerating=accelerating,
        detail=" | ".join(detail_parts),
    )
