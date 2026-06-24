"""DataManifest — deterministic, checksummed metadata record for AlphaForge runs.

DataManifest is the data-layer root object for reproducibility. Every
AlphaForge research run must produce a DataManifest before any label,
feature, or dataset work proceeds.

All inputs are local JSON fixtures under contracts/fixtures/. No real
market data, no network calls, no Binance API.

Design verified against data_contract.md Layers 1-2.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from alphaforge.errors import AlphaForgeError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST_VERSION: str = "1.0.0"

# FIXED constant for deterministic checksum stability. NEVER use datetime.now().
FIXED_CREATED_AT: str = "2026-06-23T00:00:00Z"

# Placeholder until real git integration is wired.
GIT_COMMIT_PLACEHOLDER: str = "NOT_AVAILABLE"

VALID_MODES: frozenset[str] = frozenset({"SCALP", "AGGRESSIVE_SCALP", "SWING"})
VALID_INTERVALS: frozenset[str] = frozenset({"15m", "1h", "4h", "1d"})

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ManifestValidationError(AlphaForgeError):
    """A DataManifest field failed validation.

    The ``field`` attribute names the invalid field and ``detail`` carries a
    human-readable description suitable for ACCP-YAML reports.
    """

    def __init__(self, field: str, detail: str) -> None:
        self.field = field
        self.detail = detail
        super().__init__(f"DataManifest.{field}: {detail}")


# ---------------------------------------------------------------------------
# DataManifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataManifest:
    """Deterministic, checksummed metadata record for an AlphaForge research run.

    All fields are frozen. Two manifests built from identical fixtures MUST
    produce the same manifest_id, config_hash, and every per-fixture checksum.
    """

    manifest_id: str
    created_at: str  # ISO 8601
    git_commit: str
    source_fixtures: List["FixtureRef"]
    mode: str  # SCALP | AGGRESSIVE_SCALP | SWING
    primary_interval: str  # 15m | 1h | 4h | 1d
    symbol: str
    data_layer_refs: Dict[str, str]  # layer name -> fixture path
    config_hash: str  # 64-char hex SHA256
    limitations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class FixtureRef:
    """Reference to a single simulation output fixture."""

    path: str
    checksum: str  # 64-char hex SHA256


# ---------------------------------------------------------------------------
# Canonical JSON and checksum
# ---------------------------------------------------------------------------


def _canonical_json(data: dict[str, Any]) -> bytes:
    """Produce deterministic JSON bytes for checksum stability.

    Uses sorted keys, indent=2, ensure_ascii=False, UTF-8 encoding, and a
    trailing newline. No random elements, no timestamps, no process IDs.

    This is the foundation of DataManifest checksum stability — any
    re-implementation with the same rules must produce identical bytes.
    """
    serialized: str = json.dumps(
        data,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
    )
    return (serialized + "\n").encode("utf-8")


def _compute_checksum(data: dict[str, Any]) -> str:
    """SHA256 hex digest of _canonical_json(data)."""
    return hashlib.sha256(_canonical_json(data)).hexdigest()


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_manifest(fixture_paths: list[Path]) -> DataManifest:
    """Build a DataManifest from a list of simulation output fixture paths.

    Args:
        fixture_paths: Absolute or relative Path objects pointing to
            JSON fixture files (e.g. simulation_output_minimal.json).

    Returns:
        A frozen DataManifest with deterministic manifest_id, per-fixture
        checksums, and config_hash.

    Raises:
        FileNotFoundError: If any fixture path does not exist.
        json.JSONDecodeError: If any fixture is not valid JSON.
        ManifestValidationError: If a fixture is missing required fields.
    """
    if not fixture_paths:
        raise ManifestValidationError(
            "source_fixtures", "At least one fixture path is required"
        )

    source_fixtures: list[FixtureRef] = []
    fixture_checksums: list[str] = []
    mode: str = ""
    symbol: str = ""
    primary_interval: str = ""
    data_layer_refs: dict[str, str] = {}

    for fp in fixture_paths:
        resolved = fp.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Fixture not found: {resolved}")

        raw: dict[str, Any] = json.loads(resolved.read_text(encoding="utf-8"))
        checksum = _compute_checksum(raw)
        source_fixtures.append(FixtureRef(path=str(resolved), checksum=checksum))
        fixture_checksums.append(checksum)

        # Extract metadata from fixture
        if not mode:
            mode = raw.get("mode", "")
        if not symbol:
            symbol = raw.get("symbol", "")
        if not primary_interval:
            primary_interval = raw.get("primary_interval", "")

        # Index by layer name derived from filename stem
        layer_name = resolved.stem  # e.g. "simulation_output_minimal"
        data_layer_refs[layer_name] = str(resolved)

    # Deterministic manifest_id: SHA256 of concatenated fixture checksums,
    # truncated to 16 hex characters.
    concatenated: str = "".join(fixture_checksums)
    manifest_id: str = hashlib.sha256(concatenated.encode("utf-8")).hexdigest()[:16]

    # config_hash: SHA256 of canonical form of config-relevant fields.
    config_data: dict[str, Any] = {
        "mode": mode,
        "primary_interval": primary_interval,
        "symbol": symbol,
        "data_layer_refs": dict(sorted(data_layer_refs.items())),
        "manifest_version": MANIFEST_VERSION,
    }
    config_hash: str = _compute_checksum(config_data)

    manifest = DataManifest(
        manifest_id=manifest_id,
        created_at=FIXED_CREATED_AT,
        git_commit=GIT_COMMIT_PLACEHOLDER,
        source_fixtures=source_fixtures,
        mode=mode,
        primary_interval=primary_interval,
        symbol=symbol,
        data_layer_refs=data_layer_refs,
        config_hash=config_hash,
        limitations=[
            "No real market data — fixture-only build",
            "git_commit is NOT_AVAILABLE placeholder",
            "created_at uses fixed constant for deterministic checksums",
            "Funding model is DEFERRED for all modes",
        ],
    )

    # Validate before returning
    validate_manifest(manifest)

    return manifest


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _validate_iso8601(value: str, field_name: str) -> None:
    """Raise ManifestValidationError if value is not valid ISO 8601."""
    try:
        dt_str = value.replace("Z", "+00:00")
        datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        raise ManifestValidationError(
            field_name, f"'{value}' is not a valid ISO 8601 datetime"
        )


def validate_manifest(manifest: DataManifest) -> None:
    """Validate all DataManifest fields.

    Returns None on success (valid manifest).
    Raises ManifestValidationError with field-specific message on failure.
    """
    # manifest_id: non-empty string
    if not manifest.manifest_id or not isinstance(manifest.manifest_id, str):
        raise ManifestValidationError(
            "manifest_id",
            f"Must be a non-empty string, got {manifest.manifest_id!r}",
        )

    # created_at: valid ISO 8601
    if not manifest.created_at or not isinstance(manifest.created_at, str):
        raise ManifestValidationError(
            "created_at",
            f"Must be a non-empty ISO 8601 string, got {manifest.created_at!r}",
        )
    _validate_iso8601(manifest.created_at, "created_at")

    # mode: must be one of SCALP, AGGRESSIVE_SCALP, SWING
    if manifest.mode not in VALID_MODES:
        raise ManifestValidationError(
            "mode",
            f"Must be one of {sorted(VALID_MODES)}, got {manifest.mode!r}",
        )

    # primary_interval: must be 15m, 1h, 4h, 1d
    if manifest.primary_interval not in VALID_INTERVALS:
        raise ManifestValidationError(
            "primary_interval",
            f"Must be one of {sorted(VALID_INTERVALS)}, got {manifest.primary_interval!r}",
        )

    # symbol: non-empty string
    if not manifest.symbol or not isinstance(manifest.symbol, str):
        raise ManifestValidationError(
            "symbol",
            f"Must be a non-empty string, got {manifest.symbol!r}",
        )

    # source_fixtures: non-empty list
    if not manifest.source_fixtures or not isinstance(manifest.source_fixtures, list):
        raise ManifestValidationError(
            "source_fixtures",
            f"Must be a non-empty list, got {manifest.source_fixtures!r}",
        )

    # Each fixture ref must have valid path and checksum
    for i, ref in enumerate(manifest.source_fixtures):
        if not ref.path or not isinstance(ref.path, str):
            raise ManifestValidationError(
                f"source_fixtures[{i}].path",
                f"Must be a non-empty string, got {ref.path!r}",
            )
        if not ref.checksum or not isinstance(ref.checksum, str) or len(ref.checksum) != 64:
            raise ManifestValidationError(
                f"source_fixtures[{i}].checksum",
                f"Must be a 64-character hex string, got {ref.checksum!r}",
            )
        try:
            int(ref.checksum, 16)
        except ValueError:
            raise ManifestValidationError(
                f"source_fixtures[{i}].checksum",
                f"Must be valid hex, got {ref.checksum!r}",
            )

    # config_hash: 64-char hex string
    if (
        not manifest.config_hash
        or not isinstance(manifest.config_hash, str)
        or len(manifest.config_hash) != 64
    ):
        raise ManifestValidationError(
            "config_hash",
            f"Must be a 64-character hex string, got {manifest.config_hash!r}",
        )
    try:
        int(manifest.config_hash, 16)
    except ValueError:
        raise ManifestValidationError(
            "config_hash",
            f"Must be valid hex, got {manifest.config_hash!r}",
        )
