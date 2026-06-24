"""AlphaForge V7HandoffPackage builder — review-only scaffold outputs.

Exports dry_run module symbols (WS-07) for V7 handoff dry run pipeline.
"""

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
    validate_gate_mapping,
    run_handoff_dry_run,
    run_all_dry_runs,
    _guard_promotion_status,
    _evaluate_rejection_rules,
    _make_gate_entry,
)

# Also export the existing P0.9A builder
from alphaforge.handoff.builders import (
    build_v7_handoff_package,
    build_all_handoffs,
)

__all__ = [
    "DryRunInput",
    "InputContractError",
    "PromotionGuardError",
    "RejectionRulesResult",
    "MODE_RESEARCH_REPORT_REQUIRED_FIELDS",
    "VALIDATION_REPORT_REQUIRED_FIELDS",
    "INPUT_CONTRACT_MAP",
    "VALIDATION_REPORT_INPUT_MAP",
    "validate_input_reports",
    "validate_gate_mapping",
    "run_handoff_dry_run",
    "run_all_dry_runs",
    "_guard_promotion_status",
    "_evaluate_rejection_rules",
    "_make_gate_entry",
    "build_v7_handoff_package",
    "build_all_handoffs",
]
