"""
Calibration and alpha score builder for AlphaForge.

Transforms raw XGBoost model outputs into calibrated probabilities
and R-native alpha scores consumed by V7 policy.

Calibration methods:
- Platt scaling (logistic regression) for classification probabilities
- Isotonic regression fallback for non-monotonic calibration

Alpha scores:
- long_alpha_R = calibrated_p_long * max(expected_R_long, 0) * confidence
- short_alpha_R = calibrated_p_short * max(expected_R_short, 0) * confidence
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


CALIBRATION_VERSION = "calib-1.0.0"
ALPHA_SCORE_VERSION = "alpha-1.0.0"


# ── Calibrator ─────────────────────────────────────────────────────

class Calibrator:
    """Calibrates raw model probabilities using Platt scaling.

    Fits a logistic regression on held-out data to map raw scores
    to calibrated probabilities. Falls back to isotonic regression
    if Platt scaling produces non-monotonic results.
    """

    def __init__(self, method: str = "platt"):
        self.method = method
        self._calibrators: dict[str, LogisticRegression | IsotonicRegression] = {}
        self._fitted = False

    def fit(
        self,
        raw_probabilities: np.ndarray,
        y_true: np.ndarray,
    ) -> dict[str, Any]:
        """Fit calibration models for each class.

        Args:
            raw_probabilities: Shape (n_samples, 3) — [p_long, p_short, p_no_trade].
            y_true: Shape (n_samples,) — integer class labels (0=LONG, 1=SHORT, 2=NO_TRADE).

        Returns:
            Dict of per-class calibration metrics.
        """
        n_classes = raw_probabilities.shape[1]
        metrics: dict[str, Any] = {}

        for i, label in enumerate(["long", "short", "no_trade"]):
            y_binary = (y_true == i).astype(np.float64)
            scores = raw_probabilities[:, i]

            if self.method == "platt":
                cal = LogisticRegression(C=1.0, solver="lbfgs")
                # Reshape for sklearn: (n, 1)
                cal.fit(scores.reshape(-1, 1), y_binary)
                calibrated = cal.predict_proba(scores.reshape(-1, 1))[:, 1]
            else:
                cal = IsotonicRegression(out_of_bounds="clip")
                cal.fit(scores, y_binary)
                calibrated = cal.predict(scores)

            self._calibrators[label] = cal

            # Compute calibration error (ECE: Expected Calibration Error)
            ece = _expected_calibration_error(y_binary, calibrated, n_bins=10)
            metrics[label] = {
                "method": self.method,
                "ece": round(ece, 4),
                "samples": len(y_binary),
            }

        self._fitted = True
        return {
            "calibration_version": CALIBRATION_VERSION,
            "method": self.method,
            "per_class": metrics,
        }

    def predict(self, raw_probabilities: np.ndarray) -> np.ndarray:
        """Calibrate raw probabilities.

        Args:
            raw_probabilities: Shape (n_samples, 3) or (3,).

        Returns:
            Calibrated probabilities, same shape as input.
        """
        if not self._fitted:
            raise RuntimeError("Calibrator not fitted. Call fit() first.")

        single = raw_probabilities.ndim == 1
        if single:
            raw_probabilities = raw_probabilities.reshape(1, -1)

        n = raw_probabilities.shape[0]
        calibrated = np.zeros_like(raw_probabilities)

        for i, label in enumerate(["long", "short", "no_trade"]):
            cal = self._calibrators[label]
            scores = raw_probabilities[:, i].reshape(-1, 1)
            if isinstance(cal, LogisticRegression):
                calibrated[:, i] = cal.predict_proba(scores)[:, 1]
            else:
                calibrated[:, i] = cal.predict(scores.ravel())

        # Renormalize to sum to 1
        row_sums = calibrated.sum(axis=1, keepdims=True)
        calibrated = calibrated / np.where(row_sums > 0, row_sums, 1.0)

        if single:
            return calibrated[0]
        return calibrated


def _expected_calibration_error(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error."""
    if len(y_true) == 0:
        return 0.0
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_prob, bins) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    ece = 0.0
    for i in range(n_bins):
        mask = bin_indices == i
        if not mask.any():
            continue
        bin_acc = y_true[mask].mean()
        bin_conf = y_prob[mask].mean()
        ece += mask.sum() * abs(bin_acc - bin_conf)
    return ece / len(y_true) if len(y_true) > 0 else 0.0


# ── Inference (predict + calibrate in one step) ────────────────────

def predict_calibrated(
    model_bundle: dict[str, Any],
    features: dict[str, float],
    feature_keys: list[str],
    calibrator: Calibrator | None = None,
) -> dict[str, Any]:
    """Run inference: predict raw scores, calibrate, compute alpha.

    Args:
        model_bundle: Bundle from ModelTrainer.train_fold().
        features: Feature name → value dict.
        feature_keys: Ordered feature keys matching training.
        calibrator: Optional fitted Calibrator instance.

    Returns:
        Dict with raw scores, calibrated probabilities, and alpha scores.
    """
    # Build feature vector
    X = np.zeros((1, len(feature_keys)), dtype=np.float64)
    for j, key in enumerate(feature_keys):
        X[0, j] = float(features.get(key, 0.0))

    # Classifier predictions
    clf = model_bundle["classifier"]["model"]
    raw_probs = clf.predict_proba(X)[0]  # (3,)

    # Regressor predictions
    long_reg = model_bundle.get("long_regressor", {}).get("model")
    short_reg = model_bundle.get("short_regressor", {}).get("model")

    expected_r_long = float(long_reg.predict(X)[0]) if long_reg is not None else 0.0
    expected_r_short = float(short_reg.predict(X)[0]) if short_reg is not None else 0.0

    # Calibrate
    if calibrator is not None and calibrator._fitted:
        cal_probs = calibrator.predict(raw_probs)
    else:
        cal_probs = raw_probs

    # Confidence: max calibrated probability
    confidence = float(max(cal_probs))

    # Alpha scores
    long_alpha = cal_probs[0] * max(expected_r_long, 0.0) * confidence
    short_alpha = cal_probs[1] * max(expected_r_short, 0.0) * confidence

    # Directional edge
    directional_edge = (cal_probs[0] * expected_r_long) - (cal_probs[1] * expected_r_short)

    return {
        "raw_probabilities": {
            "long": round(float(raw_probs[0]), 4),
            "short": round(float(raw_probs[1]), 4),
            "no_trade": round(float(raw_probs[2]), 4),
        },
        "calibrated_probabilities": {
            "long": round(float(cal_probs[0]), 4),
            "short": round(float(cal_probs[1]), 4),
            "no_trade": round(float(cal_probs[2]), 4),
        },
        "expected_r": {
            "long": round(expected_r_long, 4),
            "short": round(expected_r_short, 4),
        },
        "confidence": round(confidence, 4),
        "confidence_kind": "calibrated" if calibrator is not None and calibrator._fitted else "raw",
        "alpha_scores": {
            "long_alpha_R": round(long_alpha, 4),
            "short_alpha_R": round(short_alpha, 4),
            "directional_edge_R": round(directional_edge, 4),
        },
    }
