"""Label quality monitoring — tracks label stability and regression.

Monitors the quality of labels produced by the simulation/label pipeline
over time. Detects when label distributions shift, which can indicate
regime changes in market behavior or data pipeline issues.

This module is simulation-cost-aware: it never invents labels or
bypasses the simulation authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default threshold for regression detection
REGRESSION_THRESHOLD: float = 0.15

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LabelQualityReport:
    """Assessment of label quality between a reference and current period.

    Attributes:
        stability_score: 0-1 score where 1 = perfectly stable (no change).
        regression_detected: True if label quality has regressed.
        magnitude: Magnitude of the quality change (0+), directionless.
        n_current: Number of label samples in the current period.
        n_reference: Number of label samples in the reference period.
        current_mean: Mean of the current label quality metric.
        reference_mean: Mean of the reference label quality metric.
        details: Optional dict with additional diagnostics.
    """

    stability_score: float
    regression_detected: bool
    magnitude: float
    n_current: int
    n_reference: int
    current_mean: float
    reference_mean: float
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LabelQualityMonitor
# ---------------------------------------------------------------------------


class LabelQualityMonitor:
    """Monitor label quality stability over time.

    Compares label metrics (e.g. long_R_net, short_R_net, cost impact)
    between a reference period and the current period. Detects if label
    distributions have shifted significantly, which may indicate:

    - Market regime change (legitimate signal)
    - Label pipeline degradation (data quality issue)
    - Label schema drift (contract violation)
    """

    def __init__(self, regression_threshold: float = REGRESSION_THRESHOLD):
        """Initialize the label quality monitor.

        Args:
            regression_threshold: Threshold for the regression metric.
                                  Lower = more sensitive to regression.
        """
        self._threshold = regression_threshold

    def compute_label_quality_regression(
        self,
        current: np.ndarray,
        reference: np.ndarray,
    ) -> LabelQualityReport:
        """Compare current label metrics to reference and detect regression.

        Uses a combined metric of distribution shift (via normalized mean
        absolute difference) and variance change to quantify quality
        regression.

        Args:
            current: Current period label values (e.g. R_net).
            reference: Reference/baseline period label values.

        Returns:
            LabelQualityReport with stability score and regression verdict.

        Raises:
            ValueError: If either array is empty.
        """
        if len(current) == 0:
            raise ValueError("current array is empty")
        if len(reference) == 0:
            raise ValueError("reference array is empty")

        # Basic statistics
        current_mean = float(np.mean(current))
        reference_mean = float(np.mean(reference))

        # Scale for relative difference computation
        scale = max(abs(reference_mean), 1e-8)

        # Normalized mean shift component (0 = no shift)
        mean_shift = abs(current_mean - reference_mean) / scale

        # Variance ratio component (1 = same variance)
        current_var = float(np.var(current))
        reference_var = float(np.var(reference))
        var_scale = max(reference_var, 1e-8)
        var_ratio = current_var / var_scale if var_scale > 0 else 1.0

        # Clamp to reasonable range
        if var_ratio < 0.01:
            var_discrepancy = 1.0  # extreme variance collapse
        elif var_ratio > 10.0:
            var_discrepancy = 1.0  # extreme variance expansion
        else:
            var_discrepancy = abs(var_ratio - 1.0)

        # Combined magnitude: weighted sum of mean shift and variance discrepancy
        magnitude = 0.6 * mean_shift + 0.4 * var_discrepancy

        # Stability score: 1 = perfect, 0 = completely different
        stability_score = max(0.0, 1.0 - min(magnitude, 1.0))

        regression_detected = magnitude > self._threshold

        return LabelQualityReport(
            stability_score=stability_score,
            regression_detected=regression_detected,
            magnitude=magnitude,
            n_current=len(current),
            n_reference=len(reference),
            current_mean=current_mean,
            reference_mean=reference_mean,
            details={
                "mean_shift": mean_shift,
                "var_discrepancy": var_discrepancy,
                "current_var": current_var,
                "reference_var": reference_var,
            },
        )
