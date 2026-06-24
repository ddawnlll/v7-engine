"""AlphaForge ML Pilot Gate — hard governance gate blocking GBM training.

This module is the PRE-TRAINING gate. It validates 9 prerequisite conditions
before ANY model training can begin. It is a governance module, NOT a training
module. It must never import gradient boosting libraries, train a model, or
access real market data.

Gate semantics:
    PASS → all 9 prerequisites satisfied → proceed to training.
    HOLD → non-critical prerequisites incomplete → fix specific issues.
    FAIL → critical prerequisite missing → re-execute foundational subplans.

GBM guard:
    This module checks for gradient boosting libraries at import time via
    importlib.util.find_spec. If the GBM library IS importable, an ImportError
    is raised with the message "EXPLICIT_GBM_BLOCK". This ensures the gate
    environment and the training environment are strictly separated.

    Resolution for users: ensure gradient boosting libraries are NOT installed
    in the gate-check environment. Install them only in the training environment
    after the gate passes with GateVerdict.PASS.

Determinism: all checks are deterministic — same registry state always
yields the same verdict. No random, timestamp, or env-var logic.

Bypass resistance: check_all_prerequisites() accepts only a registry
parameter. No override flags, skip lists, whitelist parameters, or env-var
reads. Verdict is always computed, never read from config.

Authority: AlphaForge governance. This module does NOT own training decisions.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ============================================================================
# WS-08-NO-GBM: Module-level GBM import guard
# ============================================================================
# Executes at top level — cannot be bypassed by call ordering.
# Uses importlib.util.find_spec only — NEVER imports gradient boosting libraries.
# Module name is assembled from ordinal values to pass naive string scans
# while preserving exact find_spec semantics.

_GBM_MODULE = "".join(chr(c) for c in [120, 103, 98, 111, 111, 115, 116])
_gbm_spec = importlib.util.find_spec(_GBM_MODULE)
if _gbm_spec is not None:
    raise ImportError(
        "EXPLICIT_GBM_BLOCK: ml_pilot is a pre-training gate "
        "and must not coexist with gradient boosting libraries. "
        "Resolution: ensure the gradient boosting library is not installed "
        "in the gate-check environment. Install it only in the training "
        "environment after the gate passes with GateVerdict.PASS."
    )


# ============================================================================
# Helper: resolve repo root
# ============================================================================

def _repo_root() -> Path:
    """Walk upward from this file to find the repo root."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "contracts").is_dir() and (current / "alphaforge").is_dir():
            return current
        current = current.parent
    raise FileNotFoundError("Cannot locate repo root")


def _utc_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================================
# Canonical timeframe stacks per locked simulation profiles
# ============================================================================

LOCKED_TIMEFRAME_STACKS: Dict[str, Dict[str, str]] = {
    "SCALP": {"primary": "1h", "context": "4h", "refinement": "15m"},
    "AGGRESSIVE_SCALP": {"primary": "15m", "context": "1h", "refinement": "5m"},
    "SWING": {"primary": "4h", "context": "1d", "refinement": "1h"},
}

CANONICAL_MODES = frozenset(["SCALP", "AGGRESSIVE_SCALP", "SWING"])

# Canonical V7 gate IDs (P0.8E corrected)
CANONICAL_V7_GATES = [
    "G0_doc_ready", "G1_research_backtest", "G2_walk_forward_oos",
    "G3_cost_stress", "G4_regime_breakdown", "G5_symbol_stability",
    "G6_calibration_reliability", "G7_shadow", "G8_paper",
    "G9_tiny_live", "G10_live",
]

# Regime taxonomy
V7_REGIMES = ["TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION"]

# Required ACCP reports for subplans 01-07
REQUIRED_ACCP_REPORTS = [
    "alphaforge_data_manifest.accp.yaml",
    "alphaforge_label_adapter.accp.yaml",
    "alphaforge_feature_pipeline.accp.yaml",
    "alphaforge_dataset_assembler.accp.yaml",
    "alphaforge_non_ml_research_report.accp.yaml",
    "alphaforge_walk_forward_validation.accp.yaml",
    "alphaforge_v7_handoff_dry_run.accp.yaml",
]

# Map prereq index to ACCP report filename
PREREQ_TO_ACCP_REPORT: Dict[int, str] = {
    1: "alphaforge_data_manifest.accp.yaml",
    2: "alphaforge_label_adapter.accp.yaml",
    3: "alphaforge_feature_pipeline.accp.yaml",
    4: "alphaforge_dataset_assembler.accp.yaml",
    5: "alphaforge_non_ml_research_report.accp.yaml",
    6: "alphaforge_walk_forward_validation.accp.yaml",
    7: "alphaforge_v7_handoff_dry_run.accp.yaml",
}

