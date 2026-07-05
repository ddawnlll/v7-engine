"""Lineage tracking — provenance refs on every row, checksum chain verification.

Implements LineageTracker for building LineageProvenance records and
computing label checksums.

Key rules:
  - LineageProvenance is frozen (immutable after construction).
  - Missing required fields raise LineageError with explicit field name.
  - label_checksum is either extracted from the label row or computed via
    SHA-256 over canonical JSON of label fields.
  - No ML library imports.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict

from alphaforge.dataset.contracts import LineageProvenance


class LineageError(ValueError):
    """Raised when a required lineage field cannot be populated."""

    def __init__(self, field_name: str, detail: str = "") -> None:
        self.field_name = field_name
        self.detail = detail
        msg = f"Missing required lineage field '{field_name}'"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class LineageTracker:
    """Builds LineageProvenance records for assembled dataset rows.

    Zero ML dependencies.  Uses stdlib hashlib for SHA-256.
    """

    # ------------------------------------------------------------------
    # Canonical label fields used for checksum computation
    # ------------------------------------------------------------------

    CANONICAL_LABEL_FIELDS = [
        "long_R_net",
        "short_R_net",
        "best_action_label",
        "label_validity",
        "no_trade_quality",
        "cost_impact_long",
        "cost_impact_short",
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_provenance(
        self,
        label_row: Dict[str, Any],
        feature_spec: Dict[str, Any],
        label_spec: Dict[str, Any],
        manifest_id: str,
        assembled_at: str = "",
    ) -> LineageProvenance:
        """Build a LineageProvenance from label row + specs.

        Args:
            label_row:  One row from the label DataFrame (as dict).
            feature_spec: FeatureSetSpec as dict.
            label_spec:  LabelDatasetSpec as dict.
            manifest_id: DataManifest identifier.
            assembled_at: ISO 8601 UTC timestamp (optional; current time if empty).

        Returns:
            Frozen LineageProvenance with all 7 fields populated.

        Raises:
            LineageError: if any required field is missing.
        """
        # --- Validate required inputs -----------------------------------------
        if not manifest_id:
            raise LineageError("source_manifest_id", "manifest_id is empty")

        feature_set_id = feature_spec.get("feature_set_id", "")
        if not feature_set_id:
            raise LineageError("feature_set_id", "missing from feature_spec")

        label_dataset_id = label_spec.get("label_dataset_id", "")
        if not label_dataset_id:
            raise LineageError("label_dataset_id", "missing from label_spec")

        simulation_profile_id = label_spec.get("simulation_profile_id", "")
        if not simulation_profile_id:
            raise LineageError(
                "simulation_profile_id", "missing from label_spec"
            )

        # --- Compute or extract label checksum --------------------------------
        label_checksum = self._resolve_label_checksum(label_row)

        # --- Assemble provenance ----------------------------------------------
        if not assembled_at:
            assembled_at = datetime.now(timezone.utc).isoformat()

        return LineageProvenance(
            source_manifest_id=manifest_id,
            label_checksum=label_checksum,
            feature_spec_version=feature_set_id,
            feature_set_id=feature_set_id,
            label_dataset_id=label_dataset_id,
            simulation_profile_id=simulation_profile_id,
            assembled_at=assembled_at,
        )

    # ------------------------------------------------------------------
    # Checksum helpers
    # ------------------------------------------------------------------

    def _resolve_label_checksum(self, label_row: Dict[str, Any]) -> str:
        """Extract or compute label checksum.

        If label_row carries a pre-computed 'label_checksum', use it.
        Otherwise compute SHA-256 over canonical JSON of label fields.
        """
        if "label_checksum" in label_row:
            checksum = label_row["label_checksum"]
            if checksum and str(checksum).strip():
                return str(checksum).strip()

        # Not present — compute
        return self.compute_label_checksum(label_row)

    def compute_label_checksum(self, label_row: Dict[str, Any]) -> str:
        """Compute SHA-256 over canonical JSON of CANONICAL_LABEL_FIELDS.

        Sorted keys, deterministic float formatting.
        """
        canonical_dict: Dict[str, Any] = {}
        for field in self.CANONICAL_LABEL_FIELDS:
            val = label_row.get(field)
            canonical_dict[field] = self._canonicalize_value(val)

        json_bytes = json.dumps(canonical_dict, sort_keys=True).encode("utf-8")
        return hashlib.sha256(json_bytes).hexdigest()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _canonicalize_value(value: Any) -> Any:
        """Canonicalize a single value for deterministic serialization.

        Floats: round to 10 decimal places and format consistently.
        Strings: return as-is.
        None: return null sentinel.
        """
        if value is None or (isinstance(value, float) and value != value):  # NaN check
            return None
        if isinstance(value, float):
            # Round to 10 decimal places for deterministic checksum
            return round(value, 10)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, str)):
            return value
        return str(value)
