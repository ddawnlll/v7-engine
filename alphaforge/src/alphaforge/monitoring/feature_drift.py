"""Feature drift detection using PSI and KS-test.

Detects distribution shifts in feature values between a reference (expected)
and current (observed) distribution. Used as the first early-warning signal
that model predictions may be unreliable.

References:
    - Population Stability Index (PSI): industry standard for monitoring
      scorecard stability in credit risk modeling.
    - Kolmogorov-Smirnov test: non-parametric test for comparing two
      empirical distributions.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import ks_2samp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# PSI thresholds (industry-standard convention for credit risk scorecards)
PSI_NO_DRIFT: float = 0.10
PSI_MODERATE_DRIFT: float = 0.25

# Default number of bins for PSI computation
PSI_DEFAULT_BINS: int = 10

# Small epsilon to avoid log(0) division
EPSILON: float = 1e-10

# Alert levels
ALERT_NONE: str = "NONE"
ALERT_WARNING: str = "WARNING"
ALERT_CRITICAL: str = "CRITICAL"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DriftReport:
    """Result of a single feature drift detection.

    Attributes:
        feature_name: Name of the feature being monitored.
        drift_score: Composite drift score (PSI-based).
        is_drifted: Whether the drift exceeds the configured threshold.
        alert_level: Severity level — NONE, WARNING, or CRITICAL.
        method: Detection method used (e.g. "psi", "ks_test").
        ks_statistic: Optional KS test statistic value.
        ks_p_value: Optional KS test p-value.
    """

    feature_name: str
    drift_score: float
    is_drifted: bool
    alert_level: str = ALERT_NONE
    method: str = "psi"
    ks_statistic: float | None = None
    ks_p_value: float | None = None


# ---------------------------------------------------------------------------
# PSI computation
# ---------------------------------------------------------------------------


def compute_psi(expected: np.ndarray, actual: np.ndarray, n_bins: int = PSI_DEFAULT_BINS) -> float:
    """Compute Population Stability Index between expected and actual distributions.

    PSI = sum over bins of (actual_prop_i - expected_prop_i) * ln(actual_prop_i / expected_prop_i)

    Bins are computed from the combined min/max range of both arrays.
    Empty bins in either distribution get a small epsilon to avoid log(0).

    Args:
        expected: Reference (baseline) distribution values.
        actual: Current (observed) distribution values.
        n_bins: Number of equal-width bins (default 10).

    Returns:
        PSI score (>= 0). Convention: < 0.10 = no drift,
        0.10-0.25 = moderate drift, > 0.25 = significant drift.

    Raises:
        ValueError: If either array is empty.
    """
    if len(expected) == 0:
        raise ValueError("expected array is empty")
    if len(expected) == 0:
        raise ValueError("expected array is empty")
    if len(actual) == 0:
        raise ValueError("actual array is empty")

    combined_min = float(np.min(np.concatenate([expected, actual])))
    combined_max = float(np.max(np.concatenate([expected, actual])))

    # Handle degenerate case where all values are identical
    if combined_max == combined_min:
        combined_max = combined_min + 1.0

    bin_edges = np.linspace(combined_min, combined_max, n_bins + 1)

    expected_counts, _ = np.histogram(expected, bins=bin_edges)
    actual_counts, _ = np.histogram(actual, bins=bin_edges)

    # Convert to proportions
    expected_props = expected_counts.astype(np.float64) / len(expected)
    actual_props = actual_counts.astype(np.float64) / len(actual)

    # Clamp to avoid log(0)
    expected_props = np.clip(expected_props, EPSILON, 1.0)
    actual_props = np.clip(actual_props, EPSILON, 1.0)

    # PSI = sum (actual - expected) * ln(actual / expected)
    psi = np.sum((actual_props - expected_props) * np.log(actual_props / expected_props))

    return float(psi)


# ---------------------------------------------------------------------------
# KS test
# ---------------------------------------------------------------------------


def compute_ks_test(reference: np.ndarray, current: np.ndarray) -> tuple[float, float]:
    """Compute two-sample Kolmogorov-Smirnov test between reference and current.

    The KS statistic measures the maximum absolute difference between the
    two empirical CDFs. A small p-value suggests the two distributions differ.

    Args:
        reference: Reference (baseline) distribution values.
        current: Current (observed) distribution values.

    Returns:
        Tuple of (ks_statistic, p_value).

    Raises:
        ValueError: If either array is empty.
    """
    if len(reference) == 0:
        raise ValueError("reference array is empty")
    if len(current) == 0:
        raise ValueError("current array is empty")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        stat, p_value = ks_2samp(reference, current)

    return float(stat), float(p_value)


# ---------------------------------------------------------------------------
# Alert level assignment
# ---------------------------------------------------------------------------


def _assign_alert_level(psi: float) -> str:
    """Assign alert level based on PSI score."""
    if psi < PSI_NO_DRIFT:
        return ALERT_NONE
    elif psi < PSI_MODERATE_DRIFT:
        return ALERT_WARNING
    else:
        return ALERT_CRITICAL


# ---------------------------------------------------------------------------
# FeatureDriftDetector
# ---------------------------------------------------------------------------


class FeatureDriftDetector:
    """Detects feature drift between expected and current distributions.

    Supports two detection methods:
    - "psi": Population Stability Index (default).
    - "ks_test": Kolmogorov-Smirnov two-sample test.

    Typical usage::

        detector = FeatureDriftDetector()
        report = detector.detect_drift(
            name="log_return_4h",
            expected_stats=baseline_array,
            current_stats=current_array,
            threshold=0.1,
        )
        if report.is_drifted:
            logger.warning("Drift detected for %s: score=%.4f", report.feature_name, report.drift_score)
    """

    def __init__(self, default_method: str = "psi"):
        """Initialize the detector.

        Args:
            default_method: Detection method — "psi" or "ks_test".

        Raises:
            ValueError: If method is not recognized.
        """
        if default_method not in ("psi", "ks_test"):
            raise ValueError(f"Unsupported method: '{default_method}'. Use 'psi' or 'ks_test'.")
        self._default_method = default_method

    def detect_drift(
        self,
        name: str,
        expected_stats: np.ndarray,
        current_stats: np.ndarray,
        threshold: float = PSI_NO_DRIFT,
        method: str | None = None,
    ) -> DriftReport:
        """Detect whether a feature has drifted between expected and current.

        Args:
            name: Feature name (for reporting).
            expected_stats: Reference/baseline distribution values.
            current_stats: Current/observed distribution values.
            threshold: Drift threshold. When using PSI (default), the
                       industry convention is 0.10. Lower values are more
                       sensitive. For KS test, this is the p-value threshold
                       below which drift is flagged.
            method: Override the default detection method for this call.

        Returns:
            DriftReport with score and alert level.
        """
        method = method or self._default_method

        if method == "ks_test":
            stat, p_value = compute_ks_test(expected_stats, current_stats)
            is_drifted = p_value < threshold
            # Use the KS statistic as the drift score (0-1 scale)
            drift_score = stat
            alert = ALERT_CRITICAL if is_drifted else ALERT_NONE
            return DriftReport(
                feature_name=name,
                drift_score=drift_score,
                is_drifted=is_drifted,
                alert_level=alert,
                method=method,
                ks_statistic=stat,
                ks_p_value=p_value,
            )

        # Default: PSI method
        psi = compute_psi(expected_stats, current_stats)
        is_drifted = psi >= threshold
        alert = _assign_alert_level(psi)
        return DriftReport(
            feature_name=name,
            drift_score=psi,
            is_drifted=is_drifted,
            alert_level=alert,
            method="psi",
        )