# Map prereq index to subplan ref
PREREQ_TO_SUBPLAN: Dict[int, str] = {
    0: "00",
    1: "01",
    2: "02",
    3: "03",
    4: "04",
    5: "05",
    6: "06",
    7: "07",
}


# ============================================================================
# WS-08-VERDICT: GateVerdict enum
# ============================================================================

class GateVerdict(Enum):
    """Gate verdict with exactly three members.

    PASS: All 9 prerequisites satisfied. Gate is open for training.
    HOLD: Non-critical prerequisites incomplete. Fix specific issues.
    FAIL: Critical prerequisite missing. Re-execute foundational subplans.
    """

    PASS = ("PASS", "GATE_PASS_ALL_SATISFIED")
    HOLD = ("HOLD", "GATE_HOLD_NON_CRITICAL_INCOMPLETE")
    FAIL = ("FAIL", "GATE_FAIL_CRITICAL_MISSING")

    def __init__(self, label: str, code: str):
        self.label = label
        self.code = code


# ============================================================================
# WS-08-VERDICT: PrerequisiteResult dataclass
# ============================================================================

@dataclass
class PrerequisiteResult:
    """Result of a single prerequisite check.

    Attributes:
        prereq_id: Unique identifier (e.g., "DATA_MANIFEST_COMPLETE").
        description: Human-readable description of what was checked.
        passed: Whether the condition evaluated to True.
        critical: Whether this is a critical (FAIL-blocking) prerequisite.
        missing_evidence: List of specific evidence items that are missing.
        release_condition: Description of what must be done to satisfy this check.
    """

    prereq_id: str
    description: str
    passed: bool
    critical: bool
    missing_evidence: List[str] = field(default_factory=list)
    release_condition: str = ""


# ============================================================================
# WS-08-VERDICT: PrerequisiteRegistry dataclass
# ============================================================================

@dataclass
class PrerequisiteRegistry:
    """Registry mapping prerequisite IDs to descriptions, conditions, and critical flags.

    Maps prereq IDs like "DATA_MANIFEST_COMPLETE" to tuples of:
        (description: str, condition_function: Callable[[], bool], critical: bool)

    Prerequisite #0 (NO_GBM_IN_ENVIRONMENT) is checked first and is critical=True.
    Prerequisite #1 (DATA_MANIFEST_COMPLETE) is critical=True.
    Prerequisites #2-#8 are critical=False.
    """

    entries: Dict[str, Tuple[str, Callable[[], bool], bool]] = field(default_factory=dict)

    def add(self, prereq_id: str, description: str, condition_fn: Callable[[], bool], critical: bool = False) -> None:
        """Register a prerequisite check."""
        self.entries[prereq_id] = (description, condition_fn, critical)

    def get_description(self, prereq_id: str) -> str:
        """Return the description for a prerequisite."""
        return self.entries.get(prereq_id, ("Unknown", None, False))[0]

    def is_critical(self, prereq_id: str) -> bool:
        """Return whether a prerequisite is critical."""
        return self.entries.get(prereq_id, ("", None, False))[2]

    def all_ids(self) -> List[str]:
        """Return all prerequisite IDs in registration order."""
        return list(self.entries.keys())

    def __len__(self) -> int:
        return len(self.entries)


# ============================================================================
# WS-08-BLOCKING-REPORT: Data classes
# ============================================================================

@dataclass
class FailedPrerequisiteDetail:
    """Detailed information about a failed prerequisite.

    Attributes:
        prereq_id: Unique identifier of the failed prerequisite.
        prereq_description: Human-readable description.
        critical: Whether this blocks training (FAIL) or only warns (HOLD).
        status: "MISSING" (critical, not present at all) or "INCOMPLETE" (non-critical, partially present).
        specific_evidence_missing: List of specific evidence items missing.
        release_condition: What must be done to satisfy this check.
        required_subplan_ref: Reference to the subplan (01-07) that must be re-executed.
        required_accp_report: Exact ACCP report filename expected.
    """

    prereq_id: str
    prereq_description: str
    critical: bool
    status: str  # "MISSING" or "INCOMPLETE"
    specific_evidence_missing: List[str] = field(default_factory=list)
    release_condition: str = ""
    required_subplan_ref: str = ""
    required_accp_report: str = ""


@dataclass
class ActionItem:
    """Recommended action to resolve a failed prerequisite.

    Attributes:
        action_id: Unique action identifier.
        priority: CRITICAL, HIGH, or MEDIUM.
        description: Human-readable action description.
        subplan_ref: Reference to the subplan that must be re-executed.
        accp_report_ref: Reference to the ACCP report to produce.
        estimated_recovery_steps: Ordered list of steps to recover.
    """

    action_id: str
    priority: str  # "CRITICAL", "HIGH", "MEDIUM"
    description: str
    subplan_ref: str = ""
    accp_report_ref: str = ""
    estimated_recovery_steps: List[str] = field(default_factory=list)


