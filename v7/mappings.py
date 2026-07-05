"""
Cross-domain field mappings for V7 Engine.

Provides:
  - FieldMapping dataclass: structured definition of one field crossing a domain boundary.
  - CrossDomainMapper: runtime mapping engine backed by contract JSON files.
  - validate_field_mapping: structural validation of a single mapping definition.

Authority (from CLAUDE.md):
  - Simulation owns economic truth.
  - AlphaForge owns alpha discovery.
  - V7 owns final trade decisions (policy acceptance).
  - Mapping JSON files in contracts/mappings/ are the canonical field-level bridge.

Cross-domain field mapping rules (from CLAUDE.md):
  - V7 does NOT invent alpha. AlphaForge discovers.
  - AlphaForge does NOT own final trade decisions. V7 owns policy acceptance.
  - Simulation owns economic truth. No component bypasses simulation costs.
  - Runtime does NOT override policy with model confidence.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent

_SIM_TO_V7_PATH = (
    _REPO_ROOT / "contracts" / "mappings" / "simulation_to_v7.json"
)
_SIM_TO_ALPHAFORGE_PATH = (
    _REPO_ROOT / "contracts" / "mappings" / "simulation_to_alphaforge.json"
)

# Known enum values for validation
_VALID_ACTIONS = frozenset({"LONG_NOW", "SHORT_NOW", "NO_TRADE", "AMBIGUOUS_STATE"})
_VALID_EXIT_REASONS = frozenset({
    "STOP_HIT", "TARGET_HIT", "TIME_EXIT", "HORIZON_END",
    "UNRESOLVED", "INVALIDATED", "MANUAL_EXIT", "RUNTIME_EXIT",
    "PROJECTED_HORIZON_END", "NOT_APPLICABLE",
})
_VALID_RESOLUTION_STATUSES = frozenset({"COMPLETE", "UNRESOLVED", "INVALIDATED"})
_VALID_NO_TRADE_QUALITIES = frozenset({
    "CORRECT_NO_TRADE", "SAVED_LOSS", "MISSED_OPPORTUNITY", "AMBIGUOUS_NO_TRADE",
})
_VALID_PATH_QUALITY_BUCKETS = frozenset({"HIGH", "MEDIUM", "LOW"})

_KNOWN_DOMAINS = frozenset({"simulation", "alphaforge", "v7"})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_nested(d: dict, dotted_path: str, default: Any = None) -> Any:
    """Resolve a dot-separated path in a nested dict.

    Example: _get_nested(sim, "long_outcome.realized_r_net") -> 1.82
    """
    if not d:
        return default
    parts = dotted_path.split(".")
    current: Any = d
    for part in parts:
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def _set_nested(d: dict, dotted_path: str, value: Any) -> None:
    """Set a value at a dot-separated path in a nested dict.

    Intermediate dicts are created as needed.
    """
    parts = dotted_path.split(".")
    current = d
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _find_mapping_source(
    mappings: list[FieldMapping], target_field: str,
) -> str | None:
    """Return the source field of the first mapping that targets *target_field*."""
    for m in mappings:
        if m.target_field == target_field:
            return m.source_field
    return None


def _deduplicate_mappings(
    mappings: list[dict],
) -> list[dict]:
    """Remove duplicate mapping entries (same source + target), warn on each."""
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for entry in mappings:
        key = (entry.get("source", ""), entry.get("target", ""))
        if key in seen:
            logger.warning(
                "Duplicate mapping skipped: '%s' -> '%s'",
                key[0],
                key[1],
            )
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


# ---------------------------------------------------------------------------
# FieldMapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldMapping:
    """One field that crosses a domain boundary.

    Attributes:
        source_domain:  Domain the field originates from ("simulation", "alphaforge").
        source_field:   Dot-notation path in the source contract
                        (e.g. "long_outcome.realized_r_net").
        target_domain:  Domain consuming the field ("v7", "alphaforge").
        target_field:   Dot-notation field name in the target contract.
        required:       If True, a missing source value raises in strict mode.
        transform_fn:   Optional callable applied to the source value before
                        writing to the target.
        description:    Human-readable meaning of this mapping.
    """
    source_domain: str
    source_field: str
    target_domain: str
    target_field: str
    required: bool = True
    transform_fn: Callable[[Any], Any] | None = None
    description: str = ""


# ---------------------------------------------------------------------------
# Mapping loaders
# ---------------------------------------------------------------------------


def _load_json_mappings(
    path: Path,
    source_domain: str,
    target_domain: str,
) -> list[FieldMapping]:
    """Load a list of FieldMapping from a JSON mapping file."""
    with open(path) as f:
        data = json.load(f)

    raw = data.get("mappings", [])
    deduped = _deduplicate_mappings(raw)

    mappings: list[FieldMapping] = []
    for entry in deduped:
        mappings.append(FieldMapping(
            source_domain=source_domain,
            source_field=entry["source"],
            target_domain=target_domain,
            target_field=entry["target"],
            required=entry.get("required", True),
            description=entry.get("meaning", ""),
        ))
    return mappings


# ---------------------------------------------------------------------------
# AlphaForge -> V7 mappings  (from alphaforge_to_v7.md tables)
# ---------------------------------------------------------------------------

# These encode the structured evidence-field paths from alphaforge_to_v7.md.
#
# Source:  AlphaForge report/artifact fields (dot notation in the output dict).
# Target:  V7 gate assessment structure (grouped under "gates.G<N>_<NAME>",
#          "decision_input", "model_info", "handoff", "risk_assessment").
#
# Note: alphaforge_to_v7.md describes report-level mappings, not a flat
# field-to-field schema like the JSON mapping files. These paths reflect the
# structured nature of AlphaForge research outputs.

_ALPHAFORGE_TO_V7_DEFS: list[FieldMapping] = [
    # -- ModeResearchReport -> V7 gates --
    FieldMapping(
        "alphaforge", "data_scope",
        "v7", "gates.G0_DOC_READY.data_scope",
        True,
        description="Data scope (symbols, date range, data quality, timeframe stack) for G0 readiness",
    ),
    FieldMapping(
        "alphaforge", "metrics.oos_sharpe",
        "v7", "gates.G1_RESEARCH_BACKTEST.oos_sharpe",
        False,
        description="OOS Sharpe ratio for G1 backtest evidence",
    ),
    FieldMapping(
        "alphaforge", "metrics.oos_expectancy_r",
        "v7", "gates.G1_RESEARCH_BACKTEST.oos_expectancy_r",
        False,
        description="OOS expectancy in R for G1 backtest evidence",
    ),
    FieldMapping(
        "alphaforge", "metrics.oos_win_rate",
        "v7", "gates.G1_RESEARCH_BACKTEST.oos_win_rate",
        False,
        description="OOS win rate for G1 backtest evidence",
    ),
    FieldMapping(
        "alphaforge", "validation_summary.fold_count",
        "v7", "gates.G2_WALK_FORWARD_OOS.fold_count",
        False,
        description="Number of walk-forward folds for G2 evidence",
    ),
    FieldMapping(
        "alphaforge", "validation_summary.verdict",
        "v7", "gates.G2_WALK_FORWARD_OOS.verdict",
        True,
        description="Validation verdict for G2 walk-forward assessment",
    ),
    FieldMapping(
        "alphaforge", "validation_summary.overfit_risk",
        "v7", "gates.G2_WALK_FORWARD_OOS.overfit_risk",
        True,
        description="Overfit risk flag for G2 assessment",
    ),
    FieldMapping(
        "alphaforge", "cost_stress.fee_level",
        "v7", "gates.G3_COST_STRESS.fee_level",
        False,
        description="Fee stress level for G3 cost stress evaluation",
    ),
    FieldMapping(
        "alphaforge", "cost_stress.slippage_level",
        "v7", "gates.G3_COST_STRESS.slippage_level",
        False,
        description="Slippage stress level for G3 cost stress evaluation",
    ),
    FieldMapping(
        "alphaforge", "cost_stress.combined_stress",
        "v7", "gates.G3_COST_STRESS.combined_stress",
        False,
        description="Combined cost stress level for G3",
    ),
    FieldMapping(
        "alphaforge", "regime_breakdown",
        "v7", "gates.G4_REGIME_BREAKDOWN.regime_metrics",
        True,
        description="Per-regime metrics (TREND_UP/DOWN/RANGE/TRANSITION) for G4",
    ),
    FieldMapping(
        "alphaforge", "metrics",
        "v7", "gates.G5_SYMBOL_STABILITY.aggregate_metrics",
        False,
        description="Aggregate metrics for symbol/regime slicing consistency check at G5",
    ),
    FieldMapping(
        "alphaforge", "verdict",
        "v7", "decision_input.verdict",
        True,
        description="AlphaForge verdict as V7 decision input (PASS/PASS_WITH_LIMITATIONS/FAIL_*/INCONCLUSIVE)",
    ),
    FieldMapping(
        "alphaforge", "no_trade_comparison",
        "v7", "decision_input.no_trade_comparison",
        True,
        description="No-trade comparison evidence (cross-cutting quality check)",
    ),

    # -- ValidationReport -> V7 promotion gates --
    FieldMapping(
        "alphaforge", "split_policy",
        "v7", "gates.G0_DOC_READY.split_policy",
        True,
        description="Train/val/OOS split policy for G0-G2 methodology audit",
    ),
    FieldMapping(
        "alphaforge", "walk_forward_folds",
        "v7", "gates.G2_WALK_FORWARD_OOS.walk_forward_folds",
        True,
        description="Per-fold walk-forward metrics for detailed G2 evidence",
    ),
    FieldMapping(
        "alphaforge", "oos_summary",
        "v7", "gates.G2_WALK_FORWARD_OOS.oos_summary",
        True,
        description="Aggregate OOS metrics for G2 assessment",
    ),
    FieldMapping(
        "alphaforge", "overfit_risk_flags",
        "v7", "risk_assessment.overfit_risk_flags",
        True,
        description="Overfit risk flags for V7 risk assessment",
    ),
    FieldMapping(
        "alphaforge", "multiple_hypothesis_control",
        "v7", "risk_assessment.multiple_hypothesis_control",
        False,
        description="Multiple-hypothesis / data-snooping control evidence",
    ),
    FieldMapping(
        "alphaforge", "symbol_stability",
        "v7", "gates.G5_SYMBOL_STABILITY.symbol_stability",
        True,
        description="Per-symbol contribution analysis for G5 symbol stability",
    ),

    # -- ModelArtifact -> V7 model loading --
    FieldMapping(
        "alphaforge", "model_artifact_id",
        "v7", "model_info.model_artifact_id",
        True,
        description="Model artifact identity for model loading",
    ),
    FieldMapping(
        "alphaforge", "artifact_uri",
        "v7", "model_info.artifact_uri",
        True,
        description="Model artifact URI for model loading",
    ),
    FieldMapping(
        "alphaforge", "checksum",
        "v7", "model_info.checksum",
        True,
        description="Model integrity checksum for verification",
    ),
    FieldMapping(
        "alphaforge", "model_family",
        "v7", "model_info.model_family",
        True,
        description="Model family for V7 compatibility check",
    ),
    FieldMapping(
        "alphaforge", "feature_set_id",
        "v7", "model_info.feature_set_id",
        True,
        description="Feature set ID for V7 feature compatibility check",
    ),
    FieldMapping(
        "alphaforge", "training_metrics",
        "v7", "model_info.training_metrics",
        True,
        description="Training metrics as quality baseline for V7",
    ),
    FieldMapping(
        "alphaforge", "hyperparameters",
        "v7", "model_info.hyperparameters",
        False,
        description="Hyperparameters for reproducibility",
    ),
    FieldMapping(
        "alphaforge", "limitations",
        "v7", "model_info.limitations",
        False,
        description="Known limitations for V7 awareness during evaluation",
    ),

    # -- CalibrationCandidate -> V7 calibration gate --
    FieldMapping(
        "alphaforge", "calibration_method",
        "v7", "gates.G6_CALIBRATION_RELIABILITY.calibration_method",
        True,
        description="Calibration method used, for G6 assessment",
    ),
    FieldMapping(
        "alphaforge", "calibration_metrics.ece",
        "v7", "gates.G6_CALIBRATION_RELIABILITY.ece",
        True,
        description="Expected calibration error (ECE) for G6 gate",
    ),
    FieldMapping(
        "alphaforge", "confidence_bins",
        "v7", "gates.G6_CALIBRATION_RELIABILITY.confidence_bins",
        True,
        description="Bin-level confidence reliability for G6",
    ),
    FieldMapping(
        "alphaforge", "status",
        "v7", "gates.G6_CALIBRATION_RELIABILITY.status",
        True,
        description="Calibration status (CALIBRATED/UNCALIBRATED/UNRELIABLE) for G6 go/no-go",
    ),

    # -- V7HandoffPackage -> V7 review queue --
    FieldMapping(
        "alphaforge", "handoff_package_id",
        "v7", "handoff.handoff_package_id",
        True,
        description="Handoff package identity for V7 tracking",
    ),
    FieldMapping(
        "alphaforge", "v7_gate_mapping",
        "v7", "handoff.v7_gate_mapping",
        True,
        description="Gate-to-evidence mapping from AlphaForge for V7 evaluation",
    ),
    FieldMapping(
        "alphaforge", "recommended_status",
        "v7", "handoff.recommended_status",
        True,
        description="AlphaForge recommended status (PROMOTION_CANDIDATE, etc.)",
    ),
    FieldMapping(
        "alphaforge", "blocked_scopes",
        "v7", "handoff.blocked_scopes",
        True,
        description="Scopes V7 should not extrapolate to",
    ),
    FieldMapping(
        "alphaforge", "lineage",
        "v7", "handoff.lineage",
        True,
        description="Full provenance data for V7 audit",
    ),
    FieldMapping(
        "alphaforge", "rejection_rules_applied",
        "v7", "handoff.rejection_rules_applied",
        True,
        description="Which rejection rules were checked before handoff",
    ),
]


# ---------------------------------------------------------------------------
# CrossDomainMapper
# ---------------------------------------------------------------------------


class CrossDomainMapper:
    """Maps fields across V7 Engine domain boundaries using contract-defined mappings.

    Three mapping pipelines are available:
      1. SimulationOutput -> V7 (TradeOutcome fields)
      2. SimulationOutput -> AlphaForge (label dataset fields)
      3. AlphaForge research output -> V7 (gate assessment evidence)

    Usage::

        mapper = CrossDomainMapper()
        trade = mapper.map_simulation_to_v7(sim_output)
        labels = mapper.map_simulation_to_alphaforge(sim_output)
        assessment = mapper.map_alphaforge_to_v7(af_report)
    """

    def __init__(
        self,
        sim_to_v7_path: str | Path | None = None,
        sim_to_alphaforge_path: str | Path | None = None,
    ):
        self._sim_to_v7 = _load_json_mappings(
            Path(sim_to_v7_path) if sim_to_v7_path else _SIM_TO_V7_PATH,
            source_domain="simulation",
            target_domain="v7",
        )
        self._sim_to_alphaforge = _load_json_mappings(
            Path(sim_to_alphaforge_path) if sim_to_alphaforge_path
            else _SIM_TO_ALPHAFORGE_PATH,
            source_domain="simulation",
            target_domain="alphaforge",
        )

    # -- Accessors -----------------------------------------------------------

    @property
    def simulation_to_v7_mappings(self) -> list[FieldMapping]:
        """Return the sim->v7 mapping definitions."""
        return list(self._sim_to_v7)

    @property
    def simulation_to_alphaforge_mappings(self) -> list[FieldMapping]:
        """Return the sim->alphaforge mapping definitions."""
        return list(self._sim_to_alphaforge)

    @property
    def alphaforge_to_v7_mappings(self) -> list[FieldMapping]:
        """Return the alphaforge->v7 mapping definitions."""
        return list(_ALPHAFORGE_TO_V7_DEFS)

    # -- Mapping methods -----------------------------------------------------

    def map_simulation_to_v7(
        self,
        sim_output: dict,
        *,
        strict: bool = False,
    ) -> dict:
        """Map a SimulationOutput dict to a V7 TradeOutcome dict.

        Uses the field mappings defined in contracts/mappings/simulation_to_v7.json.

        Args:
            sim_output: SimulationOutput dict from the simulation engine.
            strict:     If True, raise ``KeyError`` when a required source field
                        is missing.  If False (default), missing required fields
                        are simply omitted.

        Returns:
            A dict keyed by V7 ``TradeOutcome`` field names.
        """
        return self._apply_mappings(
            sim_output, self._sim_to_v7, strict=strict,
        )

    def map_simulation_to_alphaforge(
        self,
        sim_output: dict,
        *,
        strict: bool = False,
    ) -> dict:
        """Map a SimulationOutput dict to an AlphaForge label dict.

        Uses the field mappings defined in
        contracts/mappings/simulation_to_alphaforge.json.

        Args:
            sim_output: SimulationOutput dict.
            strict:     If True, raise ``KeyError`` on missing required fields.

        Returns:
            A dict keyed by AlphaForge label field names.
        """
        return self._apply_mappings(
            sim_output, self._sim_to_alphaforge, strict=strict,
        )

    def map_alphaforge_to_v7(
        self,
        af_output: dict,
        *,
        strict: bool = False,
    ) -> dict:
        """Map an AlphaForge research output dict to a V7 gate assessment dict.

        Uses the field mappings from ``contracts/mappings/alphaforge_to_v7.md``
        (encoded in this module).  The output is structured by gate
        (G0_DOC_READY through G10_LIVE) and cross-cutting concerns
        (decision_input, model_info, risk_assessment, handoff).

        Args:
            af_output: AlphaForge output dict (may contain fields from any
                       AlphaForge report or artifact type).
            strict:    If True, raise ``KeyError`` on missing required fields.

        Returns:
            A dict structured per V7 gates and decision inputs.
        """
        return self._apply_mappings(
            af_output, _ALPHAFORGE_TO_V7_DEFS, strict=strict,
        )

    # -- Validation ----------------------------------------------------------

    @staticmethod
    def validate_field_mapping(mapping_def: dict) -> list[str]:
        """Validate a single mapping definition for structural correctness.

        Checks performed:
          * Required keys (``source``, ``target``) are present.
          * ``source`` is a well-formed dot path (no leading/trailing dots).
          * ``target`` is a non-empty string.
          * ``required`` is a boolean if present.
          * ``meaning`` is a string if present.

        Args:
            mapping_def: A dict representing one mapping entry.

        Returns:
            List of error strings.  Empty list means valid.
        """
        errors: list[str] = []

        # --- Required keys ---
        for key in ("source", "target"):
            if key not in mapping_def:
                errors.append(f"Missing required key '{key}'")

        # --- source field ---
        src = mapping_def.get("source")
        if src is not None and not isinstance(src, str):
            errors.append(f"'source' must be a string, got {type(src).__name__}")
        elif isinstance(src, str):
            if not src:
                errors.append("'source' must not be empty")
            if src.startswith("."):
                errors.append(f"'source' starts with a dot: '{src}'")
            if src.endswith("."):
                errors.append(f"'source' ends with a dot: '{src}'")
            if ".." in src:
                errors.append(f"'source' contains consecutive dots: '{src}'")

        # --- target field ---
        tgt = mapping_def.get("target")
        if tgt is not None and not isinstance(tgt, str):
            errors.append(f"'target' must be a string, got {type(tgt).__name__}")
        elif isinstance(tgt, str) and not tgt:
            errors.append("'target' must not be empty")

        # --- required flag ---
        if "required" in mapping_def and not isinstance(mapping_def["required"], bool):
            errors.append("'required' must be a boolean")

        # --- meaning ---
        if "meaning" in mapping_def and not isinstance(mapping_def["meaning"], str):
            errors.append("'meaning' must be a string")

        return errors

    def validate_all_simulation_to_v7(self) -> list[str]:
        """Run ``validate_field_mapping`` over every sim->v7 mapping.

        Returns:
            List of prefixed error strings, one per validation failure.
        """
        return self._validate_mapping_list(self._sim_to_v7, prefix="[sim->v7]")

    def validate_all_simulation_to_alphaforge(self) -> list[str]:
        """Run ``validate_field_mapping`` over every sim->alphaforge mapping."""
        return self._validate_mapping_list(
            self._sim_to_alphaforge, prefix="[sim->af]",
        )

    def validate_all_alphaforge_to_v7(self) -> list[str]:
        """Run ``validate_field_mapping`` over every alphaforge->v7 mapping."""
        return self._validate_mapping_list(
            _ALPHAFORGE_TO_V7_DEFS, prefix="[af->v7]",
        )

    # -- Internal helpers ----------------------------------------------------

    @staticmethod
    def _apply_mappings(
        source: dict,
        mappings: list[FieldMapping],
        *,
        strict: bool = False,
    ) -> dict:
        """Apply a list of ``FieldMapping`` to a source dict.

        Returns a flat/target-nested dict with only mapped fields.

        If multiple mappings target the same field, the **first** one wins
        and a warning is logged for subsequent duplicates.  This guards
        against accidental overwrites in the mapping definitions (e.g. the
        known ``long_outcome.fee_cost_r -> realized_r`` collision in
        ``simulation_to_v7.json`` that duplicates the intended
        ``realized_r_net -> realized_r`` mapping).
        """
        result: dict[str, Any] = {}
        missing: list[str] = []
        seen_targets: set[str] = set()

        for mapping in mappings:
            raw_value = _get_nested(source, mapping.source_field)

            if raw_value is None:
                if mapping.required:
                    missing.append(mapping.source_field)
                continue

            # Guard against duplicate target fields — first mapping wins.
            if mapping.target_field in seen_targets:
                logger.warning(
                    "Duplicate target field '%s' (previous source: "
                    "'%s', current source: '%s'). Skipping.",
                    mapping.target_field,
                    _find_mapping_source(mappings, mapping.target_field),
                    mapping.source_field,
                )
                continue

            if mapping.transform_fn is not None:
                try:
                    value = mapping.transform_fn(raw_value)
                except Exception as exc:
                    raise ValueError(
                        f"Transform failed for '{mapping.source_field}': {exc}"
                    ) from exc
            else:
                value = raw_value

            _set_nested(result, mapping.target_field, value)
            seen_targets.add(mapping.target_field)

        if strict and missing:
            raise KeyError(
                f"Missing required source field(s): {', '.join(missing)}"
            )

        return result

    @staticmethod
    def _validate_mapping_list(
        mappings: list[FieldMapping],
        prefix: str = "",
    ) -> list[str]:
        """Validate a list of FieldMapping objects."""
        errors: list[str] = []
        for m in mappings:
            entry = {
                "source": m.source_field,
                "target": m.target_field,
                "required": m.required,
            }
            for err in CrossDomainMapper.validate_field_mapping(entry):
                errors.append(f"{prefix} {m.source_field} -> {m.target_field}: {err}")

        # Also check for duplicate target fields (collision detection).
        seen_targets: dict[str, str] = {}
        for m in mappings:
            if m.target_field in seen_targets:
                errors.append(
                    f"{prefix} Duplicate target field '{m.target_field}' "
                    f"(sources: '{seen_targets[m.target_field]}' and '{m.source_field}')"
                )
            else:
                seen_targets[m.target_field] = m.source_field

        return errors
