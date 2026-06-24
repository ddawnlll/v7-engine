"""AlphaForge V7HandoffPackage builder — review-only scaffold outputs.

Exports dry_run module symbols (WS-07) for V7 handoff dry run pipeline,
P0.9A builder symbols, and legacy handoff functions that were previously
in the orphaned handoff.py module (package-vs-module conflict resolved by
consolidating all symbols into this package __init__).
"""

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Legacy handoff.py functions (imports changed from relative to absolute
# because alphaforge.handoff.{reports,errors} do not exist).
# ---------------------------------------------------------------------------

from alphaforge.constants import CANONICAL_V7_GATES, FORBIDDEN_GATE_NAMES
from alphaforge.errors import GateMappingError, HandoffBlockedError


def validate_gate_mapping(gate_mapping: Dict[str, Any]) -> None:
    """Validate gate mapping uses only canonical V7 gate names."""
    gate_keys = set(gate_mapping.keys())
    forbidden_found = gate_keys & set(FORBIDDEN_GATE_NAMES)
    if forbidden_found:
        raise GateMappingError(
            invalid_gates=sorted(forbidden_found),
            allowed_gates=CANONICAL_V7_GATES,
        )
    missing = set(CANONICAL_V7_GATES) - gate_keys
    if missing:
        raise GateMappingError(
            invalid_gates=[f"missing: {g}" for g in sorted(missing)],
            allowed_gates=CANONICAL_V7_GATES,
        )


def assert_no_old_gate_names(data: Any) -> None:
    """Recursively verify no old gate name strings appear anywhere."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in FORBIDDEN_GATE_NAMES:
                raise GateMappingError(invalid_gates=[key], allowed_gates=CANONICAL_V7_GATES)
            assert_no_old_gate_names(value)
    elif isinstance(data, list):
        for item in data:
            assert_no_old_gate_names(item)
    elif isinstance(data, str):
        for forbidden in FORBIDDEN_GATE_NAMES:
            if forbidden in data:
                raise GateMappingError(invalid_gates=[forbidden], allowed_gates=CANONICAL_V7_GATES)


def build_handoff_package(
    mode: str,
    gate_evidence: Optional[Dict[str, str]] = None,
    recommended_status: str = "REVIEW_REQUIRED",
    blocked_scopes: Optional[List[str]] = None,
    limitations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a V7HandoffPackage with canonical gate mapping."""
    from alphaforge.reports import build_minimal_handoff_package
    from datetime import datetime, timezone

    pkg = build_minimal_handoff_package(mode=mode)
    if gate_evidence:
        validate_gate_mapping(gate_evidence)
        for gate in CANONICAL_V7_GATES:
            if gate in gate_evidence:
                pkg["v7_gate_mapping"][gate] = gate_evidence[gate]
    validate_gate_mapping(pkg["v7_gate_mapping"])
    if recommended_status == "PROMOTION_CANDIDATE":
        placeholder_count = sum(
            1 for v in pkg["v7_gate_mapping"].values()
            if "placeholder" in str(v).lower() or "no real" in str(v).lower()
        )
        if placeholder_count > 5:
            raise HandoffBlockedError([
                "PROMOTION_CANDIDATE blocked — insufficient real gate evidence.",
                f"{placeholder_count} gates have placeholder descriptions.",
            ])
    pkg["recommended_status"] = recommended_status
    if blocked_scopes:
        pkg["blocked_scopes"].extend(blocked_scopes)
    if limitations:
        pkg["limitations"].extend(limitations)
    pkg["created_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert_no_old_gate_names(pkg)
    return pkg


def is_promotion_blocked(handoff_pkg: Dict[str, Any]) -> bool:
    """Return True if handoff package is not eligible for promotion."""
    if handoff_pkg.get("recommended_status") != "PROMOTION_CANDIDATE":
        return True
    blocked = handoff_pkg.get("blocked_scopes", [])
    if any("DEFERRED" in b for b in blocked):
        return True
    return False


# ---------------------------------------------------------------------------
# WS-07: V7 handoff dry_run module exports
# ---------------------------------------------------------------------------

from alphaforge.handoff.dry_run import (
    DryRunInput,
    InputContractError,
    PromotionGuardError,
    RejectionRulesResult,
    MODE_RESEARCH_REPORT_REQUIRED_FIELDS,
    VALIDATION_REPORT_REQUIRED_FIELDS,
    INPUT_CONTRACT_MAP,
    VALIDATION_REPORT_INPUT_MAP,
    validate_input_reports,
    validate_gate_mapping as _dry_run_validate_gate_mapping,
    run_handoff_dry_run,
    run_all_dry_runs,
    _guard_promotion_status,
    _evaluate_rejection_rules,
    _make_gate_entry,
)

# ---------------------------------------------------------------------------
# P0.9A builder exports
# ---------------------------------------------------------------------------

from alphaforge.handoff.builders import (
    build_v7_handoff_package,
    build_all_handoffs,
)

__all__ = [
    # Legacy (from orphaned handoff.py)
    "validate_gate_mapping",
    "assert_no_old_gate_names",
    "build_handoff_package",
    "is_promotion_blocked",
    "CANONICAL_V7_GATES",
    "FORBIDDEN_GATE_NAMES",
    "GateMappingError",
    "HandoffBlockedError",
    # WS-07: dry_run
    "DryRunInput",
    "InputContractError",
    "PromotionGuardError",
    "RejectionRulesResult",
    "MODE_RESEARCH_REPORT_REQUIRED_FIELDS",
    "VALIDATION_REPORT_REQUIRED_FIELDS",
    "INPUT_CONTRACT_MAP",
    "VALIDATION_REPORT_INPUT_MAP",
    "validate_input_reports",
    "run_handoff_dry_run",
    "run_all_dry_runs",
    "_guard_promotion_status",
    "_evaluate_rejection_rules",
    "_make_gate_entry",
    # P0.9A: builders
    "build_v7_handoff_package",
    "build_all_handoffs",
]
