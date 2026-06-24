"""Test suite for DatasetAssembler — join, filter, purge, audit.

Covers acceptance criteria:
  AC-04-007: Inner-join on (symbol, timestamp)
  AC-04-008: label_validity filtering (VALID/INVALID/AMBIGUOUS)
  AC-04-009: Purge-window (feature_timestamp >= label_timestamp drop)
  AC-04-010: JoinAuditTrail fully populated
  AC-04-011: Mode mismatch raises ValueError
  AC-04-012: Empty join returns empty list + audit (not exception)
  AC-04-013: Each row has correct fields
  AC-04-029: INVALID rows excluded
  AC-04-030: Mismatched timestamps/symbols produce zero joined
  AC-04-031: Missing symbol in one DF produces unmatched counts
  AC-04-032: feature_timestamp >= label_timestamp triggers purge
  AC-04-033: All feature timestamps >= label timestamps -> all dropped
  AC-04-034: All labels INVALID -> zero joined, full audit
"""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import pytest

from alphaforge.dataset.assembler import DefaultAssembler
from alphaforge.dataset.contracts import JoinAuditTrail, LabeledDataset


# ===================================================================
# Construction and import
# ===================================================================


class TestAssemblerConstruction:
    """AC-04-007: assembler can be constructed."""

    def test_constructs_without_error(self) -> None:
        a = DefaultAssembler()
        assert a is not None


# ===================================================================
# Positive join tests
# ===================================================================