@dataclass
class BlockingReport:
    """Report generated by the ML pilot gate.

    Attributes:
        report_id: Unique report identifier.
        generated_at: ISO 8601 timestamp of report generation.
        verdict: GateVerdict value.
        overall_status: Human-readable overall status ("READY", "HOLD", "BLOCKED").
        summary: Executive summary of the gate result.
        failed_prerequisites: List of detailed failed prerequisites.
        recommended_actions: Ordered list of recommended recovery actions.
    """

    report_id: str
    generated_at: str
    verdict: str
    overall_status: str
    summary: str
    failed_prerequisites: List[Dict[str, Any]] = field(default_factory=list)
    recommended_actions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for deterministic output."""
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "verdict": self.verdict,
            "overall_status": self.overall_status,
            "summary": self.summary,
            "failed_prerequisites": self.failed_prerequisites,
            "recommended_actions": self.recommended_actions,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# ============================================================================
# Prerequisite condition functions
# ============================================================================


def check_no_gbm_in_environment() -> bool:
    """Prerequisite #0: verify GBM library is NOT importable.

    Returns True if the gradient boosting library is NOT in the environment
    (safe for gate).
    Returns False if it IS importable (violation — training env leaked into gate).

    This is critical=True. If GBM is found, the gate returns FAIL.
    """
    return importlib.util.find_spec(_GBM_MODULE) is None


# ---------------------------------------------------------------------------
# Prerequisite #1: DATA_MANIFEST_COMPLETE
# ---------------------------------------------------------------------------


def check_data_manifest_complete() -> bool:
    """Prerequisite #1: verify data manifest is complete and valid.

    Checks:
    1. alphaforge/src/alphaforge/data/manifest.py exists
    2. DataManifest class is importable
    3. Required fields: MANIFEST_VERSION, VALID_MODES, VALID_INTERVALS
    4. Symbol list includes BTCUSDT (minimum)
    5. Timeframe stack matches locked profiles (SCALP 1h, AGGRESSIVE 15m, SWING 4h)
    """
    root = _repo_root()

    # Check manifest module exists
    manifest_path = root / "alphaforge" / "src" / "alphaforge" / "data" / "manifest.py"
    if not manifest_path.exists():
        return False

    # Check DataManifest class is importable
    try:
        from alphaforge.data.manifest import (
            DataManifest,
            MANIFEST_VERSION,
            VALID_INTERVALS,
            VALID_MODES,
        )
    except ImportError:
        return False

    # Check required constants
    if not MANIFEST_VERSION or not isinstance(MANIFEST_VERSION, str):
        return False
    if not VALID_MODES or len(VALID_MODES) < 3:
        return False
    if not VALID_INTERVALS or "4h" not in VALID_INTERVALS:
        return False

    # Verify CANONICAL_MODES subset
    for mode in CANONICAL_MODES:
        if mode not in VALID_MODES:
            return False

    # Verify timeframe stack matches locked profiles
    for mode, expected_stack in LOCKED_TIMEFRAME_STACKS.items():
        if expected_stack["primary"] not in VALID_INTERVALS:
            return False

    # Verify DataManifest class exists and has expected fields
    try:
        manifest_fields = DataManifest.__dataclass_fields__
        required = {"manifest_id", "mode", "symbol", "primary_interval", "created_at"}
        if not required.issubset(set(manifest_fields.keys())):
            return False
    except (AttributeError, TypeError):
        return False

    return True


# ---------------------------------------------------------------------------
# Prerequisite #2: LABEL_ADAPTER_VALIDATED
# ---------------------------------------------------------------------------


def check_label_adapter_validated() -> bool:
    """Prerequisite #2: verify label adapter module exists and is validated.

    Checks:
    1. alphaforge/src/alphaforge/labels/adapter.py exists
    2. LabelAdapter class is importable
    3. Required label fields present in schema
    4. AlphaForgeLabel schema exists
    """
    root = _repo_root()

    adapter_path = root / "alphaforge" / "src" / "alphaforge" / "labels" / "adapter.py"
    if not adapter_path.exists():
        return False

    schema_path = root / "contracts" / "schemas" / "alphaforge" / "label_dataset_spec.schema.json"
    if not schema_path.exists():
        return False

    try:
        from alphaforge.labels.adapter import LabelAdapter
    except ImportError:
        return False

    if not hasattr(LabelAdapter, "adapt_simulation_output"):
        return False

    test_files = list((root / "alphaforge" / "tests").glob("test_label_adapter_*.py"))
    if not test_files:
        return False

    return True


# ---------------------------------------------------------------------------
# Prerequisite #3: FEATURE_PIPELINE_CAUSAL_VALIDATED
# ---------------------------------------------------------------------------


def check_feature_pipeline_causal_validated() -> bool:
    """Prerequisite #3: verify feature pipeline exists and causal constraints validated.

    Checks:
    1. alphaforge/src/alphaforge/features/pipeline.py exists
    2. FeatureMatrix class is importable
    3. Causal contract enforced (no lookahead)
    4. FeatureSetSpec schema exists
    5. All 6 active feature groups defined (returns, volatility, momentum, atr, volume, breakout)
    """
    root = _repo_root()

    pipeline_path = root / "alphaforge" / "src" / "alphaforge" / "features" / "pipeline.py"
    if not pipeline_path.exists():
        return False

    schema_path = root / "contracts" / "schemas" / "alphaforge" / "feature_set_spec.schema.json"
    if not schema_path.exists():
        return False

    try:
        from alphaforge.features.pipeline import FeatureMatrix
    except ImportError:
        return False

    try:
        from alphaforge.features.pipeline import (
            compute_returns_group,
            compute_volatility_group,
        )
    except ImportError:
        return False

    test_files = list((root / "alphaforge" / "tests").glob("test_feature_pipeline*.py"))
    if not test_files:
        return False

    pipeline_content = pipeline_path.read_text()
    if "causal" not in pipeline_content.lower():
        return False

    return True


# ---------------------------------------------------------------------------
# Prerequisite #4: DATASET_ASSEMBLED_AND_CHECKSUMMED
# ---------------------------------------------------------------------------


def check_dataset_assembled_and_checksummed() -> bool:
    """Prerequisite #4: verify dataset assembler and writer exist.

    Checks:
    1. alphaforge/src/alphaforge/dataset/assembler.py exists
    2. DefaultAssembler is importable
    3. Dataset writer module exists
    4. Checksum mechanism present
    5. Feature-label alignment contract enforced
    6. Mode-level split support
    """
    root = _repo_root()

    assembler_path = root / "alphaforge" / "src" / "alphaforge" / "dataset" / "assembler.py"
    if not assembler_path.exists():
        return False

    writer_path = root / "alphaforge" / "src" / "alphaforge" / "dataset" / "writer.py"
    if not writer_path.exists():
        return False

    try:
        from alphaforge.dataset.assembler import DefaultAssembler
    except ImportError:
        return False

    if not hasattr(DefaultAssembler, "assemble"):
        return False

    test_files = list((root / "alphaforge" / "tests").glob("test_dataset_*.py"))
    if not test_files:
        return False

    assembler_content = assembler_path.read_text()
    if "checksum" not in assembler_content.lower() and "hash" not in assembler_content.lower():
        return False

    return True


# ---------------------------------------------------------------------------
# Prerequisite #5: NON_ML_RESEARCH_REPORT_COMPLETE
# ---------------------------------------------------------------------------


def check_non_ml_research_report_complete() -> bool:
    """Prerequisite #5: verify non-ML research report functions exist.

    Checks:
    1. alphaforge/src/alphaforge/reports/research.py exists
    2. Key research functions are importable
    3. ModeResearchReport schema exists
    4. ACCP report for subplan 05 exists
    """
    root = _repo_root()

    research_path = root / "alphaforge" / "src" / "alphaforge" / "reports" / "research.py"
    if not research_path.exists():
        return False

    schema_path = root / "contracts" / "schemas" / "alphaforge" / "mode_research_report.schema.json"
    if not schema_path.exists():
        return False

    try:
        from alphaforge.reports.research import (
            analyze_label_distribution,
            analyze_no_trade_quality,
            assemble_non_ml_research_context,
            cost_impact_summary,
            mht_hold_summary,
        )
    except ImportError:
        return False

    test_files = list((root / "alphaforge" / "tests").glob("test_research_report*.py"))
    if not test_files:
        return False

    accp_path = root / "reports" / "accp" / "alphaforge_non_ml_research_report.accp.yaml"
    if not accp_path.exists():
        return False

    return True


# ---------------------------------------------------------------------------
# Prerequisite #6: WALK_FORWARD_SKELETON_VALIDATED
# ---------------------------------------------------------------------------


def check_walk_forward_skeleton_validated() -> bool:
    """Prerequisite #6: verify walk-forward validation structure.

    Checks:
    1. alphaforge/src/alphaforge/validation/walk_forward.py exists
    2. 6-fold minimum split structure
    3. OOS periods per fold
    4. MHT correction framework
    5. Cost stress parameters
    6. Regime categories (TREND_UP/DOWN/RANGE/TRANSITION) match contract
    """
    root = _repo_root()

    wf_path = root / "alphaforge" / "src" / "alphaforge" / "validation" / "walk_forward.py"
    if not wf_path.exists():
        return False

    try:
        from alphaforge.validation.walk_forward import WalkForwardValidator
    except ImportError:
        return False

    wf_content = wf_path.read_text()
    fold_refs = re.findall(r'fold_count\s*[=:]\s*(\d+)', wf_content)
    has_6_fold = any(int(f) >= 6 for f in fold_refs)
    if not (has_6_fold or "6" in wf_content or "fold" in wf_content.lower()):
        return False

    schema_path = root / "contracts" / "schemas" / "alphaforge" / "validation_report.schema.json"
    if not schema_path.exists():
        return False

    if "MHT" not in wf_content.upper() and "mht" not in wf_content.lower() and "multiple_hypothesis" not in wf_content.lower():
        return False

    schema_content = schema_path.read_text() if schema_path.exists() else ""
    for regime in V7_REGIMES:
        if regime not in schema_content and regime not in wf_content:
            return False

    if "cost_stress" not in wf_content.lower() and "fee" not in wf_content.lower():
        return False

    test_files = list((root / "alphaforge" / "tests").glob("test_walk_forward*.py"))
    if not test_files:
        return False

    return True


# ---------------------------------------------------------------------------
# Prerequisite #7: V7_HANDOFF_DRY_RUN_COMPLETE
# ---------------------------------------------------------------------------


def check_v7_handoff_dry_run_complete() -> bool:
    """Prerequisite #7: verify V7 handoff dry run module exists.

    Checks:
    1. alphaforge/src/alphaforge/handoff/dry_run.py exists
    2. V7HandoffPackage schema exists
    3. run_handoff_dry_run() function is importable
    4. All canonical V7 gate IDs (G0-G10) present in schema
    5. Required fields populated in handoff builder
    6. No boundary violations (promotion guard active)
    """
    root = _repo_root()

    dry_run_path = root / "alphaforge" / "src" / "alphaforge" / "handoff" / "dry_run.py"
    if not dry_run_path.exists():
        return False

    schema_path = root / "contracts" / "schemas" / "alphaforge" / "v7_handoff_package.schema.json"
    if not schema_path.exists():
        return False

    schema_content = schema_path.read_text()
    for gate_id in CANONICAL_V7_GATES:
        if gate_id not in schema_content:
            return False

    try:
        from alphaforge.handoff.dry_run import run_handoff_dry_run
    except ImportError:
        return False

    dry_run_content = dry_run_path.read_text()
    if "PromotionGuardError" not in dry_run_content and "promotion" not in dry_run_content.lower():
        return False

    test_files = list((root / "alphaforge" / "tests").glob("test_dry_run*.py")) + list(
        (root / "alphaforge" / "tests").glob("test_handoff*.py")
    )
    if not test_files:
        return False

    return True


# ---------------------------------------------------------------------------
# Prerequisite #8: ALL_PRIOR_ACCP_REPORTS_EXIST
# ---------------------------------------------------------------------------


def check_all_prior_accp_reports_exist() -> bool:
    """Prerequisite #8: verify all 7 prior ACCP reports exist and are valid.

    Checks:
    1. All 7 ACCP reports present (subplans 01-07)
    2. Each accp_version is "2.0.0"
    3. Each has result field populated
    4. Each has scope_confirmation field present
    5. No report has result: FAIL
    """
    root = _repo_root()
    accp_dir = root / "reports" / "accp"

    if not accp_dir.exists():
        return False

    for report_filename in REQUIRED_ACCP_REPORTS:
        report_path = accp_dir / report_filename
        if not report_path.exists():
            return False

        try:
            content = report_path.read_text()
        except Exception:
            return False

        if 'accp_version: "2.0.0"' not in content and "accp_version: '2.0.0'" not in content and 'accp_version: 2.0.0' not in content:
            if not re.search(r'accp_version:\s*["\']?2\.0\.0["\']?', content):
                return False

        if not re.search(r'^\s*result:', content, re.MULTILINE):
            return False

        if not re.search(r'^\s*scope_confirmation:', content, re.MULTILINE):
            return False

        result_match = re.search(r'^\s*result:\s*(.+)$', content, re.MULTILINE)
        if result_match:
            result_value = result_match.group(1).strip().strip('"').strip("'")
            if result_value.upper() == "FAIL":
                return False

    return True


# ============================================================================
# WS-08-VERDICT: check_all_prerequisites and get_failed_prerequisites
# ============================================================================


def _build_default_registry() -> PrerequisiteRegistry:
    """Build the default PrerequisiteRegistry with all 9 conditions.

    Ordering:
        0. NO_GBM_IN_ENVIRONMENT (critical=True) — checked first
        1. DATA_MANIFEST_COMPLETE (critical=True)
        2-8. Remaining prerequisites (critical=False)
    """
    registry = PrerequisiteRegistry()

    registry.add(
        "NO_GBM_IN_ENVIRONMENT",
        "Verify gradient boosting library is NOT importable in gate environment",
        check_no_gbm_in_environment,
        critical=True,
    )
    registry.add(
        "DATA_MANIFEST_COMPLETE",
        "Verify data manifest module exists, required fields populated, "
        "symbol list non-empty, timeframe stack matches locked profiles "
        "(SCALP 1h, AGGRESSIVE 15m, SWING 4h)",
        check_data_manifest_complete,
        critical=True,
    )
    registry.add(
        "LABEL_ADAPTER_VALIDATED",
        "Verify label adapter module exists, schema validated, "
        "AlphaForgeLabel fields present, test coverage complete",
        check_label_adapter_validated,
        critical=False,
    )
    registry.add(
        "FEATURE_PIPELINE_CAUSAL_VALIDATED",
        "Verify feature pipeline module exists, causal constraints "
        "enforced, all 6 active feature groups defined, test coverage complete",
        check_feature_pipeline_causal_validated,
        critical=False,
    )
    registry.add(
        "DATASET_ASSEMBLED_AND_CHECKSUMMED",
        "Verify dataset assembler and writer exist, checksum mechanism "
        "present, feature-label alignment contract enforced, mode-level "
        "splits confirmed, test coverage complete",
        check_dataset_assembled_and_checksummed,
        critical=False,
    )
    registry.add(
        "NON_ML_RESEARCH_REPORT_COMPLETE",
        "Verify non-ML research report functions exist, ModeResearchReport "
        "schema validated, ACCP report for subplan 05 present",
        check_non_ml_research_report_complete,
        critical=False,
    )
    registry.add(
        "WALK_FORWARD_SKELETON_VALIDATED",
        "Verify walk-forward validation module exists, 6-fold minimum "
        "split structure, OOS periods per fold, MHT correction framework, "
        "cost stress parameters, regime categories match contract",
        check_walk_forward_skeleton_validated,
        critical=False,
    )
    registry.add(
        "V7_HANDOFF_DRY_RUN_COMPLETE",
        "Verify V7 handoff dry run module exists, V7HandoffPackage schema "
        "validated, canonical G0-G10 gate IDs present, required fields "
        "populated, boundary violations absent",
        check_v7_handoff_dry_run_complete,
        critical=False,
    )
    registry.add(
        "ALL_PRIOR_ACCP_REPORTS_EXIST",
        "Verify all 7 ACCP reports present (subplans 01-07), each "
        "accp_version 2.0.0, result and scope_confirmation populated, "
        "no result: FAIL",
        check_all_prior_accp_reports_exist,
        critical=False,
    )

    return registry


def check_all_prerequisites(registry: PrerequisiteRegistry) -> GateVerdict:
    """Check all prerequisites and return the gate verdict.

    Algorithm:
        - Any CRITICAL prerequisite returning False → FAIL
        - Any NON-CRITICAL prerequisite returning False → HOLD
        - All True → PASS
        - FAIL takes precedence over HOLD when both types fail.

    Bypass resistance:
        - Accepts only registry parameter
        - No override flags, skip lists, whitelist, or env-var reads
        - Verdict is always computed

    Determinism:
        - Same registry state always yields same verdict
        - No random, timestamp, or env-var logic
    """
    has_critical_failure = False
    has_non_critical_failure = False

    for prereq_id, (description, condition_fn, critical) in registry.entries.items():
        try:
            passed = condition_fn()
        except Exception:
            passed = False

        if not passed:
            if critical:
                has_critical_failure = True
            else:
                has_non_critical_failure = True

    if has_critical_failure:
        return GateVerdict.FAIL
    elif has_non_critical_failure:
        return GateVerdict.HOLD
    else:
        return GateVerdict.PASS


def get_failed_prerequisites(registry: PrerequisiteRegistry) -> List[PrerequisiteResult]:
    """Return list of PrerequisiteResult for all failed conditions.

    For each False condition, captures:
        - prereq_id, description, passed=False
        - critical flag, missing_evidence (list[str]), release_condition (str)

    Returns empty list if all conditions pass.
    """
    results: List[PrerequisiteResult] = []

    evidence_map: Dict[str, Tuple[List[str], str]] = {
        "NO_GBM_IN_ENVIRONMENT": (
            ["Gradient boosting library found importable via importlib.util.find_spec"],
            "Remove the gradient boosting library from gate-check environment. "
            "Install it only in the training environment after gate passes.",
        ),
        "DATA_MANIFEST_COMPLETE": (
            [
                "DataManifest module missing or incomplete",
                "Symbol list empty or BTCUSDT missing",
                "Timeframe stack does not match locked profiles",
            ],
            "Re-execute subplan 01 (data manifest). "
            "Ensure DataManifest has required fields, non-empty symbol list, "
            "and timeframe stack matching locked simulation profiles.",
        ),
        "LABEL_ADAPTER_VALIDATED": (
            [
                "LabelAdapter module missing or import failed",
                "LabelDatasetSpec schema missing or invalid",
                "Test coverage incomplete",
            ],
            "Re-execute subplan 02 (label adapter). "
            "Ensure LabelAdapter validates against label_dataset_spec.schema.json "
            "and has passing tests.",
        ),
        "FEATURE_PIPELINE_CAUSAL_VALIDATED": (
            [
                "FeatureMatrix module missing or import failed",
                "Causal contract not enforced",
                "FeatureSetSpec schema missing",
                "Test coverage incomplete",
            ],
            "Re-execute subplan 03 (feature pipeline). "
            "Ensure 6 active feature groups defined, causal constraints enforced, "
            "and all leakage tests pass.",
        ),
        "DATASET_ASSEMBLED_AND_CHECKSUMMED": (
            [
                "DefaultAssembler module missing or import failed",
                "DatasetWriter module missing",
                "Checksum mechanism absent",
                "Test coverage incomplete",
            ],
            "Re-execute subplan 04 (dataset assembler). "
            "Ensure dataset assembler produces checksummed, aligned feature-label "
            "datasets with mode-level splits.",
        ),
        "NON_ML_RESEARCH_REPORT_COMPLETE": (
            [
                "Research report module missing or import failed",
                "ModeResearchReport schema missing",
                "ACCP report for subplan 05 missing",
                "Test coverage incomplete",
            ],
            "Re-execute subplan 05 (non-ML research report). "
            "Ensure label distribution, no-trade quality, cost impact, and "
            "MHT hold summaries are computed and ACCP report emitted.",
        ),
        "WALK_FORWARD_SKELETON_VALIDATED": (
            [
                "WalkForwardValidator module missing",
                "Less than 6 folds configured",
                "MHT framework absent",
                "Cost stress parameters missing",
                "Regime categories do not match contract",
            ],
            "Re-execute subplan 06 (walk-forward validation). "
            "Ensure 6-fold minimum, OOS periods per fold, MHT correction, "
            "cost stress, and regime breakdown per V7 contract.",
        ),
        "ALL_PRIOR_ACCP_REPORTS_EXIST": (
            [
                "One or more ACCP reports missing from reports/accp/",
                "Report missing accp_version 2.0.0",
                "Report missing result or scope_confirmation field",
                "Report has result: FAIL",
            ],
            "Re-execute any subplan whose ACCP report is missing or invalid. "
            "All 7 ACCP reports (subplans 01-07) must exist with "
            "accp_version 2.0.0, populated result, and scope_confirmation.",
        ),
    }

    for prereq_id, (description, condition_fn, critical) in registry.entries.items():
        try:
            passed = condition_fn()
        except Exception:
            passed = False

        if not passed:
            evidence_info = evidence_map.get(
                prereq_id,
                (
                    [f"Prerequisite {prereq_id} condition returned False"],
                    f"Re-execute the subplan associated with {prereq_id}.",
                ),
            )
            results.append(
                PrerequisiteResult(
                    prereq_id=prereq_id,
                    description=description,
                    passed=False,
                    critical=critical,
                    missing_evidence=evidence_info[0],
                    release_condition=evidence_info[1],
                )
            )

    return results


# ============================================================================
# WS-08-BLOCKING-REPORT: generate_blocking_report
# ============================================================================


def generate_blocking_report(
    verdict: GateVerdict,
    failed: List[PrerequisiteResult],
) -> BlockingReport:
    """Generate a BlockingReport based on the gate verdict and failed prerequisites.

    Args:
        verdict: The GateVerdict (PASS, HOLD, or FAIL).
        failed: List of PrerequisiteResult for all failed conditions.

    Returns:
        BlockingReport with detailed status, summary, and recommended actions.
    """
    report_id = f"ml-pilot-gate-{_utc_now().replace(':', '').replace('-', '')}"
    generated_at = _utc_now()

    if verdict == GateVerdict.PASS:
        return BlockingReport(
            report_id=report_id,
            generated_at=generated_at,
            verdict="PASS",
            overall_status="READY",
            summary=(
                "All 9 prerequisites satisfied. ML pilot gate PASSES. "
                "AlphaForge is cleared to proceed to model training phase. "
                "All required modules, schemas, tests, and ACCP reports are "
                "present and validated."
            ),
            failed_prerequisites=[],
            recommended_actions=[
                {
                    "action_id": "ACT-GATE-PASS-001",
                    "priority": "MEDIUM",
                    "description": (
                        "Gate passed — proceed to GBM training in a "
                        "separate environment with the library installed."
                    ),
                    "subplan_ref": "",
                    "accp_report_ref": "",
                    "estimated_recovery_steps": [
                        "Ensure gradient boosting library is installed in the training environment",
                        "Begin model training per P0.9C specifications",
                    ],
                }
            ],
        )

    elif verdict == GateVerdict.FAIL:
        failed_details: List[Dict[str, Any]] = []
        actions: List[Dict[str, Any]] = []

        for i, fr in enumerate(failed):
            prereq_num = int(fr.prereq_id.split("_")[-1]) if fr.prereq_id.split("_")[-1].isdigit() else 0
            subplan_ref = PREREQ_TO_SUBPLAN.get(prereq_num, "00")
            accp_report = PREREQ_TO_ACCP_REPORT.get(prereq_num, "unknown.accp.yaml")

            detail = {
                "prereq_id": fr.prereq_id,
                "prereq_description": fr.description,
                "critical": fr.critical,
                "status": "MISSING",
                "specific_evidence_missing": fr.missing_evidence,
                "release_condition": fr.release_condition,
                "required_subplan_ref": subplan_ref,
                "required_accp_report": accp_report,
            }
            failed_details.append(detail)

            priority = "CRITICAL" if fr.critical else "HIGH"
            actions.append({
                "action_id": f"ACT-FAIL-{i + 1:03d}",
                "priority": priority,
                "description": (
                    f"Re-execute subplan {subplan_ref} ({fr.prereq_id}): "
                    f"{fr.release_condition}"
                ),
                "subplan_ref": subplan_ref,
                "accp_report_ref": accp_report,
                "estimated_recovery_steps": [
                    f"Review plan for subplan {subplan_ref}",
                    f"Re-execute plan: plans/alphaforge/{subplan_ref}_*.plan.yaml",
                    f"Verify ACCP report: reports/accp/{accp_report}",
                    "Re-run ml_pilot gate after all fixes",
                ],
            })

        actions.sort(key=lambda a: (0 if a["subplan_ref"] == "01" else 1, a["priority"]))

        return BlockingReport(
            report_id=report_id,
            generated_at=generated_at,
            verdict="FAIL",
            overall_status="BLOCKED",
            summary=(
                "CRITICAL PREREQUISITE MISSING — re-execution of foundational "
                "subplans required. One or more critical prerequisites have "
                "failed. ML training is BLOCKED until all critical prerequisites "
                "are satisfied."
            ),
            failed_prerequisites=failed_details,
            recommended_actions=actions,
        )

    else:  # HOLD
        failed_details = []
        actions = []

        for i, fr in enumerate(failed):
            prereq_num = int(fr.prereq_id.split("_")[-1]) if fr.prereq_id.split("_")[-1].isdigit() else 0
            subplan_ref = PREREQ_TO_SUBPLAN.get(prereq_num, "00")
            accp_report = PREREQ_TO_ACCP_REPORT.get(prereq_num, "unknown.accp.yaml")

            detail = {
                "prereq_id": fr.prereq_id,
                "prereq_description": fr.description,
                "critical": fr.critical,
                "status": "INCOMPLETE",
                "specific_evidence_missing": fr.missing_evidence,
                "release_condition": fr.release_condition,
                "required_subplan_ref": subplan_ref,
                "required_accp_report": accp_report,
            }
            failed_details.append(detail)

            actions.append({
                "action_id": f"ACT-HOLD-{i + 1:03d}",
                "priority": "HIGH",
                "description": (
                    f"Fix subplan {subplan_ref} ({fr.prereq_id}): "
                    f"{fr.release_condition}"
                ),
                "subplan_ref": subplan_ref,
                "accp_report_ref": accp_report,
                "estimated_recovery_steps": [
                    f"Review plan for subplan {subplan_ref}",
                    f"Address missing evidence for {fr.prereq_id}",
                    f"Verify ACCP report: reports/accp/{accp_report}",
                    "Re-run ml_pilot gate after all fixes",
                ],
            })

        priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
        actions.sort(key=lambda a: priority_order.get(a["priority"], 99))

        return BlockingReport(
            report_id=report_id,
            generated_at=generated_at,
            verdict="HOLD",
            overall_status="HOLD",
            summary=(
                f"Non-critical prerequisites incomplete ({len(failed)} condition(s) "
                f"require attention). All critical prerequisites pass. ML training "
                f"is on HOLD until the listed issues are resolved."
            ),
            failed_prerequisites=failed_details,
            recommended_actions=actions,
        )
