"""AlphaForge Dataset Assembler — join manifest + labels + features.

Subpackage exports:
  contracts  — LabeledDataset, LineageProvenance, JoinAuditTrail, protocols
  assembler  — DatasetAssembler (join logic)
  lineage    — LineageTracker (provenance)
  writer     — DatasetWriter (deterministic serialization)
"""

from alphaforge.dataset.contracts import (
    DatasetAssembler,
    DatasetWriter,
    JoinAuditTrail,
    LabeledDataset,
    LineageProvenance,
)
from alphaforge.dataset.assembler import DefaultAssembler
from alphaforge.dataset.lineage import LineageError, LineageTracker
from alphaforge.dataset.writer import DefaultWriter

__all__ = [
    "LabeledDataset",
    "LineageProvenance",
    "JoinAuditTrail",
    "DatasetAssembler",
    "DatasetWriter",
    "DefaultAssembler",
    "LineageTracker",
    "LineageError",
    "DefaultWriter",
]
