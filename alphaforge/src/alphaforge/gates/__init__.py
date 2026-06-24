"""AlphaForge Gates — governance modules that gate ML training.

The ml_pilot gate is the hard block: it validates 9 prerequisite conditions
before ANY model training can begin. No model training, no GBM imports.
"""

from alphaforge.gates.ml_pilot import (
    ActionItem,
    BlockingReport,
    FailedPrerequisiteDetail,
    GateVerdict,
    PrerequisiteRegistry,
    PrerequisiteResult,
    check_all_prerequisites,
    check_all_prior_accp_reports_exist,
    check_data_manifest_complete,
    check_dataset_assembled_and_checksummed,
    check_feature_pipeline_causal_validated,
    check_label_adapter_validated,
    check_no_gbm_in_environment,
    check_non_ml_research_report_complete,
    check_v7_handoff_dry_run_complete,
    check_walk_forward_skeleton_validated,
    generate_blocking_report,
    get_failed_prerequisites,
)

__all__ = [
    "ActionItem",
    "BlockingReport",
    "FailedPrerequisiteDetail",
    "GateVerdict",
    "PrerequisiteRegistry",
    "PrerequisiteResult",
    "check_all_prerequisites",
    "check_all_prior_accp_reports_exist",
    "check_data_manifest_complete",
    "check_dataset_assembled_and_checksummed",
    "check_feature_pipeline_causal_validated",
    "check_label_adapter_validated",
    "check_no_gbm_in_environment",
    "check_non_ml_research_report_complete",
    "check_v7_handoff_dry_run_complete",
    "check_walk_forward_skeleton_validated",
    "generate_blocking_report",
    "get_failed_prerequisites",
]
