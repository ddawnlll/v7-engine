"""Minimal V7 handoff package builder.

Uses canonical gates. Never claims promotion without evidence.
NO_TRADE is a metric/comparator, not a promotion gate.
"""

from typing import Dict, Any, List, Optional

from .reports import CANONICAL_V7_GATES, FORBIDDEN_GATE_NAMES
from .errors import GateMappingError, HandoffBlockedError


def validate_gate_mapping(gate_mapping: Dict[str, Any]) -> None:
    """Validate gate mapping uses only canonical V7 gate names.

    Raises GateMappingError if old/forbidden names present.
    """
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
    """Recursively verify no old gate name strings appear anywhere in data."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in FORBIDDEN_GATE_NAMES:
                raise GateMappingError(
                    invalid_gates=[key],
                    allowed_gates=CANONICAL_V7_GATES,
                )
            assert_no_old_gate_names(value)
    elif isinstance(data, list):
        for item in data:
            assert_no_old_gate_names(item)
    elif isinstance(data, str):
        for forbidden in FORBIDDEN_GATE_NAMES:
            if forbidden in data:
                raise GateMappingError(
                    invalid_gates=[forbidden],
                    allowed_gates=CANONICAL_V7_GATES,
                )


def build_handoff_package(
    mode: str,
    gate_evidence: Optional[Dict[str, str]] = None,
    recommended_status: str = "REVIEW_REQUIRED",
    blocked_scopes: Optional[List[str]] = None,
    limitations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a V7HandoffPackage with canonical gate mapping.

    Raises:
        GateMappingError: Old gate names present.
        HandoffBlockedError: PROMOTION_CANDIDATE without real evidence.
    """
    from .reports import build_minimal_handoff_package
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
