"""AGGRESSIVE_SCALP mode data manifest — 15m primary, 20-symbol universe.

Deterministic, fixture-based DataManifest builder for AGGRESSIVE_SCALP
mode alpha discovery runs. Every call with the same symbol produces an
identical manifest — no network, no timestamp drift, no randomness.

AGGRESSIVE_SCALP operates at 15m primary bars (context 1h, refinement 5m)
with tighter cost sensitivity and higher overfit risk than SCALP or SWING.

Uses the shared simulation_output_minimal.json fixture for checksum
stability while overriding mode=AGGRESSIVE_SCALP, primary_interval=15m,
and the per-symbol target. The config_hash correctly reflects mode-specific
fields.

Design constraint: This module imports only from ``alphaforge.data.manifest``
and stdlib. No imports from simulation/, v7/, runtime/, or interface/.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List

from alphaforge.data.manifest import (
    DataManifest,
    FixtureRef,
    FIXED_CREATED_AT,
    GIT_COMMIT_PLACEHOLDER,
    MANIFEST_VERSION,
    _compute_checksum,
    validate_manifest,
)

# ---------------------------------------------------------------------------
# Canonical symbol universe (top-20 by liquidity, USDT-margined)
# ---------------------------------------------------------------------------

AGGRESSIVE_SCALP_SYMBOLS: List[str] = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT", "ETCUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "NEARUSDT", "INJUSDT",
]

AGGRESSIVE_SCALP_MODE: str = "AGGRESSIVE_SCALP"
AGGRESSIVE_SCALP_PRIMARY_INTERVAL: str = "15m"

AGGRESSIVE_SCALP_LIMITATIONS: List[str] = [
    "No real market data — fixture-only build",
    "git_commit is NOT_AVAILABLE placeholder",
    "created_at uses fixed constant for deterministic checksums",
    "AGGRESSIVE_SCALP mode — 15m primary interval; context 1h; refinement 5m",
    "Funding model is DEFERRED for AGGRESSIVE_SCALP mode",
    "Higher fee/slippage sensitivity than SCALP — cost model under HOLD",
    "Latency analysis not performed — live viability unconfirmed",
    "No liquidity/spread data — single-fixture build",
]


# ---------------------------------------------------------------------------
# Default fixture resolution
# ---------------------------------------------------------------------------


def _default_fixture_path() -> Path:
    """Resolve the default simulation fixture for AGGRESSIVE_SCALP manifest builds.

    Returns the canonical ``simulation_output_minimal.json`` from the
    shared contracts/fixtures/ directory.  The fixture itself is SWING/4h
    but serves as a deterministic content source; the manifest module
    overrides mode, interval, and symbol.
    """
    this_file = Path(__file__).resolve()
    repo_root = this_file.parent.parent.parent.parent.parent
    fixture = repo_root / "contracts" / "fixtures" / "simulation_output_minimal.json"
    if not fixture.exists():
        raise FileNotFoundError(
            f"Default AGGRESSIVE_SCALP fixture not found: {fixture}\n"
            f"Ensure contracts/fixtures/simulation_output_minimal.json exists."
        )
    return fixture


# ---------------------------------------------------------------------------
# Single-symbol builder
# ---------------------------------------------------------------------------


def build_aggressive_manifest(
    symbol: str,
    fixture_path: Path | None = None,
) -> DataManifest:
    """Build a deterministic AGGRESSIVE_SCALP-mode DataManifest for one symbol.

    Args:
        symbol: Trading symbol, e.g. ``"BTCUSDT"``.  Must be non-empty.
        fixture_path: Optional override for the base fixture file used
            for checksum computation.  If *None*, the default
            ``simulation_output_minimal.json`` is used.

    Returns:
        A frozen :class:`DataManifest` with ``mode=AGGRESSIVE_SCALP`` and
        ``primary_interval=15m``.  The return value has already been
        validated via :func:`validate_manifest`.

    Raises:
        FileNotFoundError: If *fixture_path* does not exist.
        json.JSONDecodeError: If the fixture is not valid JSON.
        ManifestValidationError: If the constructed manifest fails
            validation.
    """
    fp = fixture_path or _default_fixture_path()
    resolved = fp.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Fixture not found: {resolved}")

    raw = json.loads(resolved.read_text(encoding="utf-8"))
    checksum = _compute_checksum(raw)
    fixture_ref = FixtureRef(path=str(resolved), checksum=checksum)

    manifest_id: str = hashlib.sha256(checksum.encode("utf-8")).hexdigest()[:16]

    layer_name = resolved.stem
    data_layer_refs = {layer_name: str(resolved)}

    config_data: dict[str, object] = {
        "mode": AGGRESSIVE_SCALP_MODE,
        "primary_interval": AGGRESSIVE_SCALP_PRIMARY_INTERVAL,
        "symbol": symbol,
        "data_layer_refs": dict(sorted(data_layer_refs.items())),
        "manifest_version": MANIFEST_VERSION,
    }
    config_hash: str = _compute_checksum(config_data)

    manifest = DataManifest(
        manifest_id=manifest_id,
        created_at=FIXED_CREATED_AT,
        git_commit=GIT_COMMIT_PLACEHOLDER,
        source_fixtures=[fixture_ref],
        mode=AGGRESSIVE_SCALP_MODE,
        primary_interval=AGGRESSIVE_SCALP_PRIMARY_INTERVAL,
        symbol=symbol,
        data_layer_refs=data_layer_refs,
        config_hash=config_hash,
        limitations=list(AGGRESSIVE_SCALP_LIMITATIONS),
    )

    validate_manifest(manifest)
    return manifest


# ---------------------------------------------------------------------------
# Bulk builder
# ---------------------------------------------------------------------------


def build_all_aggressive_manifests(
    symbols: List[str] | None = None,
) -> List[DataManifest]:
    """Build DataManifest objects for the full AGGRESSIVE_SCALP symbol universe.

    Args:
        symbols: Optional override of the symbol list.  If *None*, the
            canonical :data:`AGGRESSIVE_SCALP_SYMBOLS` (20 symbols) is used.

    Returns:
        A list of :class:`DataManifest` objects, one per symbol.
        The list length is ``len(symbols)``.
    """
    syms = symbols if symbols is not None else AGGRESSIVE_SCALP_SYMBOLS
    return [build_aggressive_manifest(s) for s in syms]
