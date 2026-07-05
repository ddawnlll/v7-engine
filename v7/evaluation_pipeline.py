"""
V7 Phase 8 — Evaluation pipeline.

Components:
  - CandidateComparisonEngine: candidate vs baseline comparison
  - WalkForwardReview: per-model-scope walk-forward review
  - CalibrationReview: calibration quality review
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _default_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── CandidateComparisonEngine ──────────────────────────────────────────────


@dataclass(frozen=True)
class CandidateComparisonReport:
    """Report comparing candidate vs baseline model performance.

    Attributes:
        candidate_label: Label identifying the candidate.
        baseline_label: Label identifying the baseline.
        metric_deltas: Dict of metric_name -> delta (candidate - baseline).
        regression_count: Number of metrics showing regression.
        improvement_count: Number of metrics showing improvement.
        overall_verdict: 'PROMOTE', 'HOLD', or 'REJECT'.
        detail: Human-readable comparison summary.
        timestamp: When the comparison was performed.
    """

    candidate_label: str = ""
    baseline_label: str = ""
    metric_deltas: dict[str, float] = field(default_factory=dict)
    regression_count: int = 0
    improvement_count: int = 0
    overall_verdict: str = "HOLD"
    detail: str = ""
    timestamp: str = ""


class CandidateComparisonEngine:
    """Compares a candidate model against its baseline.

    Evaluates metric deltas and determines whether the candidate
    should be promoted, held, or rejected.
    """

    def __init__(self) -> None:
        self._results: list[CandidateComparisonReport] = []

    def compare(
        self,
        candidate_metrics: dict[str, float],
        baseline_metrics: dict[str, float],
        *,
        candidate_label: str = "",
        baseline_label: str = "baseline",
        thresholds: dict[str, float] | None = None,
    ) -> CandidateComparisonReport:
        """Compare candidate vs baseline metrics.

        Args:
            candidate_metrics: Dict of metric_name -> value for candidate.
            baseline_metrics: Dict of metric_name -> value for baseline.
            candidate_label: Label for the candidate.
            baseline_label: Label for the baseline.
            thresholds: Dict of metric_name -> minimum improvement threshold.
                        Metrics below this threshold count as regression.
                        Default: 0.0 for all metrics (any regression counts).

        Returns:
            A CandidateComparisonReport with deltas and verdict.
        """
        thresholds = thresholds or {}
        deltas: dict[str, float] = {}
        regression_count = 0
        improvement_count = 0
        regression_details: list[str] = []
        improvement_details: list[str] = []

        all_metrics = set(candidate_metrics.keys()) | set(baseline_metrics.keys())
        for metric in sorted(all_metrics):
            cand_val = candidate_metrics.get(metric, 0.0)
            base_val = baseline_metrics.get(metric, 0.0)
            delta = cand_val - base_val
            deltas[metric] = round(delta, 4)

            threshold = thresholds.get(metric, 0.0)
            if delta < -abs(threshold):
                regression_count += 1
                regression_details.append(f"{metric}: {base_val:.4f} -> {cand_val:.4f} ({delta:+.4f})")
            elif delta > abs(threshold):
                improvement_count += 1
                improvement_details.append(f"{metric}: {base_val:.4f} -> {cand_val:.4f} ({delta:+.4f})")

        # Determine verdict
        if regression_count > 0:
            if regression_count > improvement_count:
                overall_verdict = "REJECT"
            else:
                overall_verdict = "HOLD"
        else:
            overall_verdict = "PROMOTE"

        detail_parts: list[str] = []
        if regression_details:
            detail_parts.append(f"Regressions ({regression_count}): " + "; ".join(regression_details[:5]))
        if improvement_details:
            detail_parts.append(f"Improvements ({improvement_count}): " + "; ".join(improvement_details[:5]))
        if not regression_details and not improvement_details:
            detail_parts.append("No significant metric changes")

        detail = " | ".join(detail_parts)

        report = CandidateComparisonReport(
            candidate_label=candidate_label,
            baseline_label=baseline_label,
            metric_deltas=deltas,
            regression_count=regression_count,
            improvement_count=improvement_count,
            overall_verdict=overall_verdict,
            detail=detail,
            timestamp=_default_ts(),
        )
        self._results.append(report)
        return report

    def get_history(self) -> list[CandidateComparisonReport]:
        """Get all comparison reports."""
        return list(self._results)


# ── WalkForwardReview ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class WalkForwardReviewReport:
    """Report of walk-forward review for a single model scope.

    Attributes:
        model_scope: The model scope reviewed.
        fold_count: Number of folds in the walk-forward.
        expectancy_values: List of expectancy R values per fold.
        median_expectancy: Median expectancy R across folds.
        min_expectancy: Minimum expectancy R across folds.
        max_expectancy: Maximum expectancy R across folds.
        fold_consistency: Coefficient of variation across folds.
        negative_fold_count: Number of folds with negative expectancy.
        verdict: 'PASS', 'HOLD', or 'FAIL'.
        detail: Human-readable review summary.
    """

    model_scope: str = ""
    fold_count: int = 0
    expectancy_values: list[float] = field(default_factory=list)
    median_expectancy: float = 0.0
    min_expectancy: float = 0.0
    max_expectancy: float = 0.0
    fold_consistency: float = 0.0
    negative_fold_count: int = 0
    verdict: str = "HOLD"
    detail: str = ""


class WalkForwardReview:
    """Reviews walk-forward results for a model scope.

    Evaluates fold consistency, identifies negative folds,
    and produces a PASS/HOLD/FAIL verdict.
    """

    def __init__(self, min_folds: int = 6) -> None:
        self._min_folds = min_folds
        self._reviews: list[WalkForwardReviewReport] = []

    def review(
        self,
        model_scope: str,
        fold_results: list[dict[str, Any]],
        *,
        min_expectancy_r: float = 0.15,
        max_negative_fold_rate: float = 0.2,
    ) -> WalkForwardReviewReport:
        """Review walk-forward results for a model scope.

        Args:
            model_scope: The model scope to review.
            fold_results: List of fold result dicts. Each should have:
                          - fold_index: int
                          - expectancy_r: float
                          - trade_count: int (optional)
            min_expectancy_r: Minimum acceptable expectancy R per fold median.
            max_negative_fold_rate: Max fraction of folds with negative expectancy.

        Returns:
            A WalkForwardReviewReport with review verdict.
        """
        fold_count = len(fold_results)
        expectancy_values = [
            f.get("expectancy_r", 0.0)
            for f in fold_results
            if f.get("expectancy_r") is not None
        ]

        if not expectancy_values:
            report = WalkForwardReviewReport(
                model_scope=model_scope,
                fold_count=fold_count,
                verdict="FAIL",
                detail="No expectancy values found in fold results",
            )
            self._reviews.append(report)
            return report

        sorted_vals = sorted(expectancy_values)
        n = len(sorted_vals)
        median_exp = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
        min_exp = min(expectancy_values)
        max_exp = max(expectancy_values)

        mean_exp = sum(expectancy_values) / n
        std_exp = (
            (sum((v - mean_exp) ** 2 for v in expectancy_values) / n) ** 0.5
            if n > 1
            else 0.0
        )
        consistency = std_exp / max(abs(mean_exp), 0.001) if mean_exp != 0 else 0.0

        negative_count = sum(1 for v in expectancy_values if v < 0)
        negative_fold_rate = negative_count / max(n, 1)

        # Determine verdict
        issues: list[str] = []
        if n < self._min_folds:
            issues.append(f"fold_count={n} < minimum {self._min_folds}")

        if median_exp < min_expectancy_r:
            issues.append(f"median_expectancy={median_exp:.4f} < {min_expectancy_r}")

        if negative_fold_rate > max_negative_fold_rate:
            issues.append(
                f"negative_fold_rate={negative_fold_rate:.1%} > {max_negative_fold_rate:.0%}"
            )

        if negative_count > 0:
            issues.append(f"{negative_count} fold(s) have negative expectancy")

        if issues:
            verdict = "FAIL"
        else:
            verdict = "PASS"

        detail_parts = [
            f"folds={n}",
            f"median_exp={median_exp:.4f}",
            f"consistency={consistency:.4f}",
            f"negative_folds={negative_count}",
        ]
        if issues:
            detail_parts.append("FAIL: " + "; ".join(issues))
        else:
            detail_parts.append("ALL CHECKS PASSED")

        report = WalkForwardReviewReport(
            model_scope=model_scope,
            fold_count=n,
            expectancy_values=[round(v, 4) for v in expectancy_values],
            median_expectancy=round(median_exp, 4),
            min_expectancy=round(min_exp, 4),
            max_expectancy=round(max_exp, 4),
            fold_consistency=round(consistency, 4),
            negative_fold_count=negative_count,
            verdict=verdict,
            detail=" | ".join(detail_parts),
        )
        self._reviews.append(report)
        return report

    def get_reviews(self) -> list[WalkForwardReviewReport]:
        """Get all walk-forward reviews."""
        return list(self._reviews)


# ── CalibrationReview ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalibrationReviewReport:
    """Report of calibration quality review.

    Attributes:
        ece: Expected Calibration Error.
        mce: Maximum Calibration Error.
        reliability: Overall reliability score.
        bucket_count: Number of confidence buckets.
        bucket_details: Dict of bucket_name -> dict with accuracy, confidence, count.
        calibration_verdict: 'PASS', 'HOLD', or 'FAIL'.
        detail: Human-readable calibration summary.
    """

    ece: float = 0.0
    mce: float = 0.0
    reliability: float = 0.0
    bucket_count: int = 0
    bucket_details: dict[str, dict[str, float]] = field(default_factory=dict)
    calibration_verdict: str = "HOLD"
    detail: str = ""


class CalibrationReview:
    """Reviews calibration quality of a model.

    Evaluates ECE, MCE, per-bucket reliability, and produces
    a calibration verdict.
    """

    def __init__(self) -> None:
        self._reviews: list[CalibrationReviewReport] = []

    def review(
        self,
        calibration_metrics: dict[str, Any],
        *,
        ece_threshold: float = 0.10,
        mce_threshold: float = 0.20,
    ) -> CalibrationReviewReport:
        """Review calibration metrics.

        Args:
            calibration_metrics: Dict with calibration metrics:
                - ece: Expected Calibration Error (float)
                - mce: Maximum Calibration Error (float, optional)
                - reliability: Overall reliability (float, optional)
                - buckets: Dict of bucket_name -> {accuracy, confidence, count}
            ece_threshold: Maximum acceptable ECE.
            mce_threshold: Maximum acceptable MCE.

        Returns:
            A CalibrationReviewReport with verdict.
        """
        ece = calibration_metrics.get("ece", 0.0)
        mce = calibration_metrics.get("mce", 0.0)
        reliability = calibration_metrics.get("reliability", 1.0)

        buckets = calibration_metrics.get("buckets", {})
        bucket_count = len(buckets) if isinstance(buckets, dict) else 0

        bucket_details: dict[str, dict[str, float]] = {}
        for bname, bdata in (buckets or {}).items():
            if isinstance(bdata, dict):
                bucket_details[bname] = {
                    "accuracy": bdata.get("accuracy", 0.0),
                    "confidence": bdata.get("confidence", 0.0),
                    "count": float(bdata.get("count", 0)),
                }

        # Determine verdict
        issues: list[str] = []
        if ece > ece_threshold:
            issues.append(f"ECE={ece:.4f} > {ece_threshold}")
        if mce > mce_threshold:
            issues.append(f"MCE={mce:.4f} > {mce_threshold}")
        if reliability < 0.8:
            issues.append(f"reliability={reliability:.4f} < 0.8")

        if issues:
            calibration_verdict = "FAIL"
        else:
            calibration_verdict = "PASS"

        detail_parts = [
            f"ECE={ece:.4f}",
            f"MCE={mce:.4f}",
            f"reliability={reliability:.4f}",
            f"buckets={bucket_count}",
        ]
        if issues:
            detail_parts.append("FAIL: " + "; ".join(issues))
        else:
            detail_parts.append("ALL CHECKS PASSED")

        report = CalibrationReviewReport(
            ece=round(ece, 4),
            mce=round(mce, 4),
            reliability=round(reliability, 4),
            bucket_count=bucket_count,
            bucket_details=bucket_details,
            calibration_verdict=calibration_verdict,
            detail=" | ".join(detail_parts),
        )
        self._reviews.append(report)
        return report

    def get_reviews(self) -> list[CalibrationReviewReport]:
        """Get all calibration reviews."""
        return list(self._reviews)
