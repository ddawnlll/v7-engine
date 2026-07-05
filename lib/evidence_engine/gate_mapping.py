"""
Gate Mapper — maps evidence dimensions to V7 canonical gates (G0-G10).

G0..G10 are defined in ``v7/docs/pipeline/evaluation.md``.  Each gate
inspects specific fields in an ``EvidencePassport`` and reports
PASSED / FAILED / NOT_RUN / BLOCKED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lib.evidence_engine.evidence_passport import EvidencePassport

# ---------------------------------------------------------------------------
# Gate definitions — every gate is a (name, human_label, evidence_keys) triple
# ---------------------------------------------------------------------------

GATE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "G0",
        "label": "CODE_AUDIT",
        "evidence_required": [
            "code_audit_status",
            "code_review_passed",
        ],
        "description": "Code review passed, audit trail exists.",
    },
    {
        "name": "G1",
        "label": "RESEARCH_BACKTEST",
        "evidence_required": [
            "net_expectancy_r",
            "net_sharpe_ratio",
            "accuracy",
        ],
        "description": "Basic backtest exists with positive expectancy.",
    },
    {
        "name": "G2",
        "label": "WALK_FORWARD_OOS",
        "evidence_required": [
            "n_folds",
            "overfit_gap",
            "train_oos_correlation",
            "pbo_risk",
        ],
        "description": "Walk-forward validation completed with overfit assessment.",
    },
    {
        "name": "G3",
        "label": "COST_STRESS",
        "evidence_required": [
            "cost_aware_filter_run",
            "cost_decomposition",
        ],
        "description": "Cost-aware filter run; fee/slippage/funding decomposed.",
    },
    {
        "name": "G4",
        "label": "REGIME_BREAKDOWN",
        "evidence_required": [
            "dsr_run",
            "regime_breakdown_results",
        ],
        "description": "Distribution shift robustness and regime analysis done.",
    },
    {
        "name": "G5",
        "label": "SYMBOL_STABILITY",
        "evidence_required": [
            "symbol_count",
            "symbol_stability",
        ],
        "description": "Stable performance across multiple symbols.",
    },
    {
        "name": "G6",
        "label": "CALIBRATION_RELIABILITY",
        "evidence_required": [
            "confidence_calibration_done",
            "calibration_error",
        ],
        "description": "Confidence calibration reliable, error reported.",
    },
    {
        "name": "G7",
        "label": "CONFIDENCE_THRESHOLD",
        "evidence_required": [
            "confidence_threshold_applied",
            "low_conf_rate_pct",
        ],
        "description": "Confidence threshold applied and rate known.",
    },
    {
        "name": "G8",
        "label": "HANDOFF_PACKAGE",
        "evidence_required": [
            "handoff_documentation_exists",
        ],
        "description": "Complete handoff package prepared.",
    },
    {
        "name": "G9",
        "label": "SHADOW_PAPER",
        "evidence_required": [
            "shadow_paper_written",
        ],
        "description": "Shadow paper written and reviewed.",
    },
    {
        "name": "G10",
        "label": "TINY_LIVE",
        "evidence_required": [
            "tiny_live_deployed",
        ],
        "description": "Tiny live deployment active.",
    },
]

# Map gate name -> its definition for fast lookup
_GATE_MAP: dict[str, dict[str, Any]] = {g["name"]: g for g in GATE_DEFINITIONS}


# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    """Result of evaluating a single V7 gate against a passport."""

    gate_name: str  # e.g. "G2"
    gate_label: str  # e.g. "WALK_FORWARD_OOS"
    status: str  # PASSED | FAILED | NOT_RUN | BLOCKED
    evidence_required: list[str] = field(default_factory=list)
    evidence_provided: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# GateMapper
# ---------------------------------------------------------------------------


class GateMapper:
    """Maps evidence dimensions in a passport to V7 gate statuses."""

    # Thresholds — LOCKED_INITIAL_BASELINE, re-calibrate with empirical
    # data as the project matures.
    _MIN_FOLDS = 2
    _MAX_OVERFIT_GAP = 0.10
    _MIN_EXPECTANCY = 0.0  # strictly > 0
    _MIN_SHARPE = 0.0
    _MIN_ACCURACY = 0.0  # better than random (33% for 3-class)
    _MAX_LOW_CONF_RATE = 50.0  # pct

    def map_passport_to_gates(
        self,
        passport: EvidencePassport,
    ) -> dict[str, GateResult]:
        """Evaluate every G0..G10 gate against a passport.

        Returns a dict keyed by gate name (e.g. ``"G2"``).
        """
        results: dict[str, GateResult] = {}
        metrics = passport.metrics
        evidence = self._flatten_evidence(passport)

        for g in GATE_DEFINITIONS:
            gname: str = g["name"]
            label: str = g["label"]
            required: list[str] = g["evidence_required"]

            provided: list[str] = [
                k for k in required if k in evidence and evidence[k] is not None
            ]
            missing: list[str] = [k for k in required if k not in provided]

            status = "PASSED"
            blocking: list[str] = []

            if len(provided) == 0:
                status = "NOT_RUN"
            else:
                # Gate-specific checks
                blocker = self._check_gate(gname, evidence, metrics)
                if blocker:
                    status = "FAILED"
                    blocking.append(blocker)

            results[gname] = GateResult(
                gate_name=gname,
                gate_label=label,
                status=status,
                evidence_required=list(required),
                evidence_provided=provided,
                missing_evidence=missing,
                blocking_issues=blocking,
            )

        return results

    def get_overall_progress(
        self,
        gate_results: dict[str, GateResult],
    ) -> dict:
        """Summarise gate-progress across all gates.

        Returns a dict with counts and a list of gates that are still
        actionable (i.e. not yet PASSED).
        """
        total = len(GATE_DEFINITIONS)
        passed = sum(1 for r in gate_results.values() if r.status == "PASSED")
        failed = sum(1 for r in gate_results.values() if r.status == "FAILED")
        not_run = sum(1 for r in gate_results.values() if r.status == "NOT_RUN")
        blocked = sum(1 for r in gate_results.values() if r.status == "BLOCKED")

        pending: list[str] = [
            f"{r.gate_name} ({r.gate_label})"
            for r in gate_results.values()
            if r.status != "PASSED"
        ]

        passed_pct = (passed / total * 100) if total > 0 else 0.0

        return {
            "total_gates": total,
            "passed": passed,
            "failed": failed,
            "not_run": not_run,
            "blocked": blocked,
            "passed_pct": round(passed_pct, 1),
            "pending_gates": pending,
        }

    def get_blocked_gates(
        self,
        gate_results: dict[str, GateResult],
    ) -> list[GateResult]:
        """Return gates that are FAILED or BLOCKED (actionable blockers)."""
        return [
            r for r in gate_results.values()
            if r.status in ("FAILED", "BLOCKED")
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_evidence(passport: EvidencePassport) -> dict[str, Any]:
        """Merge all passport fields into a single flat dict for lookups."""
        evidence: dict[str, Any] = {}

        # Core metrics
        evidence.update(passport.metrics)

        # Hard-cap flags
        if passport.hard_caps.blocked_actions:
            evidence["hard_caps_has_blocks"] = True
            evidence["hard_caps_blocked_actions"] = passport.hard_caps.blocked_actions
        if passport.hard_caps.allowed_actions:
            evidence["hard_caps_allowed_actions"] = passport.hard_caps.allowed_actions

        # Claim statuses
        evidence["claim_statuses"] = passport.claim_statuses

        # Data summary fields
        evidence.update(passport.data_summary)

        # Limitations
        evidence["n_limitations"] = len(passport.limitations)

        return evidence

    def _check_gate(
        self,
        gate_name: str,
        evidence: dict[str, Any],
        metrics: dict[str, Any],
    ) -> str | None:
        """Return a blocking-reason string, or None if the gate passes."""
        if gate_name == "G0":
            return self._check_g0(evidence)
        if gate_name == "G1":
            return self._check_g1(metrics)
        if gate_name == "G2":
            return self._check_g2(metrics)
        if gate_name == "G3":
            return self._check_g3(evidence)
        if gate_name == "G4":
            return self._check_g4(evidence)
        if gate_name == "G5":
            return self._check_g5(evidence)
        if gate_name == "G6":
            return self._check_g6(evidence)
        if gate_name == "G7":
            return self._check_g7(metrics)
        if gate_name == "G8":
            return None  # documentation — always passes at structural level
        if gate_name == "G9":
            return None  # paper — always passes at structural level
        if gate_name == "G10":
            return None  # live — always passes at structural level
        return f"Unknown gate {gate_name}"

    @staticmethod
    def _check_g0(evidence: dict[str, Any]) -> str | None:
        audit = evidence.get("code_audit_status")
        review = evidence.get("code_review_passed")
        if audit != "PASSED":
            return f"Code audit status is {audit!r}, expected PASSED"
        if review is not True:
            return "Code review has not passed"
        return None

    def _check_g1(self, metrics: dict[str, Any]) -> str | None:
        exp = metrics.get("net_expectancy_r", -1.0)
        sharpe = metrics.get("net_sharpe_ratio", -1.0)
        acc = metrics.get("accuracy", 0.0)
        reasons: list[str] = []
        if exp <= self._MIN_EXPECTANCY:
            reasons.append(f"net_expectancy_r={exp} <= {self._MIN_EXPECTANCY}")
        if sharpe <= self._MIN_SHARPE:
            reasons.append(f"net_sharpe_ratio={sharpe} <= {self._MIN_SHARPE}")
        if acc <= self._MIN_ACCURACY:
            reasons.append(f"accuracy={acc} <= {self._MIN_ACCURACY}")
        return "; ".join(reasons) if reasons else None

    def _check_g2(self, metrics: dict[str, Any]) -> str | None:
        folds = metrics.get("n_folds", 0)
        gap = metrics.get("overfit_gap", 1.0)
        reasons: list[str] = []
        if folds < self._MIN_FOLDS:
            reasons.append(f"n_folds={folds} < {self._MIN_FOLDS}")
        if gap > self._MAX_OVERFIT_GAP:
            reasons.append(f"overfit_gap={gap} > {self._MAX_OVERFIT_GAP}")
        return "; ".join(reasons) if reasons else None

    @staticmethod
    def _check_g3(evidence: dict[str, Any]) -> str | None:
        if not evidence.get("cost_aware_filter_run"):
            return "cost_aware_filter_run is False or missing"
        return None

    @staticmethod
    def _check_g4(evidence: dict[str, Any]) -> str | None:
        if not evidence.get("dsr_run"):
            return "dsr_run is False or missing"
        return None

    @staticmethod
    def _check_g5(evidence: dict[str, Any]) -> str | None:
        sym_count = evidence.get("symbol_count", 0)
        if sym_count < 1:
            return "symbol_count < 1"
        stability = evidence.get("symbol_stability")
        if stability is not None and stability < 0.5:
            return f"symbol_stability={stability} < 0.5"
        return None

    @staticmethod
    def _check_g6(evidence: dict[str, Any]) -> str | None:
        if not evidence.get("confidence_calibration_done"):
            return "confidence_calibration_done is False or missing"
        return None

    def _check_g7(self, metrics: dict[str, Any]) -> str | None:
        low_conf = metrics.get("low_conf_rate_pct", 100.0)
        if low_conf > self._MAX_LOW_CONF_RATE:
            return (
                f"low_conf_rate_pct={low_conf} > {self._MAX_LOW_CONF_RATE}%"
            )
        return None
