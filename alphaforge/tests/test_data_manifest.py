"""Test suite for DataManifest — deterministic, checksummed metadata records.

Covers:
  - Dataclass construction (frozen, fields)
  - build_manifest() with contracts/fixtures/simulation_output_minimal.json
  - Checksum stability (call twice, assert identical)
  - validate_manifest() negative cases
  - validate_manifest() positive cases
  - Import boundary test
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from alphaforge.data import (
    DataManifest,
    MANIFEST_VERSION,
    ManifestValidationError,
    build_manifest,
    validate_manifest,
)
from alphaforge.data.manifest import (
    FixtureRef,
    _canonical_json,
    _compute_checksum,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_DIR = REPO_ROOT / "contracts" / "fixtures"
MINIMAL_FIXTURE = FIXTURE_DIR / "simulation_output_minimal.json"


# ---------------------------------------------------------------------------
# Dataclass construction
# ---------------------------------------------------------------------------


class TestDataManifestConstruction:
    """Verify frozen dataclass behavior and field constraints."""

    def test_dataclass_is_frozen(self):
        """DataManifest instances are immutable."""
        m = DataManifest(
            manifest_id="test-id",
            created_at="2026-06-23T00:00:00Z",
            git_commit="abc123",
            source_fixtures=[],
            mode="SWING",
            primary_interval="4h",
            symbol="BTCUSDT",
            data_layer_refs={},
            config_hash="a" * 64,
        )
        with pytest.raises(Exception):
            m.mode = "SCALP"  # type: ignore[misc]

    def test_all_required_fields_present(self):
        """All fields in the design contract are present."""
        m = DataManifest(
            manifest_id="id",
            created_at="2026-01-01T00:00:00Z",
            git_commit="commit",
            source_fixtures=[FixtureRef(path="p.json", checksum="a" * 64)],
            mode="SCALP",
            primary_interval="1h",
            symbol="ETHUSDT",
            data_layer_refs={"layer1": "p.json"},
            config_hash="b" * 64,
            limitations=["limitation 1"],
        )
        assert m.manifest_id == "id"
        assert m.created_at == "2026-01-01T00:00:00Z"
        assert m.git_commit == "commit"
        assert len(m.source_fixtures) == 1
        assert m.mode == "SCALP"
        assert m.primary_interval == "1h"
        assert m.symbol == "ETHUSDT"
        assert m.data_layer_refs == {"layer1": "p.json"}
        assert m.config_hash == "b" * 64
        assert m.limitations == ["limitation 1"]

    def test_limitations_defaults_to_empty_list(self):
        """limitations field defaults to empty list."""
        m = DataManifest(
            manifest_id="id",
            created_at="2026-01-01T00:00:00Z",
            git_commit="x",
            source_fixtures=[FixtureRef(path="p.json", checksum="a" * 64)],
            mode="SWING",
            primary_interval="4h",
            symbol="BTCUSDT",
            data_layer_refs={},
            config_hash="c" * 64,
        )
        assert m.limitations == []

    def test_fixture_ref_is_frozen(self):
        """FixtureRef is also frozen."""
        ref = FixtureRef(path="x.json", checksum="a" * 64)
        with pytest.raises(Exception):
            ref.path = "y.json"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# build_manifest() with fixtures
# ---------------------------------------------------------------------------


class TestBuildManifest:
    """build_manifest() integration with real fixture files."""

    def test_build_manifest_from_minimal_fixture(self):
        """build_manifest() with simulation_output_minimal.json returns
        DataManifest with correct mode, symbol, primary_interval."""
        manifest = build_manifest([MINIMAL_FIXTURE])
        assert isinstance(manifest, DataManifest)
        assert manifest.mode == "SWING"
        assert manifest.symbol == "BTCUSDT"
        assert manifest.primary_interval == "4h"

    def test_build_manifest_has_all_metadata(self):
        """Result has manifest_id, created_at, git_commit, config_hash populated."""
        manifest = build_manifest([MINIMAL_FIXTURE])
        assert manifest.manifest_id
        assert len(manifest.manifest_id) == 16
        assert manifest.created_at
        assert manifest.git_commit
        assert manifest.config_hash
        assert len(manifest.config_hash) == 64

    def test_build_manifest_creates_fixture_refs(self):
        """source_fixtures list is populated with FixtureRef entries."""
        manifest = build_manifest([MINIMAL_FIXTURE])
        assert len(manifest.source_fixtures) >= 1
        ref = manifest.source_fixtures[0]
        assert isinstance(ref, FixtureRef)
        assert len(ref.checksum) == 64
        # Validate that checksum is valid hex
        int(ref.checksum, 16)

    def test_build_manifest_populates_data_layer_refs(self):
        """data_layer_refs maps layer names to fixture paths."""
        manifest = build_manifest([MINIMAL_FIXTURE])
        assert manifest.data_layer_refs
        assert "simulation_output_minimal" in manifest.data_layer_refs

    def test_build_manifest_has_limitations(self):
        """limitations list contains expected caveats."""
        manifest = build_manifest([MINIMAL_FIXTURE])
        assert isinstance(manifest.limitations, list)
        assert len(manifest.limitations) > 0
        assert any("fixture-only" in lim for lim in manifest.limitations)

    def test_build_manifest_handles_multiple_fixtures(self):
        """build_manifest() accepts multiple fixture paths."""
        # Build with the same fixture twice (both exist)
        manifest = build_manifest([MINIMAL_FIXTURE, MINIMAL_FIXTURE])
        assert len(manifest.source_fixtures) == 2

    def test_build_manifest_raises_on_empty_list(self):
        """Empty fixture_paths raises ManifestValidationError."""
        with pytest.raises(ManifestValidationError) as exc_info:
            build_manifest([])
        assert "source_fixtures" in str(exc_info.value)

    def test_build_manifest_raises_on_missing_file(self):
        """Nonexistent fixture path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            build_manifest([Path("/nonexistent/fixture_abc_xyz.json")])


