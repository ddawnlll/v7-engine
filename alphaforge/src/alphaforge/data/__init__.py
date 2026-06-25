"""AlphaForge data layer — DataManifest and deterministic data provenance.

DataManifest is the reproducibility anchor for every AlphaForge research
run. It is a frozen, checksummed metadata record that describes which
simulation output fixtures comprise a research run. It must be produced
before any label, feature, or dataset work.

Authority boundary: alphaforge.data owns data provenance. It does NOT
import from simulation/, v7/, runtime/, or interface/. It may import
from alphaforge.contracts.loader and alphaforge.paths only.
"""

from alphaforge.data.backfill import (
    AlphaForgeBackfillPipeline,
    BackfillConfig,
    BackfillError,
    BackfillResult,
)
from alphaforge.data.integrity import IntegrityReport, validate_kline_parquet
from alphaforge.data.manifest import (
    DataManifest,
    ManifestValidationError,
    MANIFEST_VERSION,
    build_manifest,
    validate_manifest,
)

__all__ = [
    "AlphaForgeBackfillPipeline",
    "BackfillConfig",
    "BackfillError",
    "BackfillResult",
    "DataManifest",
    "IntegrityReport",
    "MANIFEST_VERSION",
    "ManifestValidationError",
    "build_manifest",
    "validate_kline_parquet",
    "validate_manifest",
]
