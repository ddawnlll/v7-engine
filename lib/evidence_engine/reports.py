"""
Evidence report generation — converts decisions + passports into
human-readable or machine-readable formats.
"""

from __future__ import annotations

from typing import Any

from lib.evidence_engine.decisions import Decision
from lib.evidence_engine.evidence_passport import EvidencePassport


def evidence_report_to_dict(
    decision: Decision,
    passport: EvidencePassport,
) -> dict[str, Any]:
    """Serialize a decision + passport pair to a plain dict.

    This is the structured output consumed by downstream automation
    (e.g. the ACCP-YAML report generator, CI bots).
    """
    return {
        "report_type": "evidence_decision",
        "claim_id": decision.claim_id,
        "claim_type": decision.claim_type,
        "verdict": decision.verdict,
        "implementation_allowed": decision.implementation_allowed,
        "blocked_reason": decision.blocked_reason,
        "blocked_actions": decision.blocked_actions,
        "allowed_actions": decision.allowed_actions,
        "required_steps": decision.required_steps,
        "warnings": decision.warnings,
        "passport_id": passport.passport_id,
        "candidate_id": passport.candidate_id,
        "mode": passport.mode,
        "passport_metrics": {
            "accuracy": passport.metrics.get("accuracy"),
            "net_expectancy_r": passport.metrics.get("net_expectancy_r"),
            "net_sharpe_ratio": passport.metrics.get("net_sharpe_ratio"),
            "n_folds": passport.metrics.get("n_folds"),
            "overfit_gap": passport.metrics.get("overfit_gap"),
            "pbo_risk": passport.metrics.get("pbo_risk"),
        },
        "n_limitations": len(passport.limitations),
        "n_hypothesis_refs": len(passport.hypothesis_refs),
        "trial_count": passport.trial_count,
        "data_summary": dict(passport.data_summary),
        "limitations": list(passport.limitations),
    }


def evidence_report_to_markdown(
    decision: Decision,
    passport: EvidencePassport,
) -> str:
    """Generate a human-readable markdown report from a decision.

    Suitable for posting to PRs, issues, or console output.
    """
    verdict_icon = {
        "ACCEPTED": "PASS",
        "REJECTED": "FAIL",
        "INSUFFICIENT_EVIDENCE": "WARN",
    }.get(decision.verdict, "INFO")

    lines: list[str] = [
        f"## Evidence Report: {decision.claim_id}",
        "",
        f"- **Claim type:** {decision.claim_type}",
        f"- **Verdict:** {decision.verdict} ({verdict_icon})",
        f"- **Implementation allowed:** {decision.implementation_allowed}",
        "",
        "### Metrics",
        "",
    ]

    if passport.metrics:
        for key in (
            "accuracy",
            "net_expectancy_r",
            "net_sharpe_ratio",
            "overfit_gap",
            "n_folds",
            "pbo_risk",
        ):
            val = passport.metrics.get(key, "N/A")
            lines.append(f"- **{key}:** {val}")
    else:
        lines.append("_(no metrics in passport)_")

    lines.append("")
    lines.append("### Blocking Information")
    lines.append("")
    if decision.blocked_reason:
        lines.append(f"- **Blocked reason:** {decision.blocked_reason}")
    if decision.blocked_actions:
        lines.append(f"- **Blocked actions:** {', '.join(decision.blocked_actions)}")
    if decision.allowed_actions:
        lines.append(f"- **Allowed actions:** {', '.join(decision.allowed_actions)}")
    if decision.required_steps:
        lines.append("- **Required before proceeding:**")
        for step in decision.required_steps:
            lines.append(f"  - {step}")

    lines.append("")
    lines.append("### Limitations")
    if passport.limitations:
        for lim in passport.limitations:
            lines.append(f"- {lim}")
    else:
        lines.append("_(none listed)_")

    lines.append("")
    lines.append("### Warnings")
    if decision.warnings:
        for w in decision.warnings:
            lines.append(f"- {w}")
    else:
        lines.append("_(none)_")

    lines.append("")
    lines.append(f"---\n_Passport {passport.passport_id} | "
                 f"Candidate {passport.candidate_id} | "
                 f"Mode {passport.mode}_")

    return "\n".join(lines)


def generate_evidence_summary(passport: EvidencePassport) -> dict[str, Any]:
    """Produce a compact evidence summary dict from a passport.

    This is lighter than a full decision report — useful for dashboards
    and monitoring.
    """
    metrics = passport.metrics

    # Compute a simple quality score as a weighted composite
    accuracy = metrics.get("accuracy", 0.0)
    expectancy = metrics.get("net_expectancy_r", 0.0)
    sharpe = metrics.get("net_sharpe_ratio", 0.0)
    overfit_gap = metrics.get("overfit_gap", 1.0)

    quality_score = 0.0
    quality_score += min(accuracy * 20, 20.0)  # up to 20 pts
    quality_score += min(max(expectancy * 10, 0.0), 20.0)  # up to 20 pts
    quality_score += min(max(sharpe, 0.0) * 10, 20.0)  # up to 20 pts
    quality_score += max(0.0, 20.0 - overfit_gap * 100.0)  # up to 20 pts
    quality_score = min(quality_score, 100.0)

    return {
        "passport_id": passport.passport_id,
        "candidate_id": passport.candidate_id,
        "mode": passport.mode,
        "created_at": passport.created_at,
        "quality_score": round(quality_score, 1),
        "n_claims_evaluated": len(passport.claim_statuses),
        "claims_passed": sum(
            1 for s in passport.claim_statuses.values() if s == "PASSED"
        ),
        "n_gates_passed": sum(
            1 for s in passport.v7_gates.values() if s == "PASSED"
        ),
        "n_gates_total": len(passport.v7_gates) if passport.v7_gates else 0,
        "n_baselines": len(passport.baselines),
        "n_limitations": len(passport.limitations),
        "n_hypothesis_refs": len(passport.hypothesis_refs),
        "trial_count": passport.trial_count,
        "hard_caps_blocked": bool(passport.hard_caps.blocked_actions),
        "hard_caps_allowed": bool(passport.hard_caps.allowed_actions)
        or not passport.hard_caps.blocked_actions,
        "top_limitations": passport.limitations[:3],
    }