# ---------------------------------------------------------------------------
# Checksum stability
# ---------------------------------------------------------------------------


class TestChecksumStability:
    """The most critical contract: deterministic output."""

    def test_canonical_json_deterministic(self):
        """Same dict produces identical bytes."""
        data = {"b": 2, "a": 1, "c": [3, 4]}
        result1 = _canonical_json(data)
        result2 = _canonical_json(data)
        assert result1 == result2

    def test_canonical_json_sorts_keys(self):
        """Key order does not affect output."""
        data1 = {"a": 1, "b": 2}
        data2 = {"b": 2, "a": 1}
        assert _canonical_json(data1) == _canonical_json(data2)

    def test_canonical_json_has_trailing_newline(self):
        """Output ends with newline."""
        result = _canonical_json({"x": 1})
        assert result.endswith(b"\n")

    def test_build_manifest_checksum_stability(self):
        """Calling build_manifest() twice with same inputs produces identical
        manifest_id, config_hash, and per-fixture checksums."""
        m1 = build_manifest([MINIMAL_FIXTURE])
        m2 = build_manifest([MINIMAL_FIXTURE])

        assert m1.manifest_id == m2.manifest_id, "manifest_id drifted"
        assert m1.config_hash == m2.config_hash, "config_hash drifted"
        assert len(m1.source_fixtures) == len(m2.source_fixtures)
        for r1, r2 in zip(m1.source_fixtures, m2.source_fixtures):
            assert r1.checksum == r2.checksum, "fixture checksum drifted"


# ---------------------------------------------------------------------------
# validate_manifest() negative cases
# ---------------------------------------------------------------------------


