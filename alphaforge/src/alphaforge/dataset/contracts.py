"""AlphaForge Dataset contracts — dataclasses and protocols for dataset assembly.

Defines the LabeledDataset, LineageProvenance, and JoinAuditTrail dataclasses,
plus the DatasetAssembler and DatasetWriter protocols.

This module imports ZERO ML libraries.  It imports nothing from assembler.py,
writer.py, or lineage.py.  It is the authority for the dataset subpackage
interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Dict, List, Optional, Protocol, Tuple, runtime_checkable

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LineageProvenance:
    """Immutable provenance record for a single labeled data row.

    Carries all 7 required fields linking back to the source manifest,
    label dataset, feature spec, and simulation profile.

    Fields:
        source_manifest_id:  DataManifest identifier.
        label_checksum:      SHA-256 hex of canonical label fields.
        feature_spec_version: FeatureSetSpec feature_set_id (version proxy).
        feature_set_id:      FeatureSetSpec identifier.
        label_dataset_id:    LabelDatasetSpec identifier.
        simulation_profile_id: Simulation profile reference.
        assembled_at:        ISO 8601 UTC timestamp of assembly (None if not yet set).
    """

    source_manifest_id: str
    label_checksum: str
    feature_spec_version: str
    feature_set_id: str
    label_dataset_id: str
    simulation_profile_id: str
    assembled_at: Optional[str] = None


@dataclass(frozen=True)
class JoinAuditTrail:
    """Audit trail populated after every assemble() call.

    All fields are integer counts.
    """

    total_feature_rows: int = 0
    total_label_rows: int = 0
    joined_rows: int = 0
    unmatched_feature_rows: int = 0
    unmatched_label_rows: int = 0
    invalid_label_rows_dropped: int = 0
    purge_violation_rows_dropped: int = 0


@dataclass(frozen=True)
class LabeledDataset:
    """One row of an assembled (features + labels) training dataset.

    Aligned with data_contract.md Layer 4 (Label Dataset) and Layer 5
    (Research Run Manifest) requirements.
    """

    row_id: str
    symbol: str
    feature_timestamp: str  # ISO 8601
    label_timestamp: str  # ISO 8601
    mode: str
    features: Dict[str, float]
    label_long_r_net: float
    label_short_r_net: float
    label_best_action_label: str
    label_validity: str
    label_no_trade_quality: str
    label_cost_impact_long: float
    label_cost_impact_short: float
    lineage: LineageProvenance
    quality_flags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class DatasetAssembler(Protocol):
    """Protocol for assembling labeled datasets from feature + label DataFrames."""

    def assemble(
        self,
        feature_df: "pd.DataFrame",
        label_df: "pd.DataFrame",
        feature_spec: Dict,
        label_spec: Dict,
    ) -> Tuple[List[LabeledDataset], JoinAuditTrail]:
        """Join feature and label DataFrames into labeled dataset rows.

        Args:
            feature_df: pandas DataFrame with columns [symbol, timestamp,
                feature_set_id, <feature columns>].
            label_df: pandas DataFrame with columns [symbol, timestamp,
                label_dataset_id, label_checksum, best_action_label,
                label_validity, long_R_net, short_R_net, ...].
            feature_spec: FeatureSetSpec as dict (must carry 'mode',
                'feature_set_id').
            label_spec: LabelDatasetSpec as dict (must carry 'mode',
                'label_dataset_id', 'simulation_profile_id').

        Returns:
            (list_of_labeled_datasets, audit_trail).  Empty list is valid.
        """
        ...


@runtime_checkable
class DatasetWriter(Protocol):
    """Protocol for deterministic serialization and roundtrip verification."""

    def write(self, dataset: List[LabeledDataset], path: str) -> str:
        """Serialize dataset to disk. Returns SHA-256 hex digest.

        Deterministic: same input -> byte-identical output.
        """
        ...

    def read(self, path: str) -> List[LabeledDataset]:
        """Read a written dataset back into LabeledDataset instances."""
        ...

    def verify_roundtrip(
        self, path: str, original: List[LabeledDataset]
    ) -> bool:
        """Write-read-compare. Returns True iff roundtrip is lossless."""
        ...
