"""AlphaForge data layer — DataManifest and deterministic data provenance.

DataManifest is the reproducibility anchor for every AlphaForge research
run. It is a frozen, checksummed metadata record that describes which
simulation output fixtures comprise a research run. It must be produced
before any label, feature, or dataset work.

The BackfillPipeline orchestrates market data backfill from Binance through
the shared lib-level BackfillOrchestrator and produces a deterministic
DataManifest.

Authority boundary: alphaforge.data owns data provenance. It does NOT
import from simulation/, v7/, runtime/, or interface/. It may import
from alphaforge.contracts.loader and alphaforge.paths only.
"""

from alphaforge.data.manifest import (
    DataManifest,
    ManifestValidationError,
    MANIFEST_VERSION,
    build_manifest,
    validate_manifest,
)
from alphaforge.data.backfill import (
    BackfillConfig,
    BackfillError,
    BackfillPipeline,
    BackfillResult,
    create_backfill_config,
    create_pipeline,
)

__all__ = [
    "DataManifest",
    "ManifestValidationError",
    "MANIFEST_VERSION",
    "build_manifest",
    "validate_manifest",
    "BackfillConfig",
    "BackfillError",
    "BackfillPipeline",
    "BackfillResult",
    "create_backfill_config",
    "create_pipeline",
]