class TestValidateManifestNegative:
    """validate_manifest() must raise ManifestValidationError for invalid inputs."""

    def test_empty_manifest_id(self):
        """Empty manifest_id raises error."""
        m = DataManifest(
            manifest_id="",
            created_at="2026-06-23T00:00:00Z",
            git_commit="abc",
            source_fixtures=[FixtureRef(path="p.json", checksum="a" * 64)],
            mode="SWING",
            primary_interval="4h",
            symbol="BTCUSDT",
            data_layer_refs={},
            config_hash="a" * 64,
        )
        with pytest.raises(ManifestValidationError) as exc_info:
            validate_manifest(m)
        assert "manifest_id" in str(exc_info.value)

    def test_invalid_mode_day_trade(self):
        """Mode 'DAY_TRADE' is not in (SCALP, AGGRESSIVE_SCALP, SWING)."""
        m = DataManifest(
            manifest_id="id123",
            created_at="2026-06-23T00:00:00Z",
            git_commit="abc",
            source_fixtures=[FixtureRef(path="p.json", checksum="a" * 64)],
            mode="DAY_TRADE",
            primary_interval="1h",
            symbol="BTCUSDT",
            data_layer_refs={},
            config_hash="a" * 64,
        )
        with pytest.raises(ManifestValidationError) as exc_info:
            validate_manifest(m)
        assert "mode" in str(exc_info.value).lower() or "DAY_TRADE" in str(exc_info.value)

    def test_invalid_interval_5m(self):
        """Interval '5m' is not in (15m, 1h, 4h, 1d)."""
        m = DataManifest(
            manifest_id="id123",
            created_at="2026-06-23T00:00:00Z",
            git_commit="abc",
            source_fixtures=[FixtureRef(path="p.json", checksum="a" * 64)],
            mode="SWING",
            primary_interval="5m",
            symbol="BTCUSDT",
            data_layer_refs={},
            config_hash="a" * 64,
        )
        with pytest.raises(ManifestValidationError) as exc_info:
            validate_manifest(m)
        assert "primary_interval" in str(exc_info.value).lower() or "5m" in str(exc_info.value)

    def test_empty_symbol(self):
        """Empty symbol raises error."""
        m = DataManifest(
            manifest_id="id123",
            created_at="2026-06-23T00:00:00Z",
            git_commit="abc",
            source_fixtures=[FixtureRef(path="p.json", checksum="a" * 64)],
            mode="SWING",
            primary_interval="4h",
            symbol="",
            data_layer_refs={},
            config_hash="a" * 64,
        )
        with pytest.raises(ManifestValidationError) as exc_info:
            validate_manifest(m)
        assert "symbol" in str(exc_info.value)

    def test_empty_source_fixtures(self):
        """Empty source_fixtures list raises error."""
        m = DataManifest(
            manifest_id="id123",
            created_at="2026-06-23T00:00:00Z",
            git_commit="abc",
            source_fixtures=[],
            mode="SWING",
            primary_interval="4h",
            symbol="BTCUSDT",
            data_layer_refs={},
            config_hash="a" * 64,
        )
        with pytest.raises(ManifestValidationError) as exc_info:
            validate_manifest(m)
        assert "source_fixtures" in str(exc_info.value)

    def test_invalid_config_hash_length(self):
        """config_hash must be 64 hex characters."""
        m = DataManifest(
            manifest_id="id123",
            created_at="2026-06-23T00:00:00Z",
            git_commit="abc",
            source_fixtures=[FixtureRef(path="p.json", checksum="a" * 64)],
            mode="SWING",
            primary_interval="4h",
            symbol="BTCUSDT",
            data_layer_refs={},
            config_hash="too_short",
        )
        with pytest.raises(ManifestValidationError) as exc_info:
            validate_manifest(m)
        assert "config_hash" in str(exc_info.value)

    def test_invalid_config_hash_non_hex(self):
        """config_hash must be valid hex."""
        m = DataManifest(
            manifest_id="id123",
            created_at="2026-06-23T00:00:00Z",
            git_commit="abc",
            source_fixtures=[FixtureRef(path="p.json", checksum="a" * 64)],
            mode="SWING",
            primary_interval="4h",
            symbol="BTCUSDT",
            data_layer_refs={},
            config_hash="g" * 64,  # 'g' is not valid hex
        )
        with pytest.raises(ManifestValidationError) as exc_info:
            validate_manifest(m)
        assert "config_hash" in str(exc_info.value)

    def test_missing_created_at(self):
        """Empty created_at raises error."""
        m = DataManifest(
            manifest_id="id123",
            created_at="",
            git_commit="abc",
            source_fixtures=[FixtureRef(path="p.json", checksum="a" * 64)],
            mode="SWING",
            primary_interval="4h",
            symbol="BTCUSDT",
            data_layer_refs={},
            config_hash="a" * 64,
        )
        with pytest.raises(ManifestValidationError) as exc_info:
            validate_manifest(m)
        assert "created_at" in str(exc_info.value)

    def test_non_iso8601_created_at(self):
        """Non-ISO-8601 created_at raises error."""
        m = DataManifest(
            manifest_id="id123",
            created_at="not-a-date",
            git_commit="abc",
            source_fixtures=[FixtureRef(path="p.json", checksum="a" * 64)],
            mode="SWING",
            primary_interval="4h",
            symbol="BTCUSDT",
            data_layer_refs={},
            config_hash="a" * 64,
        )
        with pytest.raises(ManifestValidationError) as exc_info:
            validate_manifest(m)
        assert "created_at" in str(exc_info.value)

    def test_invalid_fixture_checksum_length(self):
        """FixtureRef checksum must be exactly 64 hex chars."""
        m = DataManifest(
            manifest_id="id123",
            created_at="2026-06-23T00:00:00Z",
            git_commit="abc",
            source_fixtures=[FixtureRef(path="p.json", checksum="short")],
            mode="SWING",
            primary_interval="4h",
            symbol="BTCUSDT",
            data_layer_refs={},
            config_hash="a" * 64,
        )
        with pytest.raises(ManifestValidationError) as exc_info:
            validate_manifest(m)
        assert "checksum" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# validate_manifest() positive cases
