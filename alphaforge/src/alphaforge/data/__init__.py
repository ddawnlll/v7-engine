"""AlphaForge data layer — DataManifest and deterministic data provenance.

DataManifest is the reproducibility anchor for every AlphaForge research
run. It is a frozen, checksummed metadata record that describes which
simulation output fixtures comprise a research run. It must be produced
before any label, feature, or dataset work.

The BackfillPipeline orchestrates market data backfill from Binance through
the shared lib-level BackfillOrchestrator and produces a deterministic
DataManifest.

Mode-specific manifest modules (scalp_manifest, aggressive_manifest) provide
convenience builders for the canonical SCALP (1h) and AGGRESSIVE_SCALP (15m)
20-symbol universes.  All manifests are fixture-based and deterministic.

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
from alphaforge.data.scalp_manifest import (
    SCALP_MODE,
    SCALP_PRIMARY_INTERVAL,
    SCALP_SYMBOLS,
    build_all_scalp_manifests,
    build_scalp_manifest,
)
from alphaforge.data.aggressive_manifest import (
    AGGRESSIVE_SCALP_MODE,
    AGGRESSIVE_SCALP_PRIMARY_INTERVAL,
    AGGRESSIVE_SCALP_SYMBOLS,
    build_aggressive_manifest,
    build_all_aggressive_manifests,
)

__all__ = [
    # Core manifest
    "DataManifest",
    "ManifestValidationError",
    "MANIFEST_VERSION",
    "build_manifest",
    "validate_manifest",
    # Backfill
    "BackfillConfig",
    "BackfillError",
    "BackfillPipeline",
    "BackfillResult",
    "create_backfill_config",
    "create_pipeline",
    # SCALP mode manifest
    "SCALP_MODE",
    "SCALP_PRIMARY_INTERVAL",
    "SCALP_SYMBOLS",
    "build_scalp_manifest",
    "build_all_scalp_manifests",
    # AGGRESSIVE_SCALP mode manifest
    "AGGRESSIVE_SCALP_MODE",
    "AGGRESSIVE_SCALP_PRIMARY_INTERVAL",
    "AGGRESSIVE_SCALP_SYMBOLS",
    "build_aggressive_manifest",
    "build_all_aggressive_manifests",
]
