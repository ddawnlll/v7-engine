"""Test suite for SCALP mode data manifest.

Covers:
  - build_scalp_manifest() returns valid DataManifest
  - Mode, interval, symbol correctness
  - Determinism (same inputs -> same output)
  - Different symbols produce different config hashes
  - Frozen dataclass behavior
  - validate_manifest() pass-through
  - SCALP_SYMBOLS list integrity
  - build_all_scalp_manifests() produces correct count
  - Limitations populated
  - FixtureFileNotFound and import boundaries
"""

from __future__ import annotations

from pathlib import Path

import pytest

from alphaforge.data import (
    DataManifest,
    ManifestValidationError,
    build_all_scalp_manifests,
    build_scalp_manifest,
    validate_manifest,
)
from alphaforge.data.scalp_manifest import (
    SCALP_LIMITATIONS,
    SCALP_MODE,
    SCALP_PRIMARY_INTERVAL,
    SCALP_SYMBOLS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MINIMAL_FIXTURE = REPO_ROOT / "contracts" / "fixtures" / "simulation_output_minimal.json"


# ---------------------------------------------------------------------------
# Single-symbol builder tests
# ---------------------------------------------------------------------------


class TestBuildScalpManifest:
    """build_scalp_manifest() with default fixture."""

    def test_returns_datamanifest(self):
        """Returns a DataManifest instance."""
        m = build_scalp_manifest("BTCUSDT")
        assert isinstance(m, DataManifest)

    def test_mode_is_scalp(self):
        """Mode is SCALP."""
        m = build_scalp_manifest("BTCUSDT")
        assert m.mode == "SCALP"

    def test_primary_interval_is_1h(self):
        """Primary interval is 1h."""
        m = build_scalp_manifest("BTCUSDT")
        assert m.primary_interval == "1h"

    def test_symbol_is_correct(self):
        """Symbol matches the argument."""
        m = build_scalp_manifest("ETHUSDT")
        assert m.symbol == "ETHUSDT"

    def test_symbol_is_correct_solusdt(self):
        """Different symbol produces correct symbol field."""
        m = build_scalp_manifest("SOLUSDT")
        assert m.symbol == "SOLUSDT"

    def test_is_frozen(self):
        """DataManifest instances are frozen (immutable)."""
        m = build_scalp_manifest("BTCUSDT")
        with pytest.raises(Exception):
            m.mode = "SWING"  # type: ignore[misc]

    def test_deterministic_same_symbol(self):
        """Two calls with the same symbol produce identical manifests."""
        m1 = build_scalp_manifest("BTCUSDT")
        m2 = build_scalp_manifest("BTCUSDT")
        assert m1.manifest_id == m2.manifest_id
        assert m1.config_hash == m2.config_hash
        assert m1.mode == m2.mode
        assert m1.primary_interval == m2.primary_interval
        assert m1.symbol == m2.symbol

    def test_different_symbols_different_config_hash(self):
        """Different symbols produce different config_hash values."""
        m_btc = build_scalp_manifest("BTCUSDT")
        m_eth = build_scalp_manifest("ETHUSDT")
        assert m_btc.config_hash != m_eth.config_hash

    def test_same_fixture_same_manifest_id(self):
        """Same fixture -> same manifest_id regardless of symbol."""
        m_btc = build_scalp_manifest("BTCUSDT")
        m_eth = build_scalp_manifest("ETHUSDT")
        # Same fixture content -> same checksum -> same manifest_id
        assert m_btc.manifest_id == m_eth.manifest_id

    def test_passes_validation(self):
        """Built manifest passes validate_manifest()."""
        m = build_scalp_manifest("BTCUSDT")
        result = validate_manifest(m)
        assert result is None

    def test_has_limitations(self):
        """Limitations list is populated."""
        m = build_scalp_manifest("BTCUSDT")
        assert isinstance(m.limitations, list)
        assert len(m.limitations) > 0
        assert any("fixture-only" in lim for lim in m.limitations)

    def test_config_hash_is_64_hex(self):
        """config_hash is a 64-character hex string."""
        m = build_scalp_manifest("BTCUSDT")
        assert len(m.config_hash) == 64
        int(m.config_hash, 16)  # valid hex

    def test_has_source_fixtures(self):
        """source_fixtures list is non-empty."""
        m = build_scalp_manifest("BTCUSDT")
        assert len(m.source_fixtures) >= 1
        ref = m.source_fixtures[0]
        assert len(ref.checksum) == 64
        int(ref.checksum, 16)

    def test_has_data_layer_refs(self):
        """data_layer_refs maps layer names to fixture paths."""
        m = build_scalp_manifest("BTCUSDT")
        assert m.data_layer_refs
        assert "simulation_output_minimal" in m.data_layer_refs

    def test_custom_fixture_path(self):
        """Accepts an explicit fixture_path override."""
        m = build_scalp_manifest("DOGEUSDT", fixture_path=MINIMAL_FIXTURE)
        assert m.symbol == "DOGEUSDT"
        assert m.mode == "SCALP"
        assert m.primary_interval == "1h"

    def test_raises_on_missing_fixture(self):
        """Raises FileNotFoundError for non-existent fixture."""
        with pytest.raises(FileNotFoundError):
            build_scalp_manifest("BTCUSDT", fixture_path=Path("/nonexistent/fixture.json"))


# ---------------------------------------------------------------------------
# Symbol universe tests
# ---------------------------------------------------------------------------


class TestScalpSymbols:
    """SCALP_SYMBOLS integrity."""

    def test_has_20_symbols(self):
        """SCALP_SYMBOLS contains exactly 20 symbols."""
        assert len(SCALP_SYMBOLS) == 20

    def test_all_symbols_are_strings(self):
        """Every entry is a string."""
        for s in SCALP_SYMBOLS:
            assert isinstance(s, str)

    def test_all_symbols_end_with_usdt(self):
        """All symbols are USDT-margined pairs."""
        for s in SCALP_SYMBOLS:
            assert s.endswith("USDT"), f"{s} does not end with USDT"

    def test_no_duplicates(self):
        """No duplicate symbols in the list."""
        assert len(SCALP_SYMBOLS) == len(set(SCALP_SYMBOLS))

    def test_btcusdt_is_first(self):
        """BTCUSDT is the first symbol (canonical ordering)."""
        assert SCALP_SYMBOLS[0] == "BTCUSDT"


# ---------------------------------------------------------------------------
# Bulk builder tests
# ---------------------------------------------------------------------------


class TestBuildAllScalpManifests:
    """build_all_scalp_manifests() behavior."""

    def test_returns_20_manifests(self):
        """Returns exactly 20 DataManifest objects."""
        manifests = build_all_scalp_manifests()
        assert len(manifests) == 20

    def test_all_are_datamanifest(self):
        """Every element is a DataManifest."""
        manifests = build_all_scalp_manifests()
        for m in manifests:
            assert isinstance(m, DataManifest)

    def test_all_have_mode_scalp(self):
        """Every manifest has mode=SCALP."""
        manifests = build_all_scalp_manifests()
        for m in manifests:
            assert m.mode == "SCALP"

    def test_all_have_interval_1h(self):
        """Every manifest has primary_interval=1h."""
        manifests = build_all_scalp_manifests()
        for m in manifests:
            assert m.primary_interval == "1h"

    def test_all_have_different_symbols(self):
        """Each manifest has a unique symbol from SCALP_SYMBOLS."""
        manifests = build_all_scalp_manifests()
        symbols = [m.symbol for m in manifests]
        assert sorted(symbols) == sorted(SCALP_SYMBOLS)

    def test_custom_symbol_list(self):
        """Accepts an explicit symbol list override."""
        custom = ["BTCUSDT", "ETHUSDT"]
        manifests = build_all_scalp_manifests(symbols=custom)
        assert len(manifests) == 2
        assert manifests[0].symbol == "BTCUSDT"
        assert manifests[1].symbol == "ETHUSDT"

    def test_all_pass_validation(self):
        """Every manifest in the bulk result passes validation."""
        manifests = build_all_scalp_manifests()
        for m in manifests:
            result = validate_manifest(m)
            assert result is None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestScalpConstants:
    """Module-level constants."""

    def test_scalp_mode_correct(self):
        """SCALP_MODE is 'SCALP'."""
        assert SCALP_MODE == "SCALP"

    def test_scalp_primary_interval_correct(self):
        """SCALP_PRIMARY_INTERVAL is '1h'."""
        assert SCALP_PRIMARY_INTERVAL == "1h"

    def test_scalp_limitations_contains_mode_specific(self):
        """Limitations mention SCALP-specific information."""
        combined = " ".join(SCALP_LIMITATIONS).lower()
        assert "scalp" in combined


# ---------------------------------------------------------------------------
# Import boundary
# ---------------------------------------------------------------------------


class TestScalpManifestImportBoundary:
    """scalp_manifest.py must not import from forbidden domains."""

    FORBIDDEN_PREFIXES = ("simulation.", "v7.", "runtime.", "interface.")

    def test_no_forbidden_imports(self):
        """Verify scalp_manifest.py has no imports from forbidden domains."""
        manifest_path = (
            REPO_ROOT / "alphaforge" / "src" / "alphaforge" / "data" / "scalp_manifest.py"
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
            f"Forbidden imports in scalp_manifest.py:\n" + "\n".join(forbidden_found)
        )