# ---------------------------------------------------------------------------


class TestValidateManifestPositive:
    """validate_manifest() returns None for valid manifests."""

    def test_valid_swing_manifest(self):
        """Valid SWING manifest passes validation."""
        manifest = build_manifest([MINIMAL_FIXTURE])
        # build_manifest already calls validate_manifest internally
        result = validate_manifest(manifest)
        assert result is None

    def test_valid_scalp_manifest(self):
        """Valid SCALP manifest with 1h interval passes validation."""
        m = DataManifest(
            manifest_id="scalp-test-id-01",
            created_at="2026-06-23T00:00:00Z",
            git_commit="test",
            source_fixtures=[FixtureRef(path="fixture.json", checksum="a" * 64)],
            mode="SCALP",
            primary_interval="1h",
            symbol="ETHUSDT",
            data_layer_refs={"layer1": "fixture.json"},
            config_hash="b" * 64,
        )
        result = validate_manifest(m)
        assert result is None

    def test_valid_aggressive_scalp_manifest(self):
        """Valid AGGRESSIVE_SCALP manifest with 15m interval passes validation."""
        m = DataManifest(
            manifest_id="aggressive-test-01",
            created_at="2026-06-23T00:00:00Z",
            git_commit="test",
            source_fixtures=[FixtureRef(path="fixture.json", checksum="a" * 64)],
            mode="AGGRESSIVE_SCALP",
            primary_interval="15m",
            symbol="SOLUSDT",
            data_layer_refs={"layer1": "fixture.json"},
            config_hash="c" * 64,
        )
        result = validate_manifest(m)
        assert result is None

    def test_valid_manifest_with_limitations(self):
        """Manifest with populated limitations still passes validation."""
        m = DataManifest(
            manifest_id="lmt-test-01",
            created_at="2026-01-01T00:00:00Z",
            git_commit="test",
            source_fixtures=[FixtureRef(path="f.json", checksum="a" * 64)],
            mode="SWING",
            primary_interval="1d",
            symbol="BTCUSDT",
            data_layer_refs={"l": "f.json"},
            config_hash="d" * 64,
            limitations=["limitation A", "limitation B"],
        )
        result = validate_manifest(m)
        assert result is None


