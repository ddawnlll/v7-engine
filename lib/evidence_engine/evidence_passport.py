"""
Evidence Passport — shared data contract between AlphaForge and V7.

AlphaForge produces it (``EvidencePassportBuilder.from_wfv_results``),
V7 consumes it (via ``GateMapper`` / ``DecisionEngine``).

Passport schema is versioned by ``passport_id`` (UUID v4), not by a
separate version field — consumers MUST treat every passport as
potentially stale and re-validate before making implementation decisions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from lib.evidence_engine.baselines import BaselineResult
from lib.evidence_engine.hard_caps import HardCapResult


# ---------------------------------------------------------------------------
# Passport
# ---------------------------------------------------------------------------


@dataclass
class EvidencePassport:
    """Canonical evidence artifact passed from AlphaForge to V7.

    Every field is populated by the builder; consumers read don't mutate.
    """

    passport_id: str
    candidate_id: str
    mode: str
    created_at: str

    # -- Core metrics (flattened key-value, e.g. what ``collect_metrics`` emits)
    metrics: dict = field(default_factory=dict)

    # -- Claim statuses (claim_type -> PASSED / FAILED / BLOCKED)
    claim_statuses: dict[str, str] = field(default_factory=dict)

    # -- Baseline comparison (baseline_name -> BaselineResult)
    baselines: dict[str, BaselineResult] = field(default_factory=dict)

    # -- Hard cap evaluation
    hard_caps: HardCapResult = field(default_factory=HardCapResult)

    # -- V7 gate mapping (gate_name -> PASSED / FAILED / NOT_RUN)
    v7_gates: dict[str, str] = field(default_factory=dict)

    # -- Hypothesis cards this passport supports
    hypothesis_refs: list[str] = field(default_factory=list)

    # -- Evidence trail
    trial_count: int = 0
    data_summary: dict = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class EvidencePassportBuilder:
    """Factory for ``EvidencePassport`` from training pipeline output."""

    @staticmethod
    def from_wfv_results(wfv_results: dict, mode: str) -> EvidencePassport:
        """Build a passport from walk-forward validation results.

        Parameters
        ----------
        wfv_results:
            Dict with keys ``metrics`` (aggregated output of
            ``collect_metrics``), ``per_fold_results`` (list of per-fold
            dicts), and optionally ``candidate_id`` and ``hypothesis_refs``.
        mode:
            Trading mode string (e.g. ``"SWING"``, ``"SCALP"``).

        Returns
        -------
        EvidencePassport
        """
        metrics: dict = wfv_results.get("metrics", {})
        per_fold: list[dict] = wfv_results.get("per_fold_results", [])

        passport = EvidencePassport(
            passport_id=str(uuid.uuid4()),
            candidate_id=wfv_results.get("candidate_id", "unknown"),
            mode=mode,
            created_at=datetime.now(timezone.utc).isoformat(),
            metrics=metrics,
            data_summary={
                "n_samples": metrics.get("n_samples", 0),
                "n_folds": metrics.get("n_folds", len(per_fold)),
                "feature_count": metrics.get("feature_count", 0),
                "exposure_pct": metrics.get("exposure_pct", 0.0),
                "total_active_trades": metrics.get("total_active_trades", 0),
                "low_conf_rate_pct": metrics.get("low_conf_rate_pct", 0.0),
            },
            limitations=EvidencePassportBuilder._derive_limitations(
                metrics, per_fold,
            ),
        )

        # Attach hypothesis refs if supplied
        hypothesis_refs: list[str] | None = wfv_results.get("hypothesis_refs")
        if hypothesis_refs:
            passport.hypothesis_refs = hypothesis_refs

        return passport

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate(passport: EvidencePassport) -> list[str]:
        """Return a list of warnings about a passport's completeness.

        An empty list means the passport is structurally sound.
        """
        warnings: list[str] = []

        if not passport.passport_id:
            warnings.append("passport_id is empty")
        if not passport.candidate_id:
            warnings.append("candidate_id is empty")
        if not passport.mode:
            warnings.append("mode is empty")
        if not passport.metrics:
            warnings.append(
                "metrics is empty — passport has no performance data",
            )
        n_folds = passport.metrics.get("n_folds", 0) if passport.metrics else 0
        if n_folds < 2:
            warnings.append(
                f"only {n_folds} fold(s) — insufficient for reliable estimation",
            )
        accuracy = passport.metrics.get("accuracy", 0) if passport.metrics else 0
        if accuracy == 0:
            warnings.append("accuracy is 0 — training may have failed")

        # Trial sanity
        if passport.trial_count < 0:
            warnings.append("trial_count is negative")

        return warnings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_limitations(
        metrics: dict,
        per_fold: list[dict],
    ) -> list[str]:
        limitations: list[str] = []

        pbo_risk = metrics.get("pbo_risk", "UNKNOWN")
        if pbo_risk == "HIGH":
            limitations.append(
                "High PBO risk — WFV results may overstate real performance",
            )
        overfit_gap = metrics.get("overfit_gap", 0.0)
        if overfit_gap > 0.10:
            limitations.append(
                f"Large overfit gap ({overfit_gap:.2f}) — train/OOS divergence",
            )
        net_exp = metrics.get("net_expectancy_r", 0.0)
        if net_exp <= 0:
            limitations.append(
                "Non-positive net expectancy — not profitable after costs",
            )
        n_folds = len(per_fold)
        if 0 < n_folds < 4:
            limitations.append(
                "Few WFV folds — results may not generalize",
            )

        return limitations
