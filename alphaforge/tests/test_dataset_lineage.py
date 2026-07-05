"""Test suite for LineageTracker — provenance, checksum, immutability.

Covers acceptance criteria:
  AC-04-014: build_provenance() returns LineageProvenance with all 7 fields
  AC-04-015: Every assembled row has non-None lineage
  AC-04-016: source_manifest_id matches input
  AC-04-017: label_checksum computed or extracted; missing raises LineageError
              (Note: missing checksum falls back to computation — LineageError
               is for missing manifest_id/feature_set_id per AC-04-018)
  AC-04-018: Missing required field raises LineageError with field name
  AC-04-019: LineageProvenance is frozen
  AC-04-020: No ML imports
  AC-04-038: FrozenInstanceError on mutation attempt
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, Dict

import pandas as pd
import pytest

from alphaforge.dataset.assembler import DefaultAssembler
from alphaforge.dataset.contracts import LineageProvenance
from alphaforge.dataset.lineage import LineageError, LineageTracker


# ===================================================================
# build_provenance field completeness
# ===================================================================


class TestBuildProvenanceFields:
    """AC-04-014: all 7 required fields populated."""

    def test_all_fields_populated(
        self,
        tracker: LineageTracker,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
    ) -> None:
        label_row = {
            "long_R_net": 0.5,
            "short_R_net": -0.2,
            "best_action_label": "LONG_NOW",
            "label_validity": "VALID",
            "no_trade_quality": "CORRECT_NO_TRADE",
            "cost_impact_long": 0.01,
            "cost_impact_short": 0.01,
        }
        prov = tracker.build_provenance(
            label_row=label_row,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id="manifest_test_001",
        )
        assert prov.source_manifest_id == "manifest_test_001"
        assert isinstance(prov.label_checksum, str) and len(prov.label_checksum) == 64
        assert prov.feature_spec_version == "swing_v1_features"
        assert prov.feature_set_id == "swing_v1_features"
        assert prov.label_dataset_id == "swing_v1_labels"
        assert prov.simulation_profile_id == "swing_baseline_v1"
        assert prov.assembled_at is not None
        # assembled_at should be ISO 8601 with timezone
        assert "T" in prov.assembled_at
        assert "+" in prov.assembled_at or "Z" in prov.assembled_at


# ===================================================================
# Assembled rows lineage
# ===================================================================


class TestAssembledRowLineage:
    """AC-04-015, AC-04-016: lineage on every assembled row."""

    def test_every_assembled_row_has_lineage(
        self,
        assembler: DefaultAssembler,
        sample_feature_df: pd.DataFrame,
        sample_label_df: pd.DataFrame,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
        sample_manifest_id: str,
    ) -> None:
        dataset, _ = assembler.assemble(
            feature_df=sample_feature_df,
            label_df=sample_label_df,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id=sample_manifest_id,
        )
        for row in dataset:
            assert row.lineage is not None, f"Row {row.row_id} has no lineage"
            assert isinstance(row.lineage, LineageProvenance)

    def test_manifest_id_matches_input(
        self,
        assembler: DefaultAssembler,
        sample_feature_df: pd.DataFrame,
        sample_label_df: pd.DataFrame,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
        sample_manifest_id: str,
    ) -> None:
        dataset, _ = assembler.assemble(
            feature_df=sample_feature_df,
            label_df=sample_label_df,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id=sample_manifest_id,
        )
        for row in dataset:
            assert row.lineage.source_manifest_id == sample_manifest_id


# ===================================================================
# Label checksum
# ===================================================================


class TestLabelChecksum:
    """AC-04-017: label_checksum computation and extraction."""

    def test_checksum_computed_when_not_in_row(
        self,
        tracker: LineageTracker,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
    ) -> None:
        label_row = {"long_R_net": 0.5, "short_R_net": -0.2}
        prov = tracker.build_provenance(
            label_row=label_row,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id="m1",
        )
        assert isinstance(prov.label_checksum, str)
        assert len(prov.label_checksum) == 64  # SHA-256 hex

    def test_checksum_extracted_when_present_in_row(
        self,
        tracker: LineageTracker,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
    ) -> None:
        label_row = {
            "long_R_net": 0.5,
            "short_R_net": -0.2,
            "label_checksum": "precomputed_hash_abc123",
        }
        prov = tracker.build_provenance(
            label_row=label_row,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id="m1",
        )
        assert prov.label_checksum == "precomputed_hash_abc123"

    def test_computed_checksum_is_deterministic(
        self,
        tracker: LineageTracker,
    ) -> None:
        label_row = {"long_R_net": 0.5, "short_R_net": -0.2,
                      "best_action_label": "LONG_NOW", "label_validity": "VALID",
                      "no_trade_quality": "CORRECT_NO_TRADE",
                      "cost_impact_long": 0.01, "cost_impact_short": 0.01}
        c1 = tracker.compute_label_checksum(label_row)
        c2 = tracker.compute_label_checksum(label_row)
        assert c1 == c2


# ===================================================================
# Missing required fields
# ===================================================================


class TestMissingRequiredFields:
    """AC-04-018: Missing required lineage fields raise LineageError."""

    def test_missing_manifest_id_raises(
        self,
        tracker: LineageTracker,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
    ) -> None:
        with pytest.raises(LineageError, match="source_manifest_id"):
            tracker.build_provenance(
                label_row={"long_R_net": 0.5},
                feature_spec=sample_feature_spec,
                label_spec=sample_label_spec,
                manifest_id="",  # empty
            )

    def test_missing_feature_set_id_raises(
        self,
        tracker: LineageTracker,
        sample_label_spec: Dict[str, Any],
    ) -> None:
        bad_feature_spec = {"mode": "SWING"}  # no feature_set_id
        with pytest.raises(LineageError, match="feature_set_id"):
            tracker.build_provenance(
                label_row={"long_R_net": 0.5},
                feature_spec=bad_feature_spec,
                label_spec=sample_label_spec,
                manifest_id="m1",
            )

    def test_missing_label_dataset_id_raises(
        self,
        tracker: LineageTracker,
        sample_feature_spec: Dict[str, Any],
    ) -> None:
        bad_label_spec = {"mode": "SWING", "simulation_profile_id": "sp1"}
        with pytest.raises(LineageError, match="label_dataset_id"):
            tracker.build_provenance(
                label_row={"long_R_net": 0.5},
                feature_spec=sample_feature_spec,
                label_spec=bad_label_spec,
                manifest_id="m1",
            )

    def test_missing_simulation_profile_id_raises(
        self,
        tracker: LineageTracker,
        sample_feature_spec: Dict[str, Any],
    ) -> None:
        bad_label_spec = {"mode": "SWING", "label_dataset_id": "v1"}
        with pytest.raises(LineageError, match="simulation_profile_id"):
            tracker.build_provenance(
                label_row={"long_R_net": 0.5},
                feature_spec=sample_feature_spec,
                label_spec=bad_label_spec,
                manifest_id="m1",
            )

    def test_error_message_contains_field_name(
        self,
        tracker: LineageTracker,
        sample_label_spec: Dict[str, Any],
    ) -> None:
        bad_feature_spec = {"mode": "SWING"}
        with pytest.raises(LineageError) as exc_info:
            tracker.build_provenance(
                label_row={"long_R_net": 0.5},
                feature_spec=bad_feature_spec,
                label_spec=sample_label_spec,
                manifest_id="m1",
            )
        assert "feature_set_id" in str(exc_info.value)


# ===================================================================
# Frozen / immutability
# ===================================================================


class TestLineageProvenanceFrozen:
    """AC-04-019, AC-04-038: frozen dataclass."""

    def test_cannot_mutate_after_construction(self) -> None:
        prov = LineageProvenance(
            source_manifest_id="m1",
            label_checksum="abc",
            feature_spec_version="v1",
            feature_set_id="v1",
            label_dataset_id="l1",
            simulation_profile_id="sp1",
            assembled_at="2025-01-01T00:00:00+00:00",
        )
        with pytest.raises(FrozenInstanceError):
            prov.source_manifest_id = "m2"  # type: ignore[misc]

    def test_frozen_prevents_field_set(self) -> None:
        prov = LineageProvenance(
            source_manifest_id="m1",
            label_checksum="abc",
            feature_spec_version="v1",
            feature_set_id="v1",
            label_dataset_id="l1",
            simulation_profile_id="sp1",
        )
        with pytest.raises(FrozenInstanceError):
            prov.label_checksum = "new_checksum"  # type: ignore[misc]


# ===================================================================
# Accuracy tests
# ===================================================================


class TestChecksumAccuracy:
    """Verify checksum behaves correctly for various inputs."""

    def test_different_labels_produce_different_checksums(
        self, tracker: LineageTracker
    ) -> None:
        c1 = tracker.compute_label_checksum({"long_R_net": 1.0, "short_R_net": -1.0})
        c2 = tracker.compute_label_checksum({"long_R_net": 2.0, "short_R_net": -2.0})
        assert c1 != c2

    def test_checksum_handles_nan_values(
        self, tracker: LineageTracker
    ) -> None:
        import math
        c1 = tracker.compute_label_checksum({
            "long_R_net": 1.0, "short_R_net": float("nan"),
            "best_action_label": "LONG_NOW", "label_validity": "VALID",
            "no_trade_quality": "CORRECT_NO_TRADE",
            "cost_impact_long": 0.01, "cost_impact_short": 0.01,
        })
        # Should compute without error
        assert isinstance(c1, str) and len(c1) == 64

    def test_checksum_handles_missing_fields(
        self, tracker: LineageTracker
    ) -> None:
        # Only one field present
        c1 = tracker.compute_label_checksum({"long_R_net": 1.0})
        assert isinstance(c1, str) and len(c1) == 64


# ===================================================================
# Import boundary
# ===================================================================


class TestImportBoundary:
    """AC-04-020: no ML imports."""

    def test_no_ml_imports(self) -> None:
        import alphaforge.dataset.lineage as lmod
        source = lmod.__file__
        if source:
            with open(source, "r") as f:
                content = f.read()
            import_lines = [
                line for line in content.split("\n")
                if line.strip().startswith(("import ", "from "))
            ]
            import_text = "\n".join(import_lines)
            for fb in ["xgboost", "sklearn", "tensorflow", "torch"]:
                assert fb not in import_text, f"Found forbidden import: {fb}"