# ---------------------------------------------------------------------------
# Import boundary
# ---------------------------------------------------------------------------


class TestImportBoundary:
    """alphaforge.data must not import from forbidden domains."""

    FORBIDDEN_PREFIXES = ("simulation.", "v7.", "runtime.", "interface.")

    def test_alphaforge_data_no_forbidden_imports(self):
        """Verify alphaforge.data has no imports from simulation, v7, runtime, or interface."""
        forbidden_found: list[str] = []
        alphaforge_data_mod = sys.modules.get("alphaforge.data")
        if alphaforge_data_mod is None:
            import alphaforge.data as _mod
            alphaforge_data_mod = _mod

        # Collect all modules loaded under alphaforge.data and its submodules
        relevant_prefixes = ("alphaforge.data", )
        for mod_name in sorted(sys.modules.keys()):
            if not mod_name.startswith(relevant_prefixes):
                continue
            if mod_name.startswith("alphaforge.data"):
                mod = sys.modules[mod_name]
                if mod is None:
                    continue
                # Check if any forbidden prefix appears in the module's __file__
                # or in the source of its sub-imports
                if hasattr(mod, "__file__") and mod.__file__:
                    file_path = mod.__file__
                    for prefix in self.FORBIDDEN_PREFIXES:
                        # Check if the module file lives under a forbidden directory
                        if f"/{prefix.replace('.', '/')}" in file_path or f"/{prefix}" in file_path:
                            forbidden_found.append(f"{mod_name} -> file path: {file_path}")

        # Also scan the source itself for import statements
        import inspect
        try:
            source = inspect.getsource(alphaforge_data_mod)
        except (TypeError, OSError):
            source = ""
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("from ") or stripped.startswith("import "):
                for prefix in self.FORBIDDEN_PREFIXES:
                    if prefix in stripped:
                        forbidden_found.append(f"import line: {stripped}")

        assert not forbidden_found, (
            f"Forbidden imports detected:\n" + "\n".join(forbidden_found)
        )

    def test_alphaforge_data_manifest_no_forbidden_imports(self):
        """Verify manifest.py has no forbidden imports."""
        # Read manifest.py source directly and scan import lines
        manifest_path = (
            REPO_ROOT / "alphaforge" / "src" / "alphaforge" / "data" / "manifest.py"
        )
        source = manifest_path.read_text(encoding="utf-8")
        forbidden_found: list[str] = []
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("from ") or stripped.startswith("import "):
                for prefix in self.FORBIDDEN_PREFIXES:
                    if prefix in stripped:
                        forbidden_found.append(stripped)
        assert not forbidden_found, (
            f"Forbidden imports in manifest.py:\n" + "\n".join(forbidden_found)
        )

    def test_manifest_uses_only_stdlib_and_alphaforge_internal(self):
        """manifest.py only imports from stdlib and alphaforge internal modules."""
        manifest_path = (
            REPO_ROOT / "alphaforge" / "src" / "alphaforge" / "data" / "manifest.py"
        )
        source = manifest_path.read_text(encoding="utf-8")
        allowed_external = {
            "alphaforge.errors",
        }
        stdlib_top = {
            "hashlib", "json", "dataclasses", "datetime",
            "pathlib", "typing", "__future__",
        }
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("from ") and "import" in stripped:
                parts = stripped.split("import")
                module = parts[0].replace("from ", "").strip()
                top = module.split(".")[0]
                if top not in stdlib_top and module not in allowed_external:
                    assert top in stdlib_top or module in allowed_external, (
                        f"Unexpected import from module: {module}"
                    )
            elif stripped.startswith("import "):
                parts = stripped.replace("import ", "").strip().split(",")
                for p in parts:
                    p = p.strip().split(" as ")[0].strip()
                    top = p.split(".")[0]
                    assert top in stdlib_top, (
                        f"Unexpected import: {p}"
                    )