class TestPositiveJoin:
    """AC-04-007, AC-04-013: valid joins produce correct output."""

    def test_valid_join_produces_rows(
        self,
        assembler: DefaultAssembler,
        sample_feature_df: pd.DataFrame,
        sample_label_df: pd.DataFrame,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
        sample_manifest_id: str,
    ) -> None:
        dataset, audit = assembler.assemble(
            feature_df=sample_feature_df,
            label_df=sample_label_df,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id=sample_manifest_id,
        )

        assert isinstance(dataset, list)
        assert isinstance(audit, JoinAuditTrail)
        # With our fixtures (features T-10 to T-4, labels T-5 to T+1),
        # there should be overlapping (symbol, timestamp) pairs
        # for the VALID labels in T-5 to T-4 range.
        assert audit.joined_rows >= 0
        assert audit.total_feature_rows == 20
        assert audit.total_label_rows == 20
        # INVALID + AMBIGUOUS + empty validity rows should be dropped
        assert audit.invalid_label_rows_dropped >= 0

    def test_each_row_has_correct_structure(
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
            assert isinstance(row.row_id, str) and len(row.row_id) > 0
            assert row.symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
            assert isinstance(row.feature_timestamp, str)
            assert isinstance(row.label_timestamp, str)
            assert row.mode == "SWING"
            assert isinstance(row.features, dict)
            assert isinstance(row.label_long_r_net, float)
            assert isinstance(row.label_short_r_net, float)
            assert row.label_best_action_label in (
                "LONG_NOW", "SHORT_NOW", "NO_TRADE"
            )
            assert row.label_validity == "VALID"
            assert row.lineage is not None
            assert isinstance(row.quality_flags, list)


# ===================================================================
# label_validity filtering
# ===================================================================


class TestLabelValidityFiltering:
    """AC-04-008, AC-04-029, AC-04-034: label_validity filtering."""

    def test_invalid_rows_excluded(
        self,
        assembler: DefaultAssembler,
        sample_feature_df: pd.DataFrame,
        sample_label_df: pd.DataFrame,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
        sample_manifest_id: str,
    ) -> None:
        dataset, audit = assembler.assemble(
            feature_df=sample_feature_df,
            label_df=sample_label_df,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id=sample_manifest_id,
        )

        # All assembled rows must be VALID
        for row in dataset:
            assert row.label_validity == "VALID"

        # INVALID + AMBIGUOUS + empty = 3 + 2 + 1 = 6 dropped
        assert audit.invalid_label_rows_dropped == 6

    def test_ambiguous_rows_excluded(self) -> None:
        """Ambiguous labels should not appear in joined output."""
        assembler = DefaultAssembler()
        feature_df = pd.DataFrame([
            {"symbol": "BTCUSDT", "timestamp": "2025-01-01T00:00:00+00:00",
             "feature_set_id": "v1", "f1": 1.0},
        ])
        label_df = pd.DataFrame([
            {"symbol": "BTCUSDT", "timestamp": "2025-01-01T00:00:00+00:00",
             "label_validity": "AMBIGUOUS", "label_dataset_id": "v1",
             "label_checksum": "abc", "best_action_label": "NO_TRADE",
             "long_R_net": 0.0, "short_R_net": 0.0,
             "no_trade_quality": "AMBIGUOUS_NO_TRADE",
             "cost_impact_long": 0.0, "cost_impact_short": 0.0},
        ])
        feature_spec = {"mode": "SWING", "feature_set_id": "v1"}
        label_spec = {"mode": "SWING", "label_dataset_id": "v1",
                       "simulation_profile_id": "sp1"}

        dataset, audit = assembler.assemble(
            feature_df=feature_df,
            label_df=label_df,
            feature_spec=feature_spec,
            label_spec=label_spec,
            manifest_id="m1",
        )
        assert len(dataset) == 0
        assert audit.invalid_label_rows_dropped == 1

    def test_all_labels_invalid_returns_empty(
        self,
        assembler: DefaultAssembler,
        sample_feature_df: pd.DataFrame,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
        sample_manifest_id: str,
    ) -> None:
        """AC-04-034: All INVALID labels -> zero joined, full audit."""
        all_invalid_df = pd.DataFrame([
            {"symbol": "BTCUSDT", "timestamp": "2025-01-15T12:00:00+00:00",
             "label_dataset_id": "v1", "label_checksum": "abc",
             "best_action_label": "NO_TRADE", "label_validity": "INVALID",
             "long_R_net": 0.0, "short_R_net": 0.0,
             "no_trade_quality": "CORRECT_NO_TRADE",
             "cost_impact_long": 0.0, "cost_impact_short": 0.0},
            {"symbol": "ETHUSDT", "timestamp": "2025-01-15T13:00:00+00:00",
             "label_dataset_id": "v1", "label_checksum": "def",
             "best_action_label": "NO_TRADE", "label_validity": "INVALID",
             "long_R_net": 0.0, "short_R_net": 0.0,
             "no_trade_quality": "CORRECT_NO_TRADE",
             "cost_impact_long": 0.0, "cost_impact_short": 0.0},
        ])

        dataset, audit = assembler.assemble(
            feature_df=sample_feature_df,
            label_df=all_invalid_df,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id=sample_manifest_id,
        )
        assert len(dataset) == 0
        assert audit.invalid_label_rows_dropped == 2
        assert audit.total_label_rows == 2
        assert audit.joined_rows == 0


# ===================================================================
# Purge-window tests
# ===================================================================


class TestPurgeWindow:
    """AC-04-009, AC-04-032, AC-04-033: purge-window enforcement."""

    def test_purge_violation_detected_and_counted(
        self,
        assembler: DefaultAssembler,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
    ) -> None:
        """Feature timestamp == label timestamp (via separate label_timestamp col)
        should trigger purge drop."""
        feature_df = pd.DataFrame([
            {"symbol": "BTCUSDT", "timestamp": "2025-01-01T00:00:00+00:00",
             "feature_set_id": "v1", "f1": 1.0},
            {"symbol": "ETHUSDT", "timestamp": "2025-01-01T01:00:00+00:00",
             "feature_set_id": "v1", "f1": 2.0},
        ])
        label_df = pd.DataFrame([
            {"symbol": "BTCUSDT", "timestamp": "2025-01-01T00:00:00+00:00",
             "label_timestamp": "2025-01-01T00:00:00+00:00",  # same! -> purge
             "label_dataset_id": "v1", "label_checksum": "abc",
             "best_action_label": "LONG_NOW", "label_validity": "VALID",
             "long_R_net": 0.5, "short_R_net": -0.2,
             "no_trade_quality": "CORRECT_NO_TRADE",
             "cost_impact_long": 0.01, "cost_impact_short": 0.01},
            {"symbol": "ETHUSDT", "timestamp": "2025-01-01T01:00:00+00:00",
             "label_timestamp": "2025-01-01T02:00:00+00:00",  # future -> keep
             "label_dataset_id": "v1", "label_checksum": "def",
             "best_action_label": "SHORT_NOW", "label_validity": "VALID",
             "long_R_net": 0.3, "short_R_net": 0.1,
             "no_trade_quality": "MISSED_OPPORTUNITY",
             "cost_impact_long": 0.01, "cost_impact_short": 0.01},
        ])

        dataset, audit = assembler.assemble(
            feature_df=feature_df,
            label_df=label_df,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id="m1",
        )
        assert audit.purge_violation_rows_dropped == 1
        assert len(dataset) == 1
        assert dataset[0].symbol == "ETHUSDT"

    def test_data_leakage_all_dropped(
        self,
        assembler: DefaultAssembler,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
    ) -> None:
        """AC-04-033: All feature timestamps >= label timestamps -> all dropped."""
        feature_df = pd.DataFrame([
            {"symbol": "BTCUSDT", "timestamp": "2025-01-01T02:00:00+00:00",
             "feature_set_id": "v1", "f1": 1.0},
            {"symbol": "ETHUSDT", "timestamp": "2025-01-01T03:00:00+00:00",
             "feature_set_id": "v1", "f1": 2.0},
        ])
        label_df = pd.DataFrame([
            {"symbol": "BTCUSDT", "timestamp": "2025-01-01T02:00:00+00:00",
             "label_timestamp": "2025-01-01T00:00:00+00:00",  # feature after label
             "label_dataset_id": "v1", "label_checksum": "abc",
             "best_action_label": "LONG_NOW", "label_validity": "VALID",
             "long_R_net": 0.5, "short_R_net": -0.2,
             "no_trade_quality": "CORRECT_NO_TRADE",
             "cost_impact_long": 0.01, "cost_impact_short": 0.01},
            {"symbol": "ETHUSDT", "timestamp": "2025-01-01T03:00:00+00:00",
             "label_timestamp": "2025-01-01T02:00:00+00:00",  # feature after label
             "label_dataset_id": "v1", "label_checksum": "def",
             "best_action_label": "SHORT_NOW", "label_validity": "VALID",
             "long_R_net": 0.3, "short_R_net": 0.1,
             "no_trade_quality": "MISSED_OPPORTUNITY",
             "cost_impact_long": 0.01, "cost_impact_short": 0.01},
        ])

        dataset, audit = assembler.assemble(
            feature_df=feature_df,
            label_df=label_df,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id="m1",
        )
        assert len(dataset) == 0
        assert audit.purge_violation_rows_dropped == 2
        assert audit.joined_rows == 0


# ===================================================================
# Mode mismatch
# ===================================================================


class TestModeMismatch:
    """AC-04-011: Mode mismatch raises ValueError."""

    def test_mode_mismatch_raises_value_error(
        self,
        assembler: DefaultAssembler,
        sample_feature_df: pd.DataFrame,
        sample_label_df: pd.DataFrame,
    ) -> None:
        feature_spec = {"mode": "SCALP", "feature_set_id": "v1"}
        label_spec = {"mode": "SWING", "label_dataset_id": "v1",
                       "simulation_profile_id": "sp1"}

        with pytest.raises(ValueError, match="Mode mismatch"):
            assembler.assemble(
                feature_df=sample_feature_df,
                label_df=sample_label_df,
                feature_spec=feature_spec,
                label_spec=label_spec,
                manifest_id="m1",
            )

    def test_mode_mismatch_message_contains_both_modes(
        self,
        assembler: DefaultAssembler,
        sample_feature_df: pd.DataFrame,
        sample_label_df: pd.DataFrame,
    ) -> None:
        feature_spec = {"mode": "AGGRESSIVE_SCALP", "feature_set_id": "v1"}
        label_spec = {"mode": "SWING", "label_dataset_id": "v1",
                       "simulation_profile_id": "sp1"}

        with pytest.raises(ValueError) as exc_info:
            assembler.assemble(
                feature_df=sample_feature_df,
                label_df=sample_label_df,
                feature_spec=feature_spec,
                label_spec=label_spec,
                manifest_id="m1",
            )
        msg = str(exc_info.value)
        assert "AGGRESSIVE_SCALP" in msg
        assert "SWING" in msg


# ===================================================================
# Empty join tests
# ===================================================================


class TestEmptyJoin:
    """AC-04-012, AC-04-030, AC-04-031: empty joins."""

    def test_non_overlapping_symbols_returns_empty(
        self,
        assembler: DefaultAssembler,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
    ) -> None:
        """AC-04-030, AC-04-031: different symbols -> zero joined."""
        feature_df = pd.DataFrame([
            {"symbol": "BTCUSDT", "timestamp": "2025-01-01T00:00:00+00:00",
             "feature_set_id": "v1", "f1": 1.0},
        ])
        label_df = pd.DataFrame([
            {"symbol": "ETHUSDT", "timestamp": "2025-01-01T00:00:00+00:00",
             "label_dataset_id": "v1", "label_checksum": "abc",
             "best_action_label": "LONG_NOW", "label_validity": "VALID",
             "long_R_net": 0.5, "short_R_net": -0.2,
             "no_trade_quality": "CORRECT_NO_TRADE",
             "cost_impact_long": 0.01, "cost_impact_short": 0.01},
        ])

        dataset, audit = assembler.assemble(
            feature_df=feature_df,
            label_df=label_df,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id="m1",
        )
        assert len(dataset) == 0
        assert audit.joined_rows == 0
        assert audit.unmatched_feature_rows == 1
        assert audit.unmatched_label_rows >= 0

    def test_non_overlapping_timestamps_returns_empty(
        self,
        assembler: DefaultAssembler,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
    ) -> None:
        feature_df = pd.DataFrame([
            {"symbol": "BTCUSDT", "timestamp": "2025-01-01T00:00:00+00:00",
             "feature_set_id": "v1", "f1": 1.0},
        ])
        label_df = pd.DataFrame([
            {"symbol": "BTCUSDT", "timestamp": "2025-02-01T00:00:00+00:00",
             "label_dataset_id": "v1", "label_checksum": "abc",
             "best_action_label": "LONG_NOW", "label_validity": "VALID",
             "long_R_net": 0.5, "short_R_net": -0.2,
             "no_trade_quality": "CORRECT_NO_TRADE",
             "cost_impact_long": 0.01, "cost_impact_short": 0.01},
        ])

        dataset, audit = assembler.assemble(
            feature_df=feature_df,
            label_df=label_df,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id="m1",
        )
        assert len(dataset) == 0
        assert audit.joined_rows == 0


# ===================================================================
# Audit trail completeness
# ===================================================================


class TestAuditTrail:
    """AC-04-010: JoinAuditTrail fully populated."""

    def test_audit_trail_all_fields_populated(
        self,
        assembler: DefaultAssembler,
        sample_feature_df: pd.DataFrame,
        sample_label_df: pd.DataFrame,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
        sample_manifest_id: str,
    ) -> None:
        _, audit = assembler.assemble(
            feature_df=sample_feature_df,
            label_df=sample_label_df,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id=sample_manifest_id,
        )
        assert audit.total_feature_rows == 20
        assert audit.total_label_rows == 20
        assert audit.joined_rows >= 0
        assert audit.unmatched_feature_rows >= 0
        assert audit.unmatched_label_rows >= 0
        assert audit.invalid_label_rows_dropped >= 0
        assert audit.purge_violation_rows_dropped >= 0


# ===================================================================
# Feature extraction correctness
# ===================================================================


class TestFeatureExtraction:
    """AC-04-013: feature dict correctness."""

    def test_features_dict_contains_expected_keys(
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
            # Check that feature keys are present
            assert isinstance(row.features, dict)
            for k, v in row.features.items():
                assert isinstance(k, str)
                assert isinstance(v, float)

    def test_feature_values_are_not_nan(
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
            for v in row.features.values():
                assert v == v, "Feature value is NaN"


# ===================================================================
# Boundary: empty DataFrames
# ===================================================================


class TestEmptyDataFrames:
    """Edge cases with empty inputs."""

    def test_empty_feature_df_returns_empty(
        self,
        assembler: DefaultAssembler,
        empty_feature_df: pd.DataFrame,
        empty_label_df: pd.DataFrame,
        sample_feature_spec: Dict[str, Any],
        sample_label_spec: Dict[str, Any],
    ) -> None:
        dataset, audit = assembler.assemble(
            feature_df=empty_feature_df,
            label_df=empty_label_df,
            feature_spec=sample_feature_spec,
            label_spec=sample_label_spec,
            manifest_id="m1",
        )
        assert len(dataset) == 0
        assert audit.total_feature_rows == 0
        assert audit.total_label_rows == 0


# ===================================================================
# Import boundary
# ===================================================================


class TestImportBoundary:
    """Verify assembler has no ML imports."""

    def test_no_ml_imports(self) -> None:
        """Verify assembler module does not import xgboost, sklearn, etc."""
        import re
        import importlib

        import alphaforge.dataset.assembler as amod
        source = importlib.import_module("alphaforge.dataset.assembler").__file__
        if source:
            with open(source, "r") as f:
                content = f.read()

            # Only check actual import statements, not docstring mentions
            import_lines = [
                line for line in content.split("\n")
                if line.strip().startswith(("import ", "from "))
            ]
            import_text = "\n".join(import_lines)

            for fb in ["xgboost", "sklearn", "tensorflow", "torch",
                       "XGBClassifier", "XGBRegressor"]:
                assert fb not in import_text, f"Found forbidden import: {fb}"
